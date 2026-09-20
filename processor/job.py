from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
)

from processor.main import process_video
from processor.settings import load_settings


def required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise ValueError(
            f"Required environment variable "
            f"{name!r} is missing."
        )

    return value


def environment_float(
    name: str,
    default: float,
) -> float:
    value = os.getenv(name)

    if not value:
        return default

    return float(value)


def environment_int(
    name: str,
    default: int,
) -> int:
    value = os.getenv(name)

    if not value:
        return default

    return int(value)


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def download_source_video(
    blob_service: BlobServiceClient,
    container_name: str,
    blob_name: str,
    local_path: Path,
) -> None:
    local_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=blob_name,
    )

    print(
        f"Downloading "
        f"{container_name}/{blob_name}..."
    )

    with local_path.open("wb") as file_handle:
        blob_client.download_blob().readinto(
            file_handle
        )

    if local_path.stat().st_size == 0:
        raise RuntimeError(
            "Downloaded source video is empty."
        )

    print(
        f"Downloaded {local_path.stat().st_size:,} "
        "bytes."
    )


def upload_job_metadata(
    blob_service: BlobServiceClient,
    container_name: str,
    video_id: str,
    local_path: Path,
) -> None:
    if not local_path.is_file():
        return

    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=f"{video_id}/{local_path.name}",
    )

    with local_path.open("rb") as file_handle:
        blob_client.upload_blob(
            data=file_handle,
            overwrite=True,
            content_settings=ContentSettings(
                content_type="application/json"
            ),
        )


def write_failure_status(
    status_path: Path,
    video_id: str,
    error: Exception,
) -> None:
    status_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Preserve filename from prior status writes if present
    existing_filename = None
    if status_path.is_file():
        try:
            existing_filename = json.loads(
                status_path.read_text(encoding="utf-8")
            ).get("filename")
        except Exception:
            pass

    value = {
        "video_id": video_id,
        "status": "failed",
        "stage": "failed",
        "progress": 100,
        "message": (
            "Container Apps ingestion "
            "job failed."
        ),
        "error": str(error),
        "updated_at": utc_now(),
    }
    if existing_filename:
        value["filename"] = existing_filename

    status_path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    settings = load_settings()

    video_id = required_environment("VIDEO_ID")
    tenant_id = os.getenv(
        "TENANT_ID",
        "dev-user",
    ).strip()
    video_blob_name = required_environment(
        "VIDEO_BLOB_NAME"
    )

    locale = os.getenv(
        "SPEECH_LOCALE",
        "en-US",
    ).strip()

    frame_interval = environment_float(
        "FRAME_INTERVAL_SECONDS",
        10.0,
    )
    max_frames = environment_int(
        "MAX_FRAMES",
        120,
    )
    visual_batch_size = environment_int(
        "VISUAL_BATCH_SIZE",
        6,
    )
    image_detail = os.getenv(
        "IMAGE_DETAIL",
        "low",
    ).strip()

    work_root = Path(
        os.getenv(
            "PROCESSOR_WORK_ROOT",
            "/tmp/video-rag",
        )
    )

    input_directory = (
        work_root / "input" / video_id
    )
    artifacts_root = (
        work_root / "artifacts"
    )
    artifact_directory = (
        artifacts_root / video_id
    )

    source_filename = Path(
        video_blob_name
    ).name

    if not source_filename:
        raise ValueError(
            "VIDEO_BLOB_NAME doesn't contain "
            "a filename."
        )

    local_video_path = (
        input_directory / source_filename
    )

    credential = DefaultAzureCredential()
    blob_service = BlobServiceClient(
        account_url=settings.storage_account_url,
        credential=credential,
    )

    status_path = (
        artifact_directory
        / "processing_status.json"
    )

    try:
        download_source_video(
            blob_service=blob_service,
            container_name=(
                settings.video_container
            ),
            blob_name=video_blob_name,
            local_path=local_video_path,
        )

        result = process_video(
            video_path=local_video_path,
            video_id=video_id,
            tenant_id=tenant_id,
            artifacts_root=artifacts_root,
            frame_interval=frame_interval,
            max_frames=max_frames,
            visual_batch_size=(
                visual_batch_size
            ),
            image_detail=image_detail,
            locale=locale,
        )

        upload_job_metadata(
            blob_service=blob_service,
            container_name=(
                settings.metadata_container
            ),
            video_id=video_id,
            local_path=status_path,
        )

        upload_job_metadata(
            blob_service=blob_service,
            container_name=(
                settings.metadata_container
            ),
            video_id=video_id,
            local_path=(
                artifact_directory
                / "processing_result.json"
            ),
        )

        print("\nContainer Apps Job completed:")
        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

    except Exception as error:
        write_failure_status(
            status_path=status_path,
            video_id=video_id,
            error=error,
        )

        upload_job_metadata(
            blob_service=blob_service,
            container_name=(
                settings.metadata_container
            ),
            video_id=video_id,
            local_path=status_path,
        )

        raise


if __name__ == "__main__":
    main()