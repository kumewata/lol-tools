"""Local video processing: audio extraction, transcription, and screenshots."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from google import genai
from PIL import Image

from lol_vod_analyzer.models import SceneSnapshot, TranscriptSegment, VideoSource
from lol_vod_analyzer.system_tools import format_missing_tools_message


def get_video_metadata(video_path: Path) -> VideoSource:
    """Extract metadata from a local video file using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", str(video_path),
            ],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            format_missing_tools_message(["ffprobe"], "ローカル動画のメタデータ取得")
        ) from exc
    info = json.loads(result.stdout)
    duration = int(float(info["format"]["duration"]))
    return VideoSource(
        local_path=video_path,
        title=video_path.stem,
        duration=duration,
        source_type="local",
    )


def extract_audio(video_path: Path, output_dir: Path) -> Path | None:
    """Extract audio from video using ffmpeg as m4a.

    Returns None if the video has no audio stream.
    """
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    safe_stem = Path(video_path.name).stem  # strip directory components
    audio_path = output_dir / f"{safe_stem}.m4a"
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", str(video_path),
                "-vn", "-acodec", "aac", "-y",
                str(audio_path),
            ],
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            format_missing_tools_message(["ffmpeg"], "ローカル動画からの音声抽出")
        ) from exc
    if result.returncode != 0:
        return None
    return audio_path


def transcribe_audio(
    audio_path: Path, api_key: str | None = None
) -> list[TranscriptSegment]:
    """Transcribe audio using Gemini API.

    Sends the audio file to Gemini and asks for timestamped transcription.
    """
    if api_key is None:
        api_key = os.environ.get("GOOGLE_API_KEY", "")

    client = genai.Client(api_key=api_key)

    # Upload the audio file
    uploaded = client.files.upload(file=audio_path)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            uploaded,
            "この音声を文字起こししてください。"
            "以下のJSON形式で、発話ごとにタイムスタンプ付きで出力してください。"
            "JSONのみを出力し、他のテキストは含めないでください。\n"
            '{"segments": [{"start_ms": <開始ミリ秒>, "end_ms": <終了ミリ秒>, "text": "<発話テキスト>"}]}',
        ],
    )

    try:
        text = response.text.strip()
        # Handle markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```") and not in_block:
                    in_block = True
                    continue
                if line.strip() == "```" and in_block:
                    break
                if in_block:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        data = json.loads(text)
        segments = []
        for seg in data.get("segments", []):
            s = TranscriptSegment(
                start_ms=seg["start_ms"],
                end_ms=seg["end_ms"],
                text=seg["text"],
            )
            segments.append(s)
        return segments
    except (json.JSONDecodeError, KeyError, TypeError):
        # If JSON parsing fails, create a single segment from the raw text
        return [
            TranscriptSegment(start_ms=0, end_ms=0, text=response.text.strip())
        ] if response.text.strip() else []


def extract_screenshots(
    video_path: Path,
    output_dir: Path,
    interval_seconds: int = 10,
) -> list[SceneSnapshot]:
    """Extract screenshots from video at regular intervals using OpenCV."""
    import cv2

    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_ms = int((total_frames / fps) * 1000) if fps > 0 else 0

    snapshots: list[SceneSnapshot] = []
    frame_interval = int(fps * interval_seconds)
    frame_index = 0

    while True:
        target_frame = frame_index * frame_interval
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        if not ret:
            break

        timestamp_ms = int((target_frame / fps) * 1000)
        frame_path = output_dir / f"screenshot_{frame_index:04d}_{timestamp_ms // 1000}s.jpg"
        cv2.imwrite(str(frame_path), frame)

        snapshots.append(
            SceneSnapshot(timestamp_ms=timestamp_ms, image_path=frame_path)
        )
        frame_index += 1

    cap.release()
    return snapshots
