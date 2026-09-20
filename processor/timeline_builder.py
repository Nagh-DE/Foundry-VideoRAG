from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def format_timestamp(milliseconds: int) -> str:
    total_seconds = max(
        0,
        round(milliseconds / 1000),
    )
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    return json.loads(
        path.read_text(encoding="utf-8")
    )


def load_transcript(
    transcript_path: Path | None,
) -> dict:
    if transcript_path is None:
        return {
            "status": "not_provided",
            "text": "",
            "segments": [],
        }

    if not transcript_path.is_file():
        return {
            "status": "not_found",
            "text": "",
            "segments": [],
        }

    transcript = load_json(transcript_path)

    if not isinstance(
        transcript.get("segments"),
        list,
    ):
        raise ValueError(
            "Transcript does not contain a segments list."
        )

    return transcript


def transcript_for_window(
    segments: list[dict],
    start_ms: int,
    end_ms: int,
) -> tuple[str, list[dict]]:
    overlapping = []

    for segment in segments:
        segment_start = int(segment["start_ms"])
        segment_end = int(segment["end_ms"])

        if (
            segment_start < end_ms
            and segment_end > start_ms
        ):
            overlapping.append(segment)

    transcript_lines = []

    for segment in overlapping:
        speaker = ""

        if segment.get("speaker") is not None:
            speaker = (
                f"Speaker {segment['speaker']}: "
            )

        transcript_lines.append(
            f"[{format_timestamp(segment['start_ms'])}"
            f"-{format_timestamp(segment['end_ms'])}] "
            f"{speaker}{segment['text']}"
        )

    return "\n".join(transcript_lines), overlapping


def unique_strings(values: list[str]) -> list[str]:
    result = []
    seen = set()

    for value in values:
        cleaned = str(value).strip()

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

    return result


def validate_video_id(video_id: str) -> str:
    if not re.fullmatch(
        r"[A-Za-z0-9_-]+",
        video_id,
    ):
        raise ValueError(
            "video_id may only contain letters, "
            "numbers, underscores, and hyphens."
        )

    return video_id


def create_chunk_title(
    timestamp: str,
    visible_text: list[str],
    summary: str,
) -> str:
    if visible_text:
        title = visible_text[0]
    elif summary:
        title = summary
    else:
        title = f"Video segment {timestamp}"

    return title[:200]


def build_search_content(
    video_name: str,
    timestamp: str,
    transcript: str,
    visual_summary: str,
    visible_text: list[str],
    objects: list[str],
    actions: list[str],
    important_details: list[str],
) -> str:
    sections = [
        f"Video: {video_name}",
        f"Time: {timestamp}",
    ]

    if transcript:
        sections.append(
            f"Transcript:\n{transcript}"
        )

    if visual_summary:
        sections.append(
            f"Visual summary:\n{visual_summary}"
        )

    if visible_text:
        sections.append(
            "Visible text:\n"
            + "\n".join(visible_text)
        )

    if objects:
        sections.append(
            "Objects and visual elements:\n"
            + "\n".join(objects)
        )

    if actions:
        sections.append(
            "Actions and changes:\n"
            + "\n".join(actions)
        )

    if important_details:
        sections.append(
            "Important visual details:\n"
            + "\n".join(important_details)
        )

    return "\n\n".join(sections)


def build_timeline(
    visual_descriptions_path: Path,
    transcript_path: Path | None,
    output_path: Path,
    markdown_output_path: Path,
    tenant_id: str,
    video_id: str,
) -> dict:
    video_id = validate_video_id(video_id)

    visual_data = load_json(
        visual_descriptions_path
    )
    transcript_data = load_transcript(
        transcript_path
    )

    descriptions = visual_data.get(
        "descriptions"
    )

    if not isinstance(descriptions, list):
        raise ValueError(
            "Visual descriptions file does not "
            "contain a descriptions list."
        )

    video = visual_data["video"]
    video_name = Path(video["path"]).name

    chunks = []
    markdown_sections = [
        f"# Video timeline: {video_name}",
        "",
        f"- Video ID: `{video_id}`",
        f"- Tenant ID: `{tenant_id}`",
        f"- Duration: {video['duration_seconds']:.3f} seconds",
        f"- Has audio: {video['has_audio']}",
        f"- Transcript status: {transcript_data['status']}",
        "",
    ]

    transcript_segments = transcript_data[
        "segments"
    ]

    for description in descriptions:
        scene_id = description["scene_id"]
        start_ms = int(description["start_ms"])
        end_ms = int(description["end_ms"])

        timestamp = (
            f"{format_timestamp(start_ms)}"
            f"-{format_timestamp(end_ms)}"
        )

        transcript_text, matching_segments = (
            transcript_for_window(
                segments=transcript_segments,
                start_ms=start_ms,
                end_ms=end_ms,
            )
        )

        visible_text = unique_strings(
            description.get("visible_text", [])
        )
        objects = unique_strings(
            description.get("objects", [])
        )
        actions = unique_strings(
            description.get("actions", [])
        )
        important_details = unique_strings(
            description.get(
                "important_details",
                [],
            )
        )

        visual_summary = str(
            description.get("summary", "")
        ).strip()

        frame_blob_paths = [
            (
                f"frames/{video_id}/"
                f"{Path(frame['path']).name}"
            )
            for frame in description.get(
                "frames",
                [],
            )
        ]

        keywords = unique_strings(
            visible_text
            + objects
            + actions
        )

        content = build_search_content(
            video_name=video_name,
            timestamp=timestamp,
            transcript=transcript_text,
            visual_summary=visual_summary,
            visible_text=visible_text,
            objects=objects,
            actions=actions,
            important_details=important_details,
        )

        chunk = {
            "id": f"{video_id}-{scene_id}",
            "tenant_id": tenant_id,
            "video_id": video_id,
            "video_name": video_name,
            "video_version": "1",
            "evidence_type": "timeline_segment",
            "scene_id": scene_id,
            "chunk_title": create_chunk_title(
                timestamp=timestamp,
                visible_text=visible_text,
                summary=visual_summary,
            ),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "timestamp": timestamp,
            "content": content,
            "transcript": transcript_text,
            "visual_summary": visual_summary,
            "ocr_text": "\n".join(visible_text),
            "keywords": ", ".join(keywords),
            "objects": objects,
            "actions": actions,
            "frame_blob_paths": frame_blob_paths,
            "source_url": (
                f"/videos/{video_id}"
                f"?t={round(start_ms / 1000)}"
            ),
            "is_active": True,
        }

        chunks.append(chunk)

        markdown_sections.extend(
            [
                f"## {timestamp}",
                "",
                f"### {chunk['chunk_title']}",
                "",
            ]
        )

        if transcript_text:
            markdown_sections.extend(
                [
                    "**Transcript**",
                    "",
                    transcript_text,
                    "",
                ]
            )

        if visual_summary:
            markdown_sections.extend(
                [
                    "**Visual summary**",
                    "",
                    visual_summary,
                    "",
                ]
            )

        if visible_text:
            markdown_sections.extend(
                [
                    "**Visible text**",
                    "",
                    *[
                        f"- {item}"
                        for item in visible_text
                    ],
                    "",
                ]
            )

        if actions:
            markdown_sections.extend(
                [
                    "**Actions**",
                    "",
                    *[
                        f"- {item}"
                        for item in actions
                    ],
                    "",
                ]
            )

        if frame_blob_paths:
            markdown_sections.extend(
                [
                    "**Frames**",
                    "",
                    *[
                        f"- `{path}`"
                        for path in frame_blob_paths
                    ],
                    "",
                ]
            )

    result = {
        "video": {
            "tenant_id": tenant_id,
            "video_id": video_id,
            "video_name": video_name,
            "duration_seconds": video[
                "duration_seconds"
            ],
            "has_audio": video["has_audio"],
            "transcript_status": (
                transcript_data["status"]
            ),
        },
        "chunk_count": len(chunks),
        "chunks": chunks,
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    markdown_output_path.write_text(
        "\n".join(markdown_sections),
        encoding="utf-8",
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Combine transcript and visual descriptions "
            "into searchable timeline chunks."
        )
    )
    parser.add_argument(
        "--visual-descriptions",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--transcript",
        type=Path,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
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

    arguments = parser.parse_args()

    result = build_timeline(
        visual_descriptions_path=(
            arguments.visual_descriptions
        ),
        transcript_path=arguments.transcript,
        output_path=arguments.output,
        markdown_output_path=(
            arguments.markdown_output
        ),
        tenant_id=arguments.tenant_id,
        video_id=arguments.video_id,
    )

    print(
        f"Timeline chunks created: "
        f"{result['chunk_count']}"
    )
    print(
        f"JSON output: "
        f"{arguments.output.resolve()}"
    )
    print(
        f"Markdown output: "
        f"{arguments.markdown_output.resolve()}"
    )


if __name__ == "__main__":
    main()