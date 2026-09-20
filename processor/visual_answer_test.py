from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path

from azure.identity import (
    DefaultAzureCredential,
    get_bearer_token_provider,
)
from azure.storage.blob import BlobServiceClient
from openai import OpenAI

from processor.frame_extractor import (
    format_timestamp,
)
from processor.search_test import search_video
from processor.settings import load_settings


MAX_TOTAL_IMAGE_BYTES = 45 * 1024 * 1024


def get_blob_name(
    stored_path: str,
    container_name: str,
) -> str:
    prefix = f"{container_name}/"

    if stored_path.startswith(prefix):
        return stored_path[len(prefix) :]

    return stored_path


def timestamp_from_blob_name(
    blob_name: str,
) -> tuple[int, str]:
    filename = Path(blob_name).name

    match = re.search(
        r"_(\d{10})\.jpg$",
        filename,
        flags=re.IGNORECASE,
    )

    if match is None:
        raise ValueError(
            "Frame filename doesn't contain the "
            f"expected timestamp: {filename}"
        )

    timestamp_ms = int(match.group(1))

    return (
        timestamp_ms,
        format_timestamp(timestamp_ms / 1000),
    )


def select_frame_paths(
    documents: list[dict],
    max_frames: int,
) -> list[str]:
    if not 1 <= max_frames <= 20:
        raise ValueError(
            "max_frames must be between 1 and 20."
        )

    selected = []
    seen = set()

    for document in documents:
        for frame_path in document.get(
            "frame_blob_paths",
            [],
        ):
            if frame_path in seen:
                continue

            seen.add(frame_path)
            selected.append(frame_path)

            if len(selected) >= max_frames:
                return selected

    return selected


def download_frames(
    frame_paths: list[str],
) -> list[dict]:
    settings = load_settings()

    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False
    )

    blob_service = BlobServiceClient(
        account_url=settings.storage_account_url,
        credential=credential,
    )

    container_client = (
        blob_service.get_container_client(
            settings.frames_container
        )
    )

    frames = []
    total_bytes = 0

    for stored_path in frame_paths:
        blob_name = get_blob_name(
            stored_path=stored_path,
            container_name=(
                settings.frames_container
            ),
        )

        blob_client = (
            container_client.get_blob_client(
                blob_name
            )
        )

        image_bytes = (
            blob_client.download_blob().readall()
        )

        total_bytes += len(image_bytes)

        if total_bytes > MAX_TOTAL_IMAGE_BYTES:
            raise ValueError(
                "Downloaded frames exceed the "
                "45 MB request safety limit."
            )

        timestamp_ms, timestamp = (
            timestamp_from_blob_name(blob_name)
        )

        frames.append(
            {
                "stored_path": stored_path,
                "blob_name": blob_name,
                "timestamp_ms": timestamp_ms,
                "timestamp": timestamp,
                "image_bytes": image_bytes,
            }
        )

    return frames


def image_as_data_url(
    image_bytes: bytes,
) -> str:
    encoded = base64.b64encode(
        image_bytes
    ).decode("ascii")

    return f"data:image/jpeg;base64,{encoded}"


def build_text_evidence(
    documents: list[dict],
) -> str:
    sections = []

    for document in documents:
        sections.append(
            "\n".join(
                [
                    (
                        f"Timeline evidence "
                        f"[{document['timestamp']}]"
                    ),
                    document.get("content", ""),
                ]
            )
        )

    return "\n\n---\n\n".join(sections)


def answer_with_visual_evidence(
    question: str,
    tenant_id: str,
    video_id: str,
    top_chunks: int = 3,
    max_frames: int = 8,
    image_detail: str = "low",
) -> dict:
    settings = load_settings()

    documents = search_video(
        question=question,
        tenant_id=tenant_id,
        video_id=video_id,
        top=top_chunks,
    )

    if not documents:
        return {
            "question": question,
            "answer": (
                "No relevant evidence was found "
                "in the indexed video."
            ),
            "retrieved_chunks": [],
            "frames": [],
        }

    frame_paths = select_frame_paths(
        documents=documents,
        max_frames=max_frames,
    )

    if not frame_paths:
        raise RuntimeError(
            "Retrieved Search documents did not "
            "contain any frame references."
        )

    print(
        f"Downloading {len(frame_paths)} "
        "relevant frames..."
    )

    frames = download_frames(frame_paths)

    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False
    )

    token_provider = get_bearer_token_provider(
        credential,
        "https://ai.azure.com/.default",
    )

    openai_client = OpenAI(
        base_url=settings.openai_base_url,
        api_key=token_provider,
    )

    text_evidence = build_text_evidence(
        documents
    )

    content = [
        {
            "type": "input_text",
            "text": (
                f"Question:\n{question}\n\n"
                "Retrieved timestamped evidence:\n"
                f"{text_evidence}\n\n"
                "Relevant original video frames follow. "
                "Use the frames to verify visible text, "
                "objects, layout, actions, and state "
                "changes before answering."
            ),
        }
    ]

    for frame in frames:
        content.append(
            {
                "type": "input_text",
                "text": (
                    "Original video frame at "
                    f"[{frame['timestamp']}]"
                ),
            }
        )

        content.append(
            {
                "type": "input_image",
                "image_url": image_as_data_url(
                    frame["image_bytes"]
                ),
                "detail": image_detail,
            }
        )

    print(
        "Sending retrieved text and frames "
        "to GPT-5.4..."
    )

    response = openai_client.responses.create(
        model=settings.gpt_deployment_name,
        instructions=(
            "Answer questions about a video using only "
            "the supplied retrieved evidence and original "
            "frames. Cite each important factual claim "
            "using [HH:MM:SS-HH:MM:SS] when referring "
            "to a timeline segment, or [HH:MM:SS] when "
            "referring to a specific frame. Do not invent "
            "details. If the evidence is insufficient, "
            "say so clearly."
        ),
        input=[
            {
                "role": "user",
                "content": content,
            }
        ],
        max_output_tokens=1200,
        store=False,
    )

    answer = response.output_text.strip()

    if not answer:
        raise RuntimeError(
            "GPT-5.4 returned an empty answer."
        )

    return {
        "question": question,
        "tenant_id": tenant_id,
        "video_id": video_id,
        "answer": answer,
        "retrieved_chunks": [
            {
                "id": document["id"],
                "timestamp": document["timestamp"],
                "title": document["chunk_title"],
                "source_url": document[
                    "source_url"
                ],
            }
            for document in documents
        ],
        "frames": [
            {
                "timestamp": frame["timestamp"],
                "timestamp_ms": frame[
                    "timestamp_ms"
                ],
                "blob_name": frame["blob_name"],
            }
            for frame in frames
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve relevant video chunks and "
            "perform GPT-5.4 visual verification."
        )
    )
    parser.add_argument(
        "--question",
        required=True,
    )
    parser.add_argument(
        "--tenant-id",
        required=True,
    )
    parser.add_argument(
        "--video-id",
        required=True,
    )
    parser.add_argument(
        "--top-chunks",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=8,
    )
    parser.add_argument(
        "--detail",
        choices=["low", "high", "auto"],
        default="low",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    arguments = parser.parse_args()

    result = answer_with_visual_evidence(
        question=arguments.question,
        tenant_id=arguments.tenant_id,
        video_id=arguments.video_id,
        top_chunks=arguments.top_chunks,
        max_frames=arguments.max_frames,
        image_detail=arguments.detail,
    )

    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    arguments.output.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\nMultimodal answer:\n")
    print(result["answer"])

    print(
        f"\nRetrieved chunks: "
        f"{len(result['retrieved_chunks'])}"
    )
    print(
        f"Frames inspected: "
        f"{len(result['frames'])}"
    )
    print(
        f"Output: "
        f"{arguments.output.resolve()}"
    )


if __name__ == "__main__":
    main()