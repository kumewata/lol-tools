"""Local video processing: audio extraction, transcription, and screenshots."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from google import genai
from PIL import Image

from lol_vod_analyzer.models import SceneSnapshot, TranscriptSegment, VideoSource
from lol_vod_analyzer.momentum import important_time_windows
from lol_vod_analyzer.system_tools import format_missing_tools_message

logger = logging.getLogger(__name__)

DEFAULT_MAX_SCREENSHOTS = 24
DEFAULT_EARLY_GAME_WINDOW_SECONDS = 180
DEFAULT_EARLY_GAME_RESERVED = 6
DEFAULT_MOMENTUM_RESERVED = 12


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


def _compute_scene_activity(
    video_path: Path,
    sample_interval: float = 2.0,
) -> list[tuple[float, float]]:
    """Scan the video and return an activity profile.

    Returns a list of ``(timestamp_sec, activity_score)`` pairs sampled at
    *sample_interval* seconds.  The activity score is ``1 - correlation``
    between consecutive grey-scale histograms (higher = more change).
    """
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        return []

    frame_step = max(1, int(fps * sample_interval))
    profile: list[tuple[float, float]] = []
    prev_hist = None
    frame_no = 0

    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        if not ret:
            break

        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([grey], [0], None, [256], [0, 256])
        cv2.normalize(hist, hist)

        ts = frame_no / fps
        if prev_hist is not None:
            corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            activity = 1.0 - max(corr, 0.0)
        else:
            activity = 0.0

        profile.append((ts, activity))
        prev_hist = hist
        frame_no += frame_step

    cap.release()
    return profile


def _adaptive_timestamps(
    activity_profile: list[tuple[float, float]],
    base_interval: float,
    max_frames: int,
) -> list[float]:
    """Compute adaptive sample timestamps from an activity profile.

    High-activity regions are sampled at ``base_interval / 3`` and
    low-activity regions at ``base_interval * 2``.  If the resulting
    set exceeds *max_frames*, frames with the lowest activity are
    dropped first.
    """
    if not activity_profile:
        return []

    scores = [score for _, score in activity_profile]
    threshold = sum(scores) / len(scores)

    timestamps: list[tuple[float, float]] = []  # (timestamp, activity)
    last_ts = -float("inf")

    for ts, score in activity_profile:
        if score > threshold:
            min_gap = base_interval / 3
        else:
            min_gap = base_interval * 2

        if ts - last_ts >= min_gap:
            timestamps.append((ts, score))
            last_ts = ts

    # Enforce max_frames by dropping lowest-activity entries first
    if len(timestamps) > max_frames:
        timestamps.sort(key=lambda x: x[1], reverse=True)
        timestamps = timestamps[:max_frames]
        timestamps.sort(key=lambda x: x[0])

    return [ts for ts, _ in timestamps]


def _fixed_interval_timestamps(
    duration_sec: float,
    interval_seconds: int,
    *,
    start_sec: float = 0.0,
) -> list[float]:
    if duration_sec <= 0 or interval_seconds <= 0 or start_sec >= duration_sec:
        return []

    timestamps: list[float] = []
    current = max(0.0, start_sec)
    while current < duration_sec:
        timestamps.append(current)
        current += interval_seconds
    return timestamps


def _evenly_spaced_timestamps(
    start_sec: float,
    end_sec: float,
    count: int,
) -> list[float]:
    if count <= 0 or end_sec <= start_sec:
        return []
    if count == 1:
        return [start_sec]

    span = end_sec - start_sec
    step = span / (count - 1)
    return [start_sec + step * i for i in range(count)]


def _merge_unique_timestamps(
    *timestamp_groups: list[float],
    limit: int,
) -> list[float]:
    seen: set[int] = set()
    merged: list[float] = []

    for group in timestamp_groups:
        for ts in group:
            key = int(round(ts * 1000))
            if key in seen:
                continue
            seen.add(key)
            merged.append(ts)
            if len(merged) >= limit:
                return sorted(merged)

    return sorted(merged)


def _momentum_candidate_timestamps(
    match_context: dict | None,
    *,
    game_start_offset: int,
    max_count: int,
) -> list[float]:
    if max_count <= 0 or not match_context:
        return []

    windows = important_time_windows(match_context)
    if not windows:
        return []
    if len(windows) > max_count:
        step = len(windows) / max_count
        windows = [windows[int(step * i)] for i in range(max_count)]

    candidates: list[float] = []
    windows_per_count = max(1, len(windows))
    base_count = max_count // windows_per_count
    remainder = max_count % windows_per_count

    for index, (start_sec, end_sec) in enumerate(windows):
        count = max(1, base_count + (1 if index < remainder else 0))
        window_start = game_start_offset + start_sec
        window_end = game_start_offset + end_sec
        candidates.extend(_evenly_spaced_timestamps(window_start, window_end, count))

    return candidates


def _early_game_timestamps(
    duration_sec: float,
    *,
    game_start_offset: int,
    reserved_count: int,
    early_game_window_seconds: int,
) -> list[float]:
    if reserved_count <= 0:
        return []

    start_sec = min(max(0, game_start_offset), duration_sec)
    end_sec = min(duration_sec, start_sec + early_game_window_seconds)
    return _evenly_spaced_timestamps(start_sec, end_sec, reserved_count)


def _build_sampling_timestamps(
    *,
    duration_sec: float,
    interval_seconds: int,
    max_screenshots: int,
    adaptive: bool,
    activity_profile: list[tuple[float, float]] | None = None,
    match_context: dict | None = None,
    game_start_offset: int = 0,
    early_game_window_seconds: int = DEFAULT_EARLY_GAME_WINDOW_SECONDS,
    early_game_reserved: int = DEFAULT_EARLY_GAME_RESERVED,
    momentum_reserved: int = DEFAULT_MOMENTUM_RESERVED,
) -> list[float]:
    if duration_sec <= 0 or max_screenshots <= 0:
        return []

    has_gameplay_context = match_context is not None or game_start_offset > 0
    early_budget = min(max_screenshots, early_game_reserved) if has_gameplay_context else 0
    momentum_budget = (
        min(max(0, max_screenshots - early_budget), momentum_reserved)
        if match_context
        else 0
    )

    early_candidates = _early_game_timestamps(
        duration_sec,
        game_start_offset=game_start_offset,
        reserved_count=early_budget,
        early_game_window_seconds=early_game_window_seconds,
    )
    momentum_candidates = _momentum_candidate_timestamps(
        match_context,
        game_start_offset=game_start_offset,
        max_count=momentum_budget,
    )

    remaining = max_screenshots - len(
        _merge_unique_timestamps(
            early_candidates,
            momentum_candidates,
            limit=max_screenshots,
        )
    )

    if adaptive and activity_profile:
        adaptive_candidates = _adaptive_timestamps(
            activity_profile,
            float(interval_seconds),
            max(max_screenshots, remaining),
        )
        backfill_candidates = [
            ts for ts in adaptive_candidates if ts >= max(0, game_start_offset)
        ]
    else:
        backfill_candidates = _fixed_interval_timestamps(
            duration_sec,
            interval_seconds,
            start_sec=max(0, game_start_offset),
        )

    return _merge_unique_timestamps(
        early_candidates,
        momentum_candidates,
        backfill_candidates,
        limit=max_screenshots,
    )


def extract_screenshots(
    video_path: Path,
    output_dir: Path,
    interval_seconds: int = 10,
    *,
    adaptive: bool = False,
    speed: float = 1.0,
    max_screenshots: int = DEFAULT_MAX_SCREENSHOTS,
    match_context: dict | None = None,
    game_start_offset: int = 0,
) -> list[SceneSnapshot]:
    """Extract screenshots from video using OpenCV.

    When *adaptive* is ``True``, a two-pass approach is used: first
    the video is scanned for scene-activity, then frames are sampled
    more densely during high-activity periods and less densely during
    low-activity periods.

    *speed* is a playback speed multiplier (e.g. 2.0 for a replay
    recorded at 2x speed).  All ``timestamp_ms`` values in the
    returned snapshots are scaled by this factor so they correspond
    to real game time rather than video time.
    """
    import cv2

    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps

    activity_profile: list[tuple[float, float]] = []
    if adaptive and duration_sec > 0:
        cap.release()
        activity_profile = _compute_scene_activity(video_path)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []

    sample_timestamps = _build_sampling_timestamps(
        duration_sec=duration_sec,
        interval_seconds=interval_seconds,
        max_screenshots=max_screenshots,
        adaptive=adaptive,
        activity_profile=activity_profile,
        match_context=match_context,
        game_start_offset=game_start_offset,
    )
    logger.info("planned screenshots: %d timestamps", len(sample_timestamps))

    snapshots: list[SceneSnapshot] = []
    for i, ts in enumerate(sample_timestamps):
        target_frame = max(0, min(int(ts * fps), max(total_frames - 1, 0)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        if not ret:
            continue

        game_time_ms = int((target_frame / fps) * 1000 * speed)
        frame_path = output_dir / f"screenshot_{i:04d}_{game_time_ms // 1000}s.jpg"
        cv2.imwrite(str(frame_path), frame)
        snapshots.append(
            SceneSnapshot(timestamp_ms=game_time_ms, image_path=frame_path)
        )

    cap.release()
    return snapshots
