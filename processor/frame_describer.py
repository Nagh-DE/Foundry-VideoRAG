from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Iterator

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from pydantic import BaseModel, Field

from processor.settings import load_settings


class VisualDescription(BaseModel):
    summary: str = Field(
        description=(
            "A concise description of what happens "
            "across the ordered video frames."
        )
    )
    visible_text: list[str] = Field(
        description=(
            "Important text visibly readable in the frames."
        )
    )
    objects: list[str] = Field(
        description=(
            "Important objects, interfaces, diagrams, "
            "documents, or visual elements."
        )
    )
    actions: list[str] = Field(
        description=(
            "Actions or state changes visible across "
            "the ordered frames."
        )
    )
    important_details: list[str] = Field(
        description=(
            "Other visually grounded details that might "
            "help answer future questions."
        )
    )


def batched(
    items: list[dict],
    batch_size: int,
) -> Iterator[list[dict]]:
    if batch_size <= 0:
        raise ValueError(
            "batch_size must be greater than zero."
        )

    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def image_as_data_url(image_path: Path) -> str:
    if not image_path.is_file():
        raise FileNotFoundError(
            f"Frame image not found: {image_path}"
        )

    encoded = base64.b64encode(
        image_path.read_bytes()
    ).decode("ascii")

    return f"data:image/jpeg;base64,{encoded}"


def load_frame_manifest(
    manifest_path: Path,
) -> dict:
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Frame manifest not found: {manifest_path}"
        )

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    frames = manifest.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError(
            "Frame manifest contains no frames."
        )

    return manifest


def describe_frame_batches(
    manifest_path: Path,
    output_path: Path,
    batch_size: int = 6,
    image_detail: str = "low",
) -> dict:
    if image_detail not in {"low", "high", "auto"}:
        raise ValueError(
            "image_detail must be low, high, or auto."
        )

    settings = load_settings()
    manifest = load_frame_manifest(manifest_path)

    frames = manifest["frames"]
    video = manifest["video"]

    cache_settings = {
        "model": settings.gpt_deployment_name,
        "batch_size": batch_size,
        "image_detail": image_detail,
    }

    if (
        output_path.is_file()
        and output_path.stat().st_mtime
        >= manifest_path.stat().st_mtime
    ):
        cached = json.loads(
            output_path.read_text(encoding="utf-8")
        )

        if cached.get("settings") == cache_settings:
            print(
                f"Using cached visual descriptions: "
                f"{output_path}"
            )
            return cached

    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False
    )

    # Use Azure OpenAI directly (not the Foundry project proxy) so that
    # chat.completions is available with the managed identity's RBAC scope.
    token_provider = get_bearer_token_provider(
        credential,
        "https://cognitiveservices.azure.com/.default",
    )
    # Base URL format: https://<account>.openai.azure.com/openai/v1/
    # Strip trailing slash for AzureOpenAI azure_endpoint parameter.
    openai_base = settings.openai_base_url.rstrip("/")
    if openai_base.endswith("/v1"):
        azure_endpoint = openai_base[: -len("/openai/v1")]
    elif openai_base.endswith("/openai"):
        azure_endpoint = openai_base[: -len("/openai")]
    else:
        azure_endpoint = openai_base

    openai_client = AzureOpenAI(
        azure_endpoint=azure_endpoint,
        azure_ad_token_provider=token_provider,
        api_version="2025-01-01-preview",
    )

    frame_batches = list(
        batched(frames, batch_size)
    )
    descriptions = []

    for batch_index, frame_batch in enumerate(
        frame_batches
    ):
        first_frame = frame_batch[0]

        start_seconds = float(
            first_frame["timestamp_seconds"]
        )

        next_batch_index = (
            (batch_index + 1) * batch_size
        )

        if next_batch_index < len(frames):
            end_seconds = float(
                frames[next_batch_index][
                    "timestamp_seconds"
                ]
            )
        else:
            end_seconds = float(
                video["duration_seconds"]
            )

        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    "Analyze these ordered frames from one "
                    "video timeline segment.\n\n"
                    "Describe only what is visibly supported. "
                    "Identify important readable text, objects, "
                    "screens, slides, diagrams, and actions or "
                    "state changes across frames.\n\n"
                    "Do not invent names, dialogue, events, or "
                    "details that aren't visually present. "
                    "If text is not readable, do not guess it. "
                    "Use empty lists when a category has no "
                    "supported evidence."
                ),
            }
        ]

        for frame in frame_batch:
            timestamp = frame["timestamp"]
            image_path = Path(frame["path"])

            content.append(
                {
                    "type": "text",
                    "text": (
                        f"Video frame at [{timestamp}]"
                    ),
                }
            )

            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_as_data_url(image_path),
                        "detail": image_detail,
                    },
                }
            )

        print(
            "Describing frame batch "
            f"{batch_index + 1} of "
            f"{len(frame_batches)}..."
        )

        response = openai_client.beta.chat.completions.parse(
            model=settings.gpt_deployment_name,
            messages=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
            response_format=VisualDescription,
            max_completion_tokens=1200,
        )

        parsed = response.choices[0].message.parsed

        if parsed is None:
            raw = response.choices[0].message.content or ""
            raise RuntimeError(
                "GPT-5.4 did not return a valid "
                "structured visual description. "
                f"Raw output: {raw}"
            )

        descriptions.append(
            {
                "scene_id": (
                    f"scene-{batch_index:04d}"
                ),
                "start_ms": round(
                    start_seconds * 1000
                ),
                "end_ms": round(
                    end_seconds * 1000
                ),
                "start_seconds": round(
                    start_seconds,
                    3,
                ),
                "end_seconds": round(
                    end_seconds,
                    3,
                ),
                "summary": parsed.summary,
                "visible_text": parsed.visible_text,
                "objects": parsed.objects,
                "actions": parsed.actions,
                "important_details": (
                    parsed.important_details
                ),
                "frames": [
                    {
                        "index": frame["index"],
                        "timestamp": frame["timestamp"],
                        "timestamp_seconds": (
                            frame["timestamp_seconds"]
                        ),
                        "path": frame["path"],
                    }
                    for frame in frame_batch
                ],
            }
        )

    result = {
        "provider": "gpt-5.4-vision",
        "model": settings.gpt_deployment_name,
        "settings": cache_settings,
        "video": video,
        "descriptions": descriptions,
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

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate structured descriptions of "
            "timestamped video frames."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=6,
    )
    parser.add_argument(
        "--detail",
        choices=["low", "high", "auto"],
        default="low",
    )

    arguments = parser.parse_args()

    result = describe_frame_batches(
        manifest_path=arguments.manifest,
        output_path=arguments.output,
        batch_size=arguments.batch_size,
        image_detail=arguments.detail,
    )

    print(
        f"Visual descriptions: "
        f"{len(result['descriptions'])}"
    )
    print(
        f"Output: {arguments.output.resolve()}"
    )


if __name__ == "__main__":
    main()