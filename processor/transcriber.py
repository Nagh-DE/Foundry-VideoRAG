from __future__ import annotations

import argparse
import json
from pathlib import Path

import av
import requests
from azure.identity import DefaultAzureCredential

from processor.settings import load_settings
from processor.video_probe import probe_video


MAX_FAST_TRANSCRIPTION_BYTES = 500 * 1024 * 1024


def extract_audio(
    video_path: Path,
    audio_path: Path,
) -> Path:
    video_path = video_path.resolve()
    audio_path = audio_path.resolve()

    if (
        audio_path.is_file()
        and audio_path.stat().st_size > 44
        and audio_path.stat().st_mtime
        >= video_path.stat().st_mtime
    ):
        print(f"Using cached audio: {audio_path}")
        return audio_path

    audio_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = audio_path.with_name(
        f"{audio_path.stem}.tmp{audio_path.suffix}"
    )
    temporary_path.unlink(missing_ok=True)

    print("Extracting mono 16 kHz WAV audio...")

    try:
        with av.open(str(video_path)) as input_container:
            audio_stream = next(
                (
                    stream
                    for stream in input_container.streams
                    if stream.type == "audio"
                ),
                None,
            )

            if audio_stream is None:
                raise ValueError(
                    f"No audio stream found in {video_path}"
                )

            resampler = av.AudioResampler(
                format="s16",
                layout="mono",
                rate=16_000,
            )

            with av.open(
                str(temporary_path),
                mode="w",
                format="wav",
            ) as output_container:
                output_stream = output_container.add_stream(
                    "pcm_s16le",
                    rate=16_000,
                )
                output_stream.layout = "mono"

                for frame in input_container.decode(audio_stream):
                    for resampled_frame in resampler.resample(
                        frame
                    ):
                        for packet in output_stream.encode(
                            resampled_frame
                        ):
                            output_container.mux(packet)

                for resampled_frame in resampler.resample(None):
                    for packet in output_stream.encode(
                        resampled_frame
                    ):
                        output_container.mux(packet)

                for packet in output_stream.encode(None):
                    output_container.mux(packet)

        temporary_path.replace(audio_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    if audio_path.stat().st_size <= 44:
        raise RuntimeError(
            "Audio extraction produced an empty WAV file."
        )

    return audio_path


def parse_speech_response(
    payload: dict,
    locale: str,
) -> dict:
    phrases = payload.get("phrases")

    if not isinstance(phrases, list):
        raise RuntimeError(
            "Azure Speech response did not contain a phrases list."
        )

    segments = []
    detected_languages = set()

    for phrase in phrases:
        text = str(phrase.get("text", "")).strip()

        if not text:
            continue

        offset_ms = phrase.get("offsetMilliseconds")
        duration_ms = phrase.get("durationMilliseconds")

        if not isinstance(offset_ms, (int, float)):
            raise RuntimeError(
                "Azure Speech returned a phrase without "
                "offsetMilliseconds."
            )

        if not isinstance(duration_ms, (int, float)):
            raise RuntimeError(
                "Azure Speech returned a phrase without "
                "durationMilliseconds."
            )

        segment = {
            "start_ms": round(offset_ms),
            "end_ms": round(offset_ms + duration_ms),
            "start_seconds": round(
                offset_ms / 1000,
                3,
            ),
            "end_seconds": round(
                (offset_ms + duration_ms) / 1000,
                3,
            ),
            "text": text,
        }

        if phrase.get("locale"):
            segment["locale"] = phrase["locale"]
            detected_languages.add(phrase["locale"])

        if phrase.get("speaker") is not None:
            segment["speaker"] = phrase["speaker"]

        segments.append(segment)

    combined_text = " ".join(
        str(item.get("text", "")).strip()
        for item in payload.get("combinedPhrases", [])
        if str(item.get("text", "")).strip()
    )

    if not combined_text:
        combined_text = " ".join(
            segment["text"]
            for segment in segments
        )

    return {
        "provider": "azure-speech-fast-transcription",
        "locale_requested": locale,
        "languages_detected": sorted(
            detected_languages
        ),
        "duration_ms": payload.get(
            "durationMilliseconds"
        ),
        "text": combined_text,
        "segments": segments,
        "status": (
            "completed"
            if segments
            else "no_speech_detected"
        ),
    }


def transcribe_video(
    video_path: Path,
    output_directory: Path,
    locale: str = "en-US",
) -> dict:
    settings = load_settings()
    video_path = video_path.resolve()
    output_directory = output_directory.resolve()

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    transcript_path = (
        output_directory / "transcript.json"
    )
    raw_response_path = (
        output_directory / "speech_response.json"
    )
    audio_path = (
        output_directory / "audio_16khz_mono.wav"
    )

    video_info = probe_video(video_path)

    if not video_info.has_audio:
        result = {
            "provider": "azure-speech-fast-transcription",
            "locale_requested": locale,
            "languages_detected": [],
            "duration_ms": None,
            "text": "",
            "segments": [],
            "status": "skipped_no_audio",
        }

        transcript_path.write_text(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        print(
            "Video has no audio stream; "
            "transcription was skipped."
        )
        return result

    if (
        transcript_path.is_file()
        and transcript_path.stat().st_mtime
        >= video_path.stat().st_mtime
    ):
        cached = json.loads(
            transcript_path.read_text(
                encoding="utf-8"
            )
        )

        if (
            cached.get("provider")
            == "azure-speech-fast-transcription"
            and cached.get("locale_requested") == locale
        ):
            print(
                f"Using cached transcript: "
                f"{transcript_path}"
            )
            return cached

    audio_path = extract_audio(
        video_path=video_path,
        audio_path=audio_path,
    )

    if audio_path.stat().st_size >= (
        MAX_FAST_TRANSCRIPTION_BYTES
    ):
        raise ValueError(
            "Extracted audio is 500 MB or larger. "
            "Use Azure Speech batch transcription."
        )

    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False
    )
    access_token = credential.get_token(
        "https://cognitiveservices.azure.com/.default"
    )

    endpoint = settings.speech_endpoint.rstrip("/")
    url = (
        f"{endpoint}/speechtotext/"
        "transcriptions:transcribe"
    )

    definition = {
        "locales": [locale],
    }

    print(
        "Sending audio to Azure Speech "
        "Fast Transcription..."
    )

    with audio_path.open("rb") as audio_file:
        response = requests.post(
            url,
            params={
                "api-version": (
                    settings.speech_api_version
                )
            },
            headers={
                "Authorization": (
                    f"Bearer {access_token.token}"
                )
            },
            files={
                "audio": (
                    audio_path.name,
                    audio_file,
                    "audio/wav",
                )
            },
            data={
                "definition": json.dumps(definition)
            },
            timeout=(30, 1800),
        )

    if not response.ok:
        request_id = (
            response.headers.get("apim-request-id")
            or response.headers.get("x-ms-request-id")
            or "not provided"
        )

        raise RuntimeError(
            "Azure Speech transcription failed. "
            f"HTTP status: {response.status_code}. "
            f"Request ID: {request_id}. "
            f"Response: {response.text[:2000]}"
        )

    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise RuntimeError(
            "Azure Speech returned a non-JSON response."
        ) from exc

    raw_response_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    transcript = parse_speech_response(
        payload=payload,
        locale=locale,
    )

    transcript_path.write_text(
        json.dumps(
            transcript,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return transcript


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Transcribe video audio with Azure Speech."
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
        "--locale",
        default="en-US",
    )

    arguments = parser.parse_args()

    transcript = transcribe_video(
        video_path=arguments.video,
        output_directory=arguments.output,
        locale=arguments.locale,
    )

    print(f"Status: {transcript['status']}")
    print(
        f"Transcript segments: "
        f"{len(transcript['segments'])}"
    )
    print(
        f"Transcript: "
        f"{(arguments.output / 'transcript.json').resolve()}"
    )

    if transcript["text"]:
        preview = transcript["text"][:500]
        print(f"\nPreview:\n{preview}")


if __name__ == "__main__":
    main()