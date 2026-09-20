from __future__ import annotations

import argparse
import json
import math
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2

from processor.video_probe import VideoInfo, probe_video


@dataclass(frozen=True)
class FrameSample:
    index: int
    requested_timestamp_seconds: float
    timestamp_seconds: float
    timestamp: str
    path: str

    def to_dict(self) -> dict:
        return asdict(self)


def format_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def choose_timestamps(
    duration_seconds: float,
    interval_seconds: float,
    max_frames: int,
) -> list[float]:
    if duration_seconds <= 0:
        raise ValueError(
            "duration_seconds must be greater than zero."
        )

    if interval_seconds <= 0:
        raise ValueError(
            "interval_seconds must be greater than zero."
        )

    if max_frames <= 0:
        raise ValueError("max_frames must be greater than zero.")

    requested_count = max(
        1,
        math.ceil(duration_seconds / interval_seconds),
    )

    if requested_count <= max_frames:
        return [
            index * interval_seconds
            for index in range(requested_count)
            if index * interval_seconds < duration_seconds
        ]

    if max_frames == 1:
        return [0.0]

    endpoint_margin = min(
        5.0,
        max(0.5, interval_seconds / 2),
    )
    final_timestamp = max(
        0.0,
        duration_seconds - endpoint_margin,
    )
    step = final_timestamp / (max_frames - 1)

    return [
        index * step
        for index in range(max_frames)
    ]


def resize_frame(frame, max_dimension: int):
    height, width = frame.shape[:2]

    scale = min(
        1.0,
        max_dimension / max(height, width),
    )

    if scale == 1.0:
        return frame

    return cv2.resize(
        frame,
        (
            max(1, round(width * scale)),
            max(1, round(height * scale)),
        ),
        interpolation=cv2.INTER_AREA,
    )


def decode_frame_near_timestamp(
    capture: cv2.VideoCapture,
    timestamp_seconds: float,
    interval_seconds: float,
):
    retry_offsets = (
        0.0,
        0.5,
        1.0,
        2.0,
        min(5.0, interval_seconds / 2),
        interval_seconds,
    )

    attempted = set()

    for offset in retry_offsets:
        candidate = max(
            0.0,
            timestamp_seconds - offset,
        )
        candidate_key = round(candidate, 3)

        if candidate_key in attempted:
            continue

        attempted.add(candidate_key)

        capture.set(
            cv2.CAP_PROP_POS_MSEC,
            candidate * 1000,
        )

        succeeded, frame = capture.read()

        if succeeded and frame is not None:
            return frame, candidate

    return None, None


def extract_frames(
    video_path: Path,
    output_directory: Path,
    interval_seconds: float = 10.0,
    max_frames: int = 120,
    max_dimension: int = 1280,
    jpeg_quality: int = 75,
) -> tuple[VideoInfo, list[FrameSample]]:
    if not 1 <= jpeg_quality <= 100:
        raise ValueError(
            "jpeg_quality must be between 1 and 100."
        )

    video_info = probe_video(video_path)

    timestamps = choose_timestamps(
        duration_seconds=video_info.duration_seconds,
        interval_seconds=interval_seconds,
        max_frames=max_frames,
    )

    frames_directory = output_directory / "frames"
    frames_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    capture = cv2.VideoCapture(str(video_path))

    if not capture.isOpened():
        raise RuntimeError(
            f"OpenCV could not open {video_path}"
        )

    samples: list[FrameSample] = []

    try:
        for requested_timestamp in timestamps:
            frame, actual_timestamp = (
                decode_frame_near_timestamp(
                    capture=capture,
                    timestamp_seconds=requested_timestamp,
                    interval_seconds=interval_seconds,
                )
            )

            if frame is None or actual_timestamp is None:
                warnings.warn(
                    "Skipping undecodable frame near "
                    f"{format_timestamp(requested_timestamp)}.",
                    RuntimeWarning,
                )
                continue

            if abs(actual_timestamp - requested_timestamp) >= 0.001:
                warnings.warn(
                    "Requested frame "
                    f"{format_timestamp(requested_timestamp)} "
                    "was unavailable; using "
                    f"{format_timestamp(actual_timestamp)}.",
                    RuntimeWarning,
                )

            resized = resize_frame(
                frame,
                max_dimension=max_dimension,
            )

            succeeded, encoded = cv2.imencode(
                ".jpg",
                resized,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    jpeg_quality,
                ],
            )

            if not succeeded:
                raise RuntimeError(
                    "Could not encode frame at "
                    f"{format_timestamp(actual_timestamp)}."
                )

            sample_index = len(samples)
            timestamp_ms = round(
                actual_timestamp * 1000
            )

            frame_path = (
                frames_directory
                / (
                    f"frame_{sample_index:04d}_"
                    f"{timestamp_ms:010d}.jpg"
                )
            )

            frame_path.write_bytes(encoded.tobytes())

            samples.append(
                FrameSample(
                    index=sample_index,
                    requested_timestamp_seconds=round(
                        requested_timestamp,
                        3,
                    ),
                    timestamp_seconds=round(
                        actual_timestamp,
                        3,
                    ),
                    timestamp=format_timestamp(
                        actual_timestamp
                    ),
                    path=str(frame_path.resolve()),
                )
            )
    finally:
        capture.release()

    if not samples:
        raise RuntimeError(
            "No frames could be decoded from the video."
        )

    manifest = {
        "video": video_info.to_dict(),
        "extraction": {
            "interval_seconds": interval_seconds,
            "max_frames": max_frames,
            "max_dimension": max_dimension,
            "jpeg_quality": jpeg_quality,
        },
        "frames": [
            sample.to_dict()
            for sample in samples
        ],
    }

    manifest_path = (
        output_directory / "frame_manifest.json"
    )
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return video_info, samples


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Probe a video and extract timestamped frames."
        )
    )
    parser.add_argument(
        "--video",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=120,
    )

    arguments = parser.parse_args()

    video_info, samples = extract_frames(
        video_path=arguments.video,
        output_directory=arguments.output,
        interval_seconds=arguments.interval,
        max_frames=arguments.max_frames,
    )

    print(
        f"Duration: "
        f"{format_timestamp(video_info.duration_seconds)}"
    )
    print(f"Resolution: {video_info.width}x{video_info.height}")
    print(f"Codec: {video_info.codec}")
    print(f"Has audio: {video_info.has_audio}")
    print(f"Frames extracted: {len(samples)}")
    print(
        "Manifest: "
        f"{(arguments.output / 'frame_manifest.json').resolve()}"
    )


if __name__ == "__main__":
    main()