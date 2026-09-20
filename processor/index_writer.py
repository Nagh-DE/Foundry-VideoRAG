from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
from typing import Iterable

from azure.identity import (
    DefaultAzureCredential,
    get_bearer_token_provider,
)
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
)

from processor.settings import load_settings


METADATA_FILES = (
    "source_manifest.json",
    "processing_status.json",
    "frame_manifest.json",
    "transcript.json",
    "speech_response.json",
    "visual_descriptions.json",
    "timeline_chunks.json",
    "timeline.md",
)


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    return json.loads(
        path.read_text(encoding="utf-8")
    )


def batched(
    items: list,
    batch_size: int,
) -> Iterable[list]:
    if batch_size <= 0:
        raise ValueError(
            "batch_size must be greater than zero."
        )

    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def content_type_for(path: Path) -> str:
    content_type, _ = mimetypes.guess_type(
        path.name
    )

    if content_type:
        return content_type

    if path.suffix.lower() == ".json":
        return "application/json"

    if path.suffix.lower() == ".md":
        return "text/markdown"

    return "application/octet-stream"


def upload_file(
    container_client,
    local_path: Path,
    blob_name: str,
) -> None:
    if not local_path.is_file():
        raise FileNotFoundError(
            f"Upload file not found: {local_path}"
        )

    blob_client = container_client.get_blob_client(
        blob_name
    )

    with local_path.open("rb") as file_handle:
        blob_client.upload_blob(
            data=file_handle,
            overwrite=True,
            content_settings=ContentSettings(
                content_type=content_type_for(
                    local_path
                )
            ),
        )


def generate_embeddings(
    chunks: list[dict],
    openai_client,
    deployment_name: str,
    dimensions: int,
    batch_size: int = 16,
) -> None:
    for batch_number, chunk_batch in enumerate(
        batched(chunks, batch_size),
        start=1,
    ):
        texts = [
            chunk["content"]
            for chunk in chunk_batch
        ]

        print(
            f"Generating embeddings for batch "
            f"{batch_number}..."
        )

        response = openai_client.embeddings.create(
            model=deployment_name,
            input=texts,
            dimensions=dimensions,
        )

        ordered_embeddings = sorted(
            response.data,
            key=lambda item: item.index,
        )

        if len(ordered_embeddings) != len(
            chunk_batch
        ):
            raise RuntimeError(
                "Embedding response count did not "
                "match the input count."
            )

        for chunk, embedding_item in zip(
            chunk_batch,
            ordered_embeddings,
            strict=True,
        ):
            embedding = embedding_item.embedding

            if len(embedding) != dimensions:
                raise RuntimeError(
                    "Embedding dimension mismatch. "
                    f"Expected {dimensions}, "
                    f"received {len(embedding)}."
                )

            chunk["content_vector"] = embedding


def escape_odata(value: str) -> str:
    return value.replace("'", "''")


def delete_existing_video_documents(
    search_client: SearchClient,
    tenant_id: str,
    video_id: str,
) -> None:
    filter_expression = (
        f"tenant_id eq "
        f"'{escape_odata(tenant_id)}' and "
        f"video_id eq "
        f"'{escape_odata(video_id)}'"
    )

    results = search_client.search(
        search_text="*",
        filter=filter_expression,
        select=["id"],
        top=1000,
    )

    documents = [
        {"id": result["id"]}
        for result in results
    ]

    if not documents:
        print(
            "No existing Search documents "
            "need deletion."
        )
        return

    print(
        f"Deleting {len(documents)} existing "
        "Search documents..."
    )

    for document_batch in batched(
        documents,
        1000,
    ):
        indexing_results = (
            search_client.delete_documents(
                documents=document_batch
            )
        )

        failures = [
            result
            for result in indexing_results
            if not result.succeeded
        ]

        if failures:
            details = "; ".join(
                (
                    f"{result.key}: "
                    f"{result.error_message}"
                )
                for result in failures
            )

            raise RuntimeError(
                "Deleting existing Search documents "
                f"failed: {details}"
            )


def upload_search_documents(
    search_client: SearchClient,
    chunks: list[dict],
) -> None:
    for chunk_batch in batched(chunks, 1000):
        results = search_client.upload_documents(
            documents=chunk_batch
        )

        failures = [
            result
            for result in results
            if not result.succeeded
        ]

        if failures:
            details = "; ".join(
                (
                    f"{result.key}: "
                    f"{result.error_message}"
                )
                for result in failures
            )

            raise RuntimeError(
                "Uploading Search documents failed: "
                f"{details}"
            )


def publish_video(
    video_path: Path,
    artifact_directory: Path,
    timeline_path: Path,
) -> dict:
    settings = load_settings()

    video_path = video_path.resolve()
    artifact_directory = (
        artifact_directory.resolve()
    )
    timeline_path = timeline_path.resolve()

    if not video_path.is_file():
        raise FileNotFoundError(
            f"Video not found: {video_path}"
        )

    frames_directory = (
        artifact_directory / "frames"
    )

    if not frames_directory.is_dir():
        raise FileNotFoundError(
            f"Frames directory not found: "
            f"{frames_directory}"
        )

    timeline = load_json(timeline_path)

    video_metadata = timeline["video"]
    chunks = timeline["chunks"]

    if not chunks:
        raise ValueError(
            "Timeline contains no chunks."
        )

    video_id = video_metadata["video_id"]
    tenant_id = video_metadata["tenant_id"]

    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False
    )

    blob_service = BlobServiceClient(
        account_url=settings.storage_account_url,
        credential=credential,
    )

    videos_container = (
        blob_service.get_container_client(
            settings.video_container
        )
    )
    frames_container = (
        blob_service.get_container_client(
            settings.frames_container
        )
    )
    metadata_container = (
        blob_service.get_container_client(
            settings.metadata_container
        )
    )

    print("Uploading source video...")

    source_blob_name = (
        f"{video_id}/{video_path.name}"
    )

    upload_file(
        container_client=videos_container,
        local_path=video_path,
        blob_name=source_blob_name,
    )

    print("Uploading extracted frames...")

    frame_files = sorted(
        frames_directory.glob("*.jpg")
    )

    if not frame_files:
        raise RuntimeError(
            "No JPG frames were found."
        )

    uploaded_frame_blobs = []

    for frame_path in frame_files:
        blob_name = (
            f"{video_id}/{frame_path.name}"
        )

        upload_file(
            container_client=frames_container,
            local_path=frame_path,
            blob_name=blob_name,
        )

        uploaded_frame_blobs.append(
            f"{settings.frames_container}/"
            f"{blob_name}"
        )

    print(
        f"Uploaded {len(uploaded_frame_blobs)} "
        "frames."
    )

    print("Uploading processing metadata...")

    uploaded_metadata_blobs = []

    for filename in METADATA_FILES:
        local_path = artifact_directory / filename

        if not local_path.is_file():
            continue

        blob_name = f"{video_id}/{filename}"

        upload_file(
            container_client=metadata_container,
            local_path=local_path,
            blob_name=blob_name,
        )

        uploaded_metadata_blobs.append(
            f"{settings.metadata_container}/"
            f"{blob_name}"
        )

    print("Generating timeline embeddings...")

    token_provider = get_bearer_token_provider(
        credential,
        "https://cognitiveservices.azure.com/.default",
    )

    # Derive azure_endpoint from openai_base_url
    # e.g. https://ACCOUNT.openai.azure.com/openai/v1/ → https://ACCOUNT.openai.azure.com
    openai_base = settings.openai_base_url.rstrip("/")
    if openai_base.endswith("/openai/v1"):
        azure_endpoint = openai_base[: -len("/openai/v1")]
    elif openai_base.endswith("/openai"):
        azure_endpoint = openai_base[: -len("/openai")]
    else:
        azure_endpoint = openai_base

    openai_client = AzureOpenAI(
        azure_endpoint=azure_endpoint,
        azure_ad_token_provider=token_provider,
        api_version="2024-12-01-preview",
        max_retries=10,
    )

    generate_embeddings(
        chunks=chunks,
        openai_client=openai_client,
        deployment_name=(
            settings.embedding_deployment_name
        ),
        dimensions=settings.embedding_dimensions,
    )

    print("Connecting to Azure AI Search...")

    search_client = SearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.search_index_name,
        credential=credential,
    )

    delete_existing_video_documents(
        search_client=search_client,
        tenant_id=tenant_id,
        video_id=video_id,
    )

    print(
        f"Uploading {len(chunks)} timeline "
        "documents to Search..."
    )

    upload_search_documents(
        search_client=search_client,
        chunks=chunks,
    )

    publish_result = {
        "tenant_id": tenant_id,
        "video_id": video_id,
        "video_name": video_metadata[
            "video_name"
        ],
        "source_blob": (
            f"{settings.video_container}/"
            f"{source_blob_name}"
        ),
        "frame_count": len(
            uploaded_frame_blobs
        ),
        "frame_blobs": uploaded_frame_blobs,
        "metadata_blobs": uploaded_metadata_blobs,
        "search_index": (
            settings.search_index_name
        ),
        "search_document_count": len(chunks),
        "search_document_ids": [
            chunk["id"]
            for chunk in chunks
        ],
        "status": "published",
    }

    publish_manifest_path = (
        artifact_directory
        / "publish_manifest.json"
    )

    publish_manifest_path.write_text(
        json.dumps(
            publish_result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    upload_file(
        container_client=metadata_container,
        local_path=publish_manifest_path,
        blob_name=(
            f"{video_id}/publish_manifest.json"
        ),
    )

    return publish_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Upload video artifacts and index "
            "timeline chunks in Azure AI Search."
        )
    )
    parser.add_argument(
        "--video",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--timeline",
        type=Path,
        required=True,
    )

    arguments = parser.parse_args()

    result = publish_video(
        video_path=arguments.video,
        artifact_directory=arguments.artifacts,
        timeline_path=arguments.timeline,
    )

    print("\nVideo publication completed.")
    print(f"Video ID: {result['video_id']}")
    print(
        f"Frames uploaded: "
        f"{result['frame_count']}"
    )
    print(
        f"Search documents uploaded: "
        f"{result['search_document_count']}"
    )
    print(
        f"Search index: "
        f"{result['search_index']}"
    )


if __name__ == "__main__":
    main()