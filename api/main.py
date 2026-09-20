from __future__ import annotations

import asyncio
import io
import json
import re
import subprocess
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import conversations as conv_svc
from . import foundry_agent as agent_svc
from . import processor_jobs as job_svc
from .models import (
    CitationModel,
    ConversationListResponse,
    ConversationResponse,
    MessageRequest,
    MessageResponse,
    PatchConversationRequest,
    ProcessingStatusResponse,
    ProcessJobResponse,
    VideoContentResponse,
    VideoFromUrlRequest,
    VideoFromUrlResponse,
    VideoMetadata,
    VideoUploadResponse,
)
from .settings import Settings, get_settings
from .storage import (
    download_blob_json,
    generate_video_sas_url,
    get_blob_service_client,
    get_table_service_client,
    upload_blob_bytes,
    upload_blob_stream,
)

# ---------------------------------------------------------------------------
# Private IP / localhost detection for URL validation
# ---------------------------------------------------------------------------

import ipaddress
import socket


def _is_private_url(url: str) -> bool:
    """Return True if the URL resolves to a private/loopback address."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return True
        # Resolve and check
        addr = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(addr)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except Exception:
        # If resolution fails, reject it to be safe
        return True


# ---------------------------------------------------------------------------
# Lifespan — initialise shared clients once
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Build credential — uses AZURE_CLIENT_ID env var for workload identity
    credential = DefaultAzureCredential(
        managed_identity_client_id=settings.azure_client_id or None
    )

    blob_service = get_blob_service_client(credential, settings.azure_storage_account_url)
    table_service = get_table_service_client(credential, settings.azure_table_account_url)

    # Ensure the Conversations table exists
    try:
        table_service.create_table(settings.conversations_table_name)
    except Exception:
        pass  # Table already exists

    # Store in app.state for endpoint access
    app.state.credential = credential
    app.state.blob_service = blob_service
    app.state.table_service = table_service
    app.state.settings = settings

    yield

    # Cleanup (close SDK clients that support it)
    try:
        blob_service.close()
    except Exception:
        pass
    try:
        table_service.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Video RAG API",
        version="1.0.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return application


app = create_app()

# ---------------------------------------------------------------------------
# React SPA static files at /ui
# ---------------------------------------------------------------------------

_UI_DIST = Path(__file__).parent.parent / "ui" / "dist"

if _UI_DIST.is_dir():
    app.mount("/ui/assets", StaticFiles(directory=_UI_DIST / "assets"), name="ui-assets")

    @app.get("/ui/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Serve index.html for all /ui/* routes so React Router handles navigation."""
        return FileResponse(_UI_DIST / "index.html")

    @app.get("/ui", include_in_schema=False)
    async def serve_spa_root():
        return FileResponse(_UI_DIST / "index.html")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(request: Request):
    return request.app.state


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Video upload (multipart)
# ---------------------------------------------------------------------------

@app.post("/api/videos/upload", response_model=VideoUploadResponse, status_code=201)
def upload_video(request: Request, file: UploadFile = File(...)):
    filename = file.filename or "video.mp4"

    if not filename.lower().endswith(".mp4"):
        raise HTTPException(status_code=422, detail="Only .mp4 files are supported.")

    state = _state(request)
    settings: Settings = state.settings
    blob_service = state.blob_service

    max_bytes = settings.max_upload_mb * 1024 * 1024
    video_id = str(uuid.uuid4())
    blob_name = f"{video_id}/{filename}"

    # Stream upload — read in chunks to avoid buffering the whole file
    class _ChunkedStream:
        def __init__(self, upload_file: UploadFile, max_size: int):
            self._f = upload_file
            self._max = max_size
            self._read = 0

        def read(self, size: int = -1) -> bytes:
            chunk = self._f.file.read(size if size > 0 else -1)
            self._read += len(chunk)
            if self._read > self._max:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum size of {settings.max_upload_mb} MB.",
                )
            return chunk

    stream = _ChunkedStream(file, max_bytes)
    upload_blob_stream(
        blob_service,
        settings.video_container_name,
        blob_name,
        stream,
        content_type=file.content_type or "video/mp4",
    )

    # Write initial processing status
    initial_status = {
        "video_id": video_id,
        "status": "uploaded",
        "stage": "queued",
        "progress": 0,
        "message": "Video uploaded, waiting to be processed.",
        "filename": filename,
    }
    upload_blob_bytes(
        blob_service,
        settings.metadata_container_name,
        f"{video_id}/processing_status.json",
        json.dumps(initial_status).encode(),
    )

    return VideoUploadResponse(video_id=video_id, filename=filename, status="uploaded")


# ---------------------------------------------------------------------------
# Video from URL
# ---------------------------------------------------------------------------

@app.post("/api/videos/from-url", response_model=VideoFromUrlResponse, status_code=201)
async def video_from_url(request: Request, body: VideoFromUrlRequest):
    url = body.url
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail="Only http/https URLs are supported.")

    if _is_private_url(url):
        raise HTTPException(
            status_code=422,
            detail="Private/loopback IP addresses are not allowed.",
        )

    state = _state(request)
    settings: Settings = state.settings
    blob_service = state.blob_service
    max_bytes = settings.max_upload_mb * 1024 * 1024

    # Derive a filename from the URL path
    url_path = parsed.path.rstrip("/")
    filename = url_path.split("/")[-1] or "video.mp4"
    if not filename.lower().endswith(".mp4"):
        filename = filename + ".mp4"

    video_id = str(uuid.uuid4())
    blob_name = f"{video_id}/{filename}"

    # Stream download with httpx
    buffer = io.BytesIO()
    total = 0
    content_type = "video/mp4"

    async with httpx.AsyncClient(
        follow_redirects=True,
        max_redirects=3,
        timeout=30,
    ) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if not ct.startswith("video/") and not filename.lower().endswith(".mp4"):
                raise HTTPException(
                    status_code=422,
                    detail="URL does not point to a video file.",
                )
            if ct:
                content_type = ct.split(";")[0].strip()

            async for chunk in resp.aiter_bytes(chunk_size=4 * 1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Remote video exceeds maximum size of {settings.max_upload_mb} MB.",
                    )
                buffer.write(chunk)

    buffer.seek(0)

    # Upload to blob storage (blocking call — run in thread pool)
    await asyncio.to_thread(
        upload_blob_stream,
        blob_service,
        settings.video_container_name,
        blob_name,
        buffer,
        content_type,
    )

    # Write initial processing status
    initial_status = {
        "video_id": video_id,
        "status": "uploaded",
        "stage": "queued",
        "progress": 0,
        "message": "Video uploaded from URL, waiting to be processed.",
        "filename": filename,
    }
    await asyncio.to_thread(
        upload_blob_bytes,
        blob_service,
        settings.metadata_container_name,
        f"{video_id}/processing_status.json",
        json.dumps(initial_status).encode(),
    )

    return VideoFromUrlResponse(video_id=video_id, filename=filename, status="uploaded")


# ---------------------------------------------------------------------------
# YouTube download → blob → processor (background task)
# ---------------------------------------------------------------------------

async def _download_youtube_and_process(
    url: str,
    video_id: str,
    blob_service: Any,
    settings: Settings,
    credential: Any,
) -> None:
    meta_container = settings.metadata_container_name

    async def _write_status(
        stage: str,
        progress: int,
        message: str,
        status: str = "processing",
        filename: str = "video.mp4",
    ) -> None:
        data = {
            "video_id": video_id,
            "status": status,
            "stage": stage,
            "progress": progress,
            "message": message,
            "filename": filename,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await asyncio.to_thread(
            upload_blob_bytes,
            blob_service,
            meta_container,
            f"{video_id}/processing_status.json",
            json.dumps(data).encode(),
        )

    filename = "video.mp4"
    blob_name = f"{video_id}/{filename}"

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_tpl = str(Path(tmpdir) / "%(title)s.%(ext)s")
            cmd = [
                "yt-dlp",
                "--format",
                "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]"
                "/bestvideo[height<=720]+bestaudio"
                "/best[ext=mp4][height<=720]"
                "/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "--output", output_tpl,
                "--restrict-filenames",
                "--no-playlist",
                # Use the iOS player client to bypass bot-detection on YouTube
                "--extractor-args", "youtube:player_client=ios,web_creator,mweb",
                url,
            ]
            proc = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=600
            )
            if proc.returncode != 0:
                stderr = (proc.stderr or proc.stdout or "")[-500:]
                raise RuntimeError(f"yt-dlp exited {proc.returncode}: {stderr}")

            mp4_files = sorted(Path(tmpdir).glob("*.mp4"))
            if not mp4_files:
                raise RuntimeError("yt-dlp produced no .mp4 file.")
            local_file = mp4_files[0]
            filename = local_file.name
            blob_name = f"{video_id}/{filename}"

            await _write_status("uploading", 15, "Uploading to cloud storage...", filename=filename)

            with local_file.open("rb") as fh:
                await asyncio.to_thread(
                    upload_blob_stream,
                    blob_service,
                    settings.video_container_name,
                    blob_name,
                    fh,
                    "video/mp4",
                )

        # Temp dir cleaned up; trigger processor
        await _write_status("queued", 20, "Starting video analysis...", filename=filename)

        await asyncio.to_thread(
            job_svc.start_processor_job,
            credential,
            settings,
            video_id=video_id,
            tenant_id=settings.tenant_id,
            blob_name=blob_name,
        )

    except Exception as exc:
        err_data = {
            "video_id": video_id,
            "status": "failed",
            "stage": "failed",
            "progress": 0,
            "message": f"YouTube processing failed: {exc}",
            "filename": filename,
        }
        await asyncio.to_thread(
            upload_blob_bytes,
            blob_service,
            meta_container,
            f"{video_id}/processing_status.json",
            json.dumps(err_data).encode(),
        )


@app.post("/api/videos/from-link", response_model=VideoFromUrlResponse, status_code=201)
async def video_from_link(
    request: Request,
    body: VideoFromUrlRequest,
    background_tasks: BackgroundTasks,
):
    url = body.url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Please provide a valid http/https URL.")

    state = _state(request)
    settings: Settings = state.settings
    blob_service = state.blob_service
    video_id = str(uuid.uuid4())

    # Write immediate status so the polling page has something to display
    initial_status = {
        "video_id": video_id,
        "status": "processing",
        "stage": "downloading",
        "progress": 5,
        "message": "Downloading video from YouTube...",
        "filename": "video.mp4",
    }
    upload_blob_bytes(
        blob_service,
        settings.metadata_container_name,
        f"{video_id}/processing_status.json",
        json.dumps(initial_status).encode(),
    )

    background_tasks.add_task(
        _download_youtube_and_process,
        url,
        video_id,
        blob_service,
        settings,
        state.credential,
    )

    return VideoFromUrlResponse(video_id=video_id, filename="video.mp4", status="downloading")


# ---------------------------------------------------------------------------
# Trigger processor job
# ---------------------------------------------------------------------------

@app.post("/api/videos/{video_id}/process", response_model=ProcessJobResponse)
def process_video(request: Request, video_id: str):
    state = _state(request)
    settings: Settings = state.settings
    blob_service = state.blob_service

    # Retrieve the status blob to get the filename
    status_data = download_blob_json(
        blob_service,
        settings.metadata_container_name,
        f"{video_id}/processing_status.json",
    )
    if status_data is None:
        raise HTTPException(status_code=404, detail="Video not found.")

    filename = status_data.get("filename")
    if not filename:
        # Fall back to listing video container for the actual file
        try:
            cc = blob_service.get_container_client(settings.video_container_name)
            blobs = list(cc.list_blobs(name_starts_with=f"{video_id}/"))
            vid_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
            matches = [b.name for b in blobs if any(b.name.lower().endswith(e) for e in vid_exts)]
            filename = matches[0].split("/", 1)[1] if matches else "video.mp4"
        except Exception:
            filename = "video.mp4"
    blob_name = f"{video_id}/{filename}"

    try:
        execution_name = job_svc.start_processor_job(
            state.credential,
            settings,
            video_id=video_id,
            tenant_id=settings.tenant_id,
            blob_name=blob_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to start processor job: {exc}")

    return ProcessJobResponse(execution_name=execution_name, status="triggered")


# ---------------------------------------------------------------------------
# Processing status
# ---------------------------------------------------------------------------

@app.get("/api/videos/{video_id}/status", response_model=ProcessingStatusResponse)
def get_video_status(request: Request, video_id: str):
    state = _state(request)
    settings: Settings = state.settings
    blob_service = state.blob_service

    data = download_blob_json(
        blob_service,
        settings.metadata_container_name,
        f"{video_id}/processing_status.json",
    )
    if data is None:
        # Blob not yet written — treat as freshly queued
        return ProcessingStatusResponse(
            video_id=video_id,
            status="uploaded",
            stage="queued",
            progress=0,
        )

    return ProcessingStatusResponse(
        video_id=video_id,
        status=data.get("status", "unknown"),
        stage=data.get("stage", "unknown"),
        progress=int(data.get("progress", 0)),
        message=data.get("message"),
        updated_at=data.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Video metadata
# ---------------------------------------------------------------------------

@app.get("/api/videos/{video_id}", response_model=VideoMetadata)
def get_video_metadata(request: Request, video_id: str):
    state = _state(request)
    settings: Settings = state.settings
    blob_service = state.blob_service

    data = download_blob_json(
        blob_service,
        settings.metadata_container_name,
        f"{video_id}/processing_status.json",
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Video not found.")

    return VideoMetadata(
        video_id=video_id,
        filename=data.get("filename", ""),
        status=data.get("status", "unknown"),
        stage=data.get("stage"),
        progress=int(data.get("progress", 0)),
        updated_at=data.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Short-lived SAS URL for video content
# ---------------------------------------------------------------------------

@app.get("/api/videos/{video_id}/content", response_model=VideoContentResponse)
def get_video_content(request: Request, video_id: str):
    state = _state(request)
    settings: Settings = state.settings
    blob_service = state.blob_service

    # Look up the original filename from metadata
    status_data = download_blob_json(
        blob_service,
        settings.metadata_container_name,
        f"{video_id}/processing_status.json",
    )
    if status_data is None:
        raise HTTPException(status_code=404, detail="Video not found.")

    filename = status_data.get("filename", "video.mp4")
    blob_name = f"{video_id}/{filename}"

    sas_url = generate_video_sas_url(
        storage_account_url=settings.azure_storage_account_url,
        account_name=settings.storage_account_name,
        container=settings.video_container_name,
        blob_name=blob_name,
        credential=state.credential,
        expiry_minutes=5,
    )

    return VideoContentResponse(url=sas_url, expires_in_seconds=300)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

@app.post(
    "/api/videos/{video_id}/conversations",
    response_model=ConversationResponse,
    status_code=201,
)
def create_conversation(request: Request, video_id: str):
    state = _state(request)
    settings: Settings = state.settings
    blob_service = state.blob_service
    table_service = state.table_service

    # Retrieve the filename for display
    status_data = download_blob_json(
        blob_service,
        settings.metadata_container_name,
        f"{video_id}/processing_status.json",
    )
    if status_data is None:
        raise HTTPException(status_code=404, detail="Video not found.")

    video_name = status_data.get("filename", "video.mp4")

    # Create a Foundry conversation
    openai_client = agent_svc.get_openai_client(settings, state.credential)
    foundry_conversation_id = agent_svc.create_foundry_conversation(openai_client)

    conversation = conv_svc.create_conversation(
        table_service=table_service,
        settings=settings,
        video_id=video_id,
        video_name=video_name,
        foundry_conversation_id=foundry_conversation_id,
    )
    return conversation


@app.get("/api/conversations", response_model=ConversationListResponse)
def list_conversations(request: Request):
    state = _state(request)
    items = conv_svc.list_conversations(state.table_service, state.settings)
    return ConversationListResponse(conversations=items, total=len(items))


@app.get("/api/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(request: Request, conversation_id: str):
    state = _state(request)
    item = conv_svc.get_conversation(
        state.table_service, state.settings, conversation_id
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return item


@app.get("/api/conversations/{conversation_id}/messages")
def list_messages(request: Request, conversation_id: str):
    """
    Message history is managed by Foundry; the UI should render messages
    from its local state. This endpoint returns an empty list as a stub.
    """
    # Validate the conversation exists
    state = _state(request)
    item = conv_svc.get_conversation(
        state.table_service, state.settings, conversation_id
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"messages": [], "conversation_id": conversation_id}


@app.post(
    "/api/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
)
def send_message(request: Request, conversation_id: str, body: MessageRequest):
    state = _state(request)
    settings: Settings = state.settings

    # Load conversation to retrieve foundry_conversation_id + video_id
    table_client = state.table_service.get_table_client(settings.conversations_table_name)
    try:
        entity = table_client.get_entity(
            partition_key=settings.tenant_id,
            row_key=conversation_id,
        )
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    if entity.get("Status") == "deleted":
        raise HTTPException(status_code=404, detail="Conversation not found.")

    foundry_conversation_id: str = entity["FoundryConversationId"]
    video_id: str = entity.get("VideoId", "")
    current_count = int(entity.get("MessageCount", 0))

    openai_client = agent_svc.get_openai_client(settings, state.credential)

    result = agent_svc.send_message(
        openai_client=openai_client,
        foundry_conversation_id=foundry_conversation_id,
        question=body.message,
        tenant_id=settings.tenant_id,
        video_id=video_id,
        agent_name=settings.foundry_agent_name,
    )

    answer: str = result["answer"]
    citations_raw: list[dict] = result["citations"]
    response_id: str = result["response_id"]

    new_count = current_count + 1
    preview = answer[:120]

    conv_svc.update_conversation_after_message(
        table_service=state.table_service,
        settings=settings,
        conversation_id=conversation_id,
        last_message_preview=preview,
        message_count=new_count,
    )

    return MessageResponse(
        conversation_id=conversation_id,
        answer=answer,
        citations=[CitationModel(**c) for c in citations_raw],
        response_id=response_id,
    )


@app.patch("/api/conversations/{conversation_id}", response_model=ConversationResponse)
def patch_conversation(
    request: Request, conversation_id: str, body: PatchConversationRequest
):
    state = _state(request)
    try:
        result = conv_svc.patch_conversation(
            state.table_service, state.settings, conversation_id, body.title
        )
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return result


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(request: Request, conversation_id: str):
    state = _state(request)
    conv_svc.delete_conversation(
        state.table_service, state.settings, conversation_id
    )
    return None
