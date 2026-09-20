from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import av


@dataclass(frozen=True)
class VideoInfo:
    path: str
    duration_seconds: float
    width: int
    height: int
    fps: float | None
    frame_count: int | None
    codec: str | None
    has_audio: bool

    def to_dict(self) -> dict:
        return asdict(self)


def probe_video(video_path: Path) -> VideoInfo:
    video_path = video_path.resolve()

    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    with av.open(str(video_path)) as container:
        video_stream = next(
            (
                stream
                for stream in container.streams
                if stream.type == "video"
            ),
            None,
        )

        if video_stream is None:
            raise ValueError(
                f"No video stream was found in {video_path}"
            )

        stream_duration = None
        if (
            video_stream.duration is not None
            and video_stream.time_base is not None
        ):
            stream_duration = (
                float(video_stream.duration)
                * float(video_stream.time_base)
            )

        container_duration = None
        if container.duration is not None:
            container_duration = float(container.duration) / 1_000_000

        duration_seconds = (
            stream_duration
            if stream_duration and stream_duration > 0
            else container_duration
        )

        if duration_seconds is None or duration_seconds <= 0:
            raise ValueError(
                "The video does not contain valid duration metadata."
            )

        fps = None
        if video_stream.average_rate is not None:
            fps = float(video_stream.average_rate)

        frame_count = (
            int(video_stream.frames)
            if video_stream.frames
            else None
        )

        codec = None
        if video_stream.codec_context is not None:
            codec = video_stream.codec_context.name

        has_audio = any(
            stream.type == "audio"
            for stream in container.streams
        )

        return VideoInfo(
            path=str(video_path),
            duration_seconds=duration_seconds,
            width=int(video_stream.width),
            height=int(video_stream.height),
            fps=fps,
            frame_count=frame_count,
            codec=codec,
            has_audio=has_audio,
        )