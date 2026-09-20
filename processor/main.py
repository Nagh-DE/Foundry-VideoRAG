from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from processor.frame_describer import (
    describe_frame_batches,
)
from processor.frame_extractor import (
    extract_frames,
)
from processor.index_writer import publish_video
from processor.timeline_builder import (
    build_timeline,
)
from processor.transcriber import transcribe_video


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        while chunk := file_handle.read(
            1024 * 1024
        ):
            digest.update(chunk)

    return digest.hexdigest()


def write_json_atomic(
    path: Path,
    value: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        f"{path.suffix}.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(path)


def write_status(
    status_path: Path,
    video_id: str,
    status: str,
    stage: str,
    progress: int,
    message: str,
    error: str | None = None,
    filename: str | None = None,
) -> None:
    value = {
        "video_id": video_id,
        "status": status,
        "stage": stage,
        "progress": progress,
        "message": message,
        "updated_at": utc_now(),
    }

    if filename:
        value["filename"] = filename

    if error:
        value["error"] = error

    write_json_atomic(
        status_path,
        value,
    )

    print(
        f"[{progress:3d}%] {stage}: {message}"
    )


def validate_source_identity(
    video_path: Path,
    artifact_directory: Path,
    video_id: str,
) -> dict:
    manifest_path = (
        artifact_directory
        / "source_manifest.json"
    )

    source_hash = calculate_sha256(
        video_path
    )

    source_manifest = {
        "video_id": video_id,
        "source_path": str(
            video_path.resolve()
        ),
        "source_filename": video_path.name,
        "source_size_bytes": (
            video_path.stat().st_size
        ),
        "source_sha256": source_hash,
    }

    if manifest_path.is_file():
        existing = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        if (
            existing.get("source_sha256")
            != source_hash
        ):
            raise ValueError(
                f"Video ID {video_id!r} is already "
                "associated with a different source file. "
                "Use a new video ID to avoid mixing cached "
                "frames and transcripts."
            )

    write_json_atomic(
        manifest_path,
        source_manifest,
    )

    return source_manifest


def process_video(
    video_path: Path,
    video_id: str,
    tenant_id: str,
    artifacts_root: Path,
    frame_interval: float,
    max_frames: int,
    visual_batch_size: int,
    image_detail: str,
    locale: str,
) -> dict:
    video_path = video_path.resolve()

    if not video_path.is_file():
        raise FileNotFoundError(
            f"Video not found: {video_path}"
        )

    source_filename = video_path.name

    artifact_directory = (
        artifacts_root.resolve() / video_id
    )
    artifact_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    status_path = (
        artifact_directory
        / "processing_status.json"
    )

    write_status(
        status_path=status_path,
        video_id=video_id,
        status="processing",
        stage="validating",
        progress=5,
        message="Validating source video.",
        filename=source_filename,
    )

    validate_source_identity(
        video_path=video_path,
        artifact_directory=artifact_directory,
        video_id=video_id,
    )

    try:
        write_status(
            status_path=status_path,
            video_id=video_id,
            status="processing",
            stage="extracting_frames",
            progress=15,
            message="Extracting timestamped frames.",
            filename=source_filename,
        )

        video_info, frames = extract_frames(
            video_path=video_path,
            output_directory=artifact_directory,
            interval_seconds=frame_interval,
            max_frames=max_frames,
        )

        write_status(
            status_path=status_path,
            video_id=video_id,
            status="processing",
            stage="transcribing",
            progress=30,
            message=(
                "Transcribing audio with Azure Speech."
                if video_info.has_audio
                else "Video has no audio; skipping transcription."
            ),
            filename=source_filename,
        )

        transcript = transcribe_video(
            video_path=video_path,
            output_directory=artifact_directory,
            locale=locale,
        )

        write_status(
            status_path=status_path,
            video_id=video_id,
            status="processing",
            stage="describing_frames",
            progress=50,
            message=(
                "Generating visual descriptions "
                "with GPT-5.4."
            ),
            filename=source_filename,
        )

        visual_descriptions_path = (
            artifact_directory
            / "visual_descriptions.json"
        )

        visual_result = describe_frame_batches(
            manifest_path=(
                artifact_directory
                / "frame_manifest.json"
            ),
            output_path=(
                visual_descriptions_path
            ),
            batch_size=visual_batch_size,
            image_detail=image_detail,
        )

        write_status(
            status_path=status_path,
            video_id=video_id,
            status="processing",
            stage="building_timeline",
            progress=70,
            message=(
                "Combining transcript and "
                "visual evidence."
            ),
            filename=source_filename,
        )

        timeline_path = (
            artifact_directory
            / "timeline_chunks.json"
        )

        timeline_result = build_timeline(
            visual_descriptions_path=(
                visual_descriptions_path
            ),
            transcript_path=(
                artifact_directory
                / "transcript.json"
            ),
            output_path=timeline_path,
            markdown_output_path=(
                artifact_directory
                / "timeline.md"
            ),
            tenant_id=tenant_id,
            video_id=video_id,
        )

        write_status(
            status_path=status_path,
            video_id=video_id,
            status="processing",
            stage="publishing",
            progress=85,
            message=(
                "Uploading artifacts and "
                "indexing timeline chunks."
            ),
            filename=source_filename,
        )

        publish_result = publish_video(
            video_path=video_path,
            artifact_directory=(
                artifact_directory
            ),
            timeline_path=timeline_path,
        )

        result = {
            "video_id": video_id,
            "tenant_id": tenant_id,
            "source_video": str(video_path),
            "artifact_directory": str(
                artifact_directory
            ),
            "duration_seconds": (
                video_info.duration_seconds
            ),
            "has_audio": (
                video_info.has_audio
            ),
            "frame_count": len(frames),
            "transcript_status": (
                transcript["status"]
            ),
            "transcript_segment_count": len(
                transcript["segments"]
            ),
            "visual_description_count": len(
                visual_result["descriptions"]
            ),
            "timeline_chunk_count": (
                timeline_result["chunk_count"]
            ),
            "search_document_count": (
                publish_result[
                    "search_document_count"
                ]
            ),
            "status": "ready",
            "completed_at": utc_now(),
        }

        write_json_atomic(
            artifact_directory
            / "processing_result.json",
            result,
        )

        write_status(
            status_path=status_path,
            video_id=video_id,
            status="ready",
            stage="completed",
            progress=100,
            message=(
                "Video processing completed "
                "successfully."
            ),
            filename=source_filename,
        )

        return result

    except Exception as error:
        write_status(
            status_path=status_path,
            video_id=video_id,
            status="failed",
            stage="failed",
            progress=100,
            message="Video processing failed.",
            error=str(error),
            filename=source_filename,
        )

        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Process and index a video end-to-end."
        )
    )
    parser.add_argument(
        "--video",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--video-id",
        required=True,
    )
    parser.add_argument(
        "--tenant-id",
        default="dev-user",
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts"),
    )
    parser.add_argument(
        "--frame-interval",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=120,
    )
    parser.add_argument(
        "--visual-batch-size",
        type=int,
        default=6,
    )
    parser.add_argument(
        "--detail",
        choices=["low", "high", "auto"],
        default="low",
    )
    parser.add_argument(
        "--locale",
        default="en-US",
    )

    arguments = parser.parse_args()

    result = process_video(
        video_path=arguments.video,
        video_id=arguments.video_id,
        tenant_id=arguments.tenant_id,
        artifacts_root=arguments.artifacts_root,
        frame_interval=arguments.frame_interval,
        max_frames=arguments.max_frames,
        visual_batch_size=(
            arguments.visual_batch_size
        ),
        image_detail=arguments.detail,
        locale=arguments.locale,
    )

    print("\nProcessing result:\n")
    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()