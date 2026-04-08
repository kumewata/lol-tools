"""Local video processing and screenshot planning."""

from __future__ import annotations

import json
import logging
import math
import subprocess
from pathlib import Path

from PIL import Image

from lol_vod_analyzer.models import SceneSnapshot, TranscriptSegment, VideoSource
from lol_vod_analyzer.momentum import important_time_windows
from lol_vod_analyzer.system_tools import format_missing_tools_message

logger = logging.getLogger(__name__)

DEFAULT_MAX_SCREENSHOTS = 24
DEFAULT_EARLY_GAME_WINDOW_SECONDS = 180
DEFAULT_EARLY_GAME_RESERVED = 6
DEFAULT_MOMENTUM_RESERVED = 12
DEFAULT_FOCUS_WINDOW_SECONDS = 45
DEFAULT_FOCUS_BUDGET_RATIO = 0.75
DEFAULT_GLOBAL_BACKFILL = 4
DEFAULT_OBJECTIVE_MERGE_GAP_SECONDS = 30
DEFAULT_MAX_MOMENTUM_WINDOW_SECONDS = 180
DEFAULT_FOCUS_PROFILE = "balanced"
VALID_FOCUS_PROFILES = {"balanced", "lane", "objective", "roam"}
DEFAULT_LANE_PHASE_SECONDS = 12 * 60
DEFAULT_LANE_PHASE_WINDOWS = 3
DEFAULT_ROAM_DISTANCE_THRESHOLD = 3500


def _normalize_speed(speed: float) -> float:
    return speed if speed > 0 else 1.0


def _game_time_to_video_time(timestamp_sec: float, *, speed: float) -> float:
    return timestamp_sec / _normalize_speed(speed)


def _video_time_to_game_time(timestamp_sec: float, *, speed: float) -> float:
    return timestamp_sec * _normalize_speed(speed)


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
    speed: float = 1.0,
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
        window_start = game_start_offset + _game_time_to_video_time(start_sec, speed=speed)
        window_end = game_start_offset + _game_time_to_video_time(end_sec, speed=speed)
        candidates.extend(_evenly_spaced_timestamps(window_start, window_end, count))

    return candidates


def _early_game_timestamps(
    duration_sec: float,
    *,
    game_start_offset: int,
    reserved_count: int,
    early_game_window_seconds: int,
    speed: float = 1.0,
) -> list[float]:
    if reserved_count <= 0:
        return []

    start_sec = min(max(0, game_start_offset), duration_sec)
    end_sec = min(
        duration_sec,
        start_sec + _game_time_to_video_time(early_game_window_seconds, speed=speed),
    )
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
    sampling_strategy: str = "fixed",
    focus_window_seconds: int = DEFAULT_FOCUS_WINDOW_SECONDS,
    focus_budget_ratio: float = DEFAULT_FOCUS_BUDGET_RATIO,
    global_backfill: int = DEFAULT_GLOBAL_BACKFILL,
    focus_profile: str | None = None,
    speed: float = 1.0,
) -> list[float]:
    return _build_sampling_plan(
        duration_sec=duration_sec,
        interval_seconds=interval_seconds,
        max_screenshots=max_screenshots,
        adaptive=adaptive,
        activity_profile=activity_profile,
        match_context=match_context,
        game_start_offset=game_start_offset,
        early_game_window_seconds=early_game_window_seconds,
        early_game_reserved=early_game_reserved,
        momentum_reserved=momentum_reserved,
        sampling_strategy=sampling_strategy,
        focus_window_seconds=focus_window_seconds,
        focus_budget_ratio=focus_budget_ratio,
        global_backfill=global_backfill,
        focus_profile=focus_profile,
        speed=speed,
    )["final_timestamps_sec"]


def _resolve_sampling_strategy(
    sampling_strategy: str | None,
    adaptive: bool,
) -> str:
    if sampling_strategy:
        return sampling_strategy
    return "adaptive" if adaptive else "fixed"


def _resolve_focus_profile(focus_profile: str | None) -> str:
    if focus_profile is None:
        return DEFAULT_FOCUS_PROFILE

    normalized = focus_profile.strip().lower()
    if normalized not in VALID_FOCUS_PROFILES:
        valid = ", ".join(sorted(VALID_FOCUS_PROFILES))
        raise ValueError(f"Unsupported focus profile: {focus_profile}. Choose from {valid}.")
    return normalized


def _make_focus_window(
    *,
    window_id: str,
    reason: str,
    priority: int,
    start_sec: float,
    end_sec: float,
    source_events: list[dict],
) -> dict:
    return {
        "id": window_id,
        "reason": reason,
        "reasons": [reason],
        "priority": priority,
        "start_sec": start_sec,
        "end_sec": end_sec,
        "source_events": source_events,
    }


def _merge_focus_windows(windows: list[dict]) -> list[dict]:
    if not windows:
        return []

    sorted_windows = sorted(
        windows,
        key=lambda w: (w["start_sec"], w["end_sec"], -w["priority"]),
    )
    merged: list[dict] = []

    for window in sorted_windows:
        if (
            not merged
            or window["start_sec"] > merged[-1]["end_sec"]
            or window["reason"] != merged[-1]["reason"]
        ):
            merged.append({
                "id": window["id"],
                "reason": window["reason"],
                "reasons": list(window["reasons"]),
                "priority": window["priority"],
                "start_sec": window["start_sec"],
                "end_sec": window["end_sec"],
                "source_events": list(window["source_events"]),
            })
            continue

        current = merged[-1]
        current["end_sec"] = max(current["end_sec"], window["end_sec"])
        current["priority"] = max(current["priority"], window["priority"])
        for reason in window["reasons"]:
            if reason not in current["reasons"]:
                current["reasons"].append(reason)
        current["reason"] = "+".join(current["reasons"])
        current["source_events"].extend(window["source_events"])

    return merged


def _compress_focus_windows(
    windows: list[dict],
    *,
    objective_merge_gap_seconds: int = DEFAULT_OBJECTIVE_MERGE_GAP_SECONDS,
    max_momentum_window_seconds: int = DEFAULT_MAX_MOMENTUM_WINDOW_SECONDS,
) -> list[dict]:
    if not windows:
        return []

    compressed: list[dict] = []

    for window in sorted(windows, key=lambda w: (w["start_sec"], w["end_sec"], -w["priority"])):
        current = {
            "id": window["id"],
            "reason": window["reason"],
            "reasons": list(window["reasons"]),
            "priority": window["priority"],
            "start_sec": window["start_sec"],
            "end_sec": window["end_sec"],
            "source_events": list(window["source_events"]),
        }

        if (
            compressed
            and current["reason"] == "objective"
            and compressed[-1]["reason"] == "objective"
            and current["start_sec"] - compressed[-1]["end_sec"] <= objective_merge_gap_seconds
        ):
            previous = compressed[-1]
            previous["end_sec"] = max(previous["end_sec"], current["end_sec"])
            previous["priority"] = max(previous["priority"], current["priority"])
            previous["source_events"].extend(current["source_events"])
            continue

        if current["reason"] == "momentum" and max_momentum_window_seconds > 0:
            duration = current["end_sec"] - current["start_sec"]
            if duration > max_momentum_window_seconds:
                current["end_sec"] = current["start_sec"] + max_momentum_window_seconds
                for event in current["source_events"]:
                    if event.get("type") == "momentum":
                        event["original_end_sec"] = event["end_sec"]
                        event["end_sec"] = min(
                            event["start_sec"] + max_momentum_window_seconds,
                            event["end_sec"],
                        )

        compressed.append(current)

    return compressed


def _build_focus_windows(
    *,
    duration_sec: float,
    match_context: dict | None,
    game_start_offset: int,
    focus_window_seconds: int,
    focus_profile: str = DEFAULT_FOCUS_PROFILE,
    speed: float = 1.0,
) -> list[dict]:
    if duration_sec <= 0 or focus_window_seconds <= 0 or not match_context:
        return []

    focus_profile = _resolve_focus_profile(focus_profile)

    profile_priorities = {
        "balanced": {
            "death": 100,
            "kill": 75,
            "assist": 65,
            "objective_elite": 90,
            "objective_building": 85,
            "level": 60,
            "momentum": 80,
        },
        "lane": {
            "death": 70,
            "kill": 68,
            "assist": 58,
            "objective_elite": 62,
            "objective_building": 58,
            "level": 82,
            "momentum": 56,
        },
        "objective": {
            "death": 105,
            "kill": 80,
            "assist": 70,
            "objective_elite": 115,
            "objective_building": 100,
            "level": 55,
            "momentum": 98,
        },
        "roam": {
            "death": 65,
            "kill": 82,
            "assist": 100,
            "objective_elite": 96,
            "objective_building": 88,
            "level": 62,
            "momentum": 92,
        },
    }[focus_profile]

    def bounded_window(
        ts: int,
        *,
        reason: str,
        priority: int,
        event_payload: dict,
    ) -> dict | None:
        video_ts = game_start_offset + _game_time_to_video_time(ts, speed=speed)
        if video_ts < 0 or video_ts > duration_sec:
            return None
        video_window = _game_time_to_video_time(focus_window_seconds, speed=speed)
        start_sec = max(0.0, float(video_ts - video_window))
        end_sec = min(duration_sec, float(video_ts + video_window))
        if end_sec <= start_sec:
            return None
        return _make_focus_window(
            window_id=f"{reason}_{ts}",
            reason=reason,
            priority=priority,
            start_sec=start_sec,
            end_sec=end_sec,
            source_events=[event_payload],
        )

    windows: list[dict] = []

    for ts in match_context.get("death_timestamps", []):
        if isinstance(ts, int):
            window = bounded_window(
                ts,
                reason="death",
                priority=profile_priorities["death"],
                event_payload={"type": "death", "timestamp_sec": ts},
            )
            if window:
                windows.append(window)

    for ts in match_context.get("kill_timestamps", []):
        if isinstance(ts, int):
            window = bounded_window(
                ts,
                reason="kill",
                priority=profile_priorities["kill"],
                event_payload={"type": "kill", "timestamp_sec": ts},
            )
            if window:
                windows.append(window)

    for ts in match_context.get("assist_timestamps", []):
        if isinstance(ts, int):
            window = bounded_window(
                ts,
                reason="assist",
                priority=profile_priorities["assist"],
                event_payload={"type": "assist", "timestamp_sec": ts},
            )
            if window:
                windows.append(window)

    for event in match_context.get("objective_events", []):
        ts = event.get("timestamp")
        if isinstance(ts, int):
            event_type = event.get("type", "objective")
            priority = (
                profile_priorities["objective_elite"]
                if event_type == "ELITE_MONSTER_KILL"
                else profile_priorities["objective_building"]
            )
            window = bounded_window(
                ts,
                reason="objective",
                priority=priority,
                event_payload={"type": event_type, "timestamp_sec": ts},
            )
            if window:
                windows.append(window)

    for level_info in match_context.get("level_ups", []):
        ts = level_info.get("timestamp")
        level = level_info.get("level")
        if isinstance(ts, int) and level in {6, 11, 16}:
            window = bounded_window(
                ts,
                reason=f"level_{level}",
                priority=profile_priorities["level"],
                event_payload={"type": "level_up", "timestamp_sec": ts, "level": level},
            )
            if window:
                windows.append(window)

    if focus_profile == "lane":
        lane_start = max(0.0, float(game_start_offset))
        lane_end = min(
            duration_sec,
            lane_start + _game_time_to_video_time(DEFAULT_LANE_PHASE_SECONDS, speed=speed),
        )
        if lane_end - lane_start >= 90:
            span = lane_end - lane_start
            segment_count = min(
                DEFAULT_LANE_PHASE_WINDOWS,
                max(
                    1,
                    int(math.ceil(
                        span / max(
                            _game_time_to_video_time(180.0, speed=speed),
                            _game_time_to_video_time(focus_window_seconds * 2, speed=speed),
                        )
                    )),
                ),
            )
            step = span / segment_count
            for index in range(segment_count):
                segment_start = lane_start + (step * index)
                segment_end = lane_end if index == segment_count - 1 else segment_start + step
                windows.append(
                    _make_focus_window(
                        window_id=f"lane_phase_{index}",
                        reason="lane",
                        priority=110 - (index * 4),
                        start_sec=segment_start,
                        end_sec=segment_end,
                        source_events=[{
                            "type": "lane_phase",
                            "start_sec": max(0, int(round(segment_start - game_start_offset))),
                            "end_sec": max(0, int(round(segment_end - game_start_offset))),
                        }],
                    )
                )

        for item in match_context.get("item_purchases", []):
            ts = item.get("timestamp")
            if isinstance(ts, int) and 0 <= ts <= DEFAULT_LANE_PHASE_SECONDS:
                window = bounded_window(
                    ts,
                    reason="lane_reset",
                    priority=90,
                    event_payload={
                        "type": "item_purchase",
                        "timestamp_sec": ts,
                        "item_name": item.get("item_name"),
                    },
                )
                if window:
                    windows.append(window)

    if focus_profile == "roam":
        positions = match_context.get("position_timeline", [])
        previous_frame: dict | None = None
        for frame in positions:
            ts = frame.get("timestamp")
            x = frame.get("x")
            y = frame.get("y")
            if not all(isinstance(value, int) for value in (ts, x, y)):
                continue
            if previous_frame is not None:
                prev_ts = previous_frame["timestamp"]
                distance = math.dist(
                    (float(previous_frame["x"]), float(previous_frame["y"])),
                    (float(x), float(y)),
                )
                if 360 <= ts <= 1320 and 0 < ts - prev_ts <= 180 and distance >= DEFAULT_ROAM_DISTANCE_THRESHOLD:
                    window = bounded_window(
                        ts,
                        reason="roam",
                        priority=95,
                        event_payload={
                            "type": "position_transition",
                            "timestamp_sec": ts,
                            "distance": round(distance, 1),
                        },
                    )
                    if window:
                        windows.append(window)
            previous_frame = frame

    for index, (start_sec, end_sec) in enumerate(important_time_windows(match_context)):
        video_start = max(
            0.0,
            float(game_start_offset + _game_time_to_video_time(start_sec, speed=speed)),
        )
        video_end = min(
            duration_sec,
            float(game_start_offset + _game_time_to_video_time(end_sec, speed=speed)),
        )
        if video_end <= video_start:
            continue
        windows.append(
            _make_focus_window(
                window_id=f"momentum_{index}",
                reason="momentum",
                priority=profile_priorities["momentum"],
                start_sec=video_start,
                end_sec=video_end,
                source_events=[{"type": "momentum", "start_sec": start_sec, "end_sec": end_sec}],
            )
        )

    return _compress_focus_windows(_merge_focus_windows(windows))


def _allocate_focus_counts(
    windows: list[dict],
    *,
    focus_budget: int,
) -> tuple[list[dict], int]:
    if focus_budget <= 0 or not windows:
        return [], focus_budget

    minimum_per_window = 2 if focus_budget >= 2 else 1
    max_windows = max(1, focus_budget // minimum_per_window)
    selected = sorted(
        windows,
        key=lambda w: (-w["priority"], w["start_sec"], w["end_sec"]),
    )[:max_windows]

    if not selected:
        return [], focus_budget

    for window in selected:
        window["allocated_count"] = minimum_per_window
        window["selected_timestamps_sec"] = []

    remaining = focus_budget - (minimum_per_window * len(selected))
    if remaining <= 0:
        return selected, 0

    weights = [
        max(1.0, window["priority"] * math.sqrt(max(1.0, window["end_sec"] - window["start_sec"])))
        for window in selected
    ]
    total_weight = sum(weights)
    extra_counts = [0] * len(selected)
    fractions: list[tuple[float, int]] = []

    for index, weight in enumerate(weights):
        share = (weight / total_weight) * remaining if total_weight else 0.0
        whole = int(math.floor(share))
        extra_counts[index] = whole
        fractions.append((share - whole, index))

    allocated = sum(extra_counts)
    for _, index in sorted(fractions, key=lambda item: (-item[0], item[1])):
        if allocated >= remaining:
            break
        extra_counts[index] += 1
        allocated += 1

    for window, extra in zip(selected, extra_counts):
        window["allocated_count"] += extra

    return selected, max(0, remaining - allocated)


def _build_focused_sampling_report(
    *,
    duration_sec: float,
    max_screenshots: int,
    windows: list[dict],
    focus_budget_ratio: float,
    global_backfill: int,
    game_start_offset: int,
    focus_profile: str = DEFAULT_FOCUS_PROFILE,
) -> dict:
    focus_profile = _resolve_focus_profile(focus_profile)

    if duration_sec <= 0 or max_screenshots <= 0:
        return {
            "strategy": "focused",
            "focus_profile": focus_profile,
            "video_duration_sec": duration_sec,
            "max_screenshots": max_screenshots,
            "focus_budget": 0,
            "backfill_budget": 0,
            "focus_windows": [],
            "backfill": {"allocated_count": 0, "selected_timestamps_sec": []},
            "final_timestamps_sec": [],
        }

    if not windows:
        backfill_timestamps = _evenly_spaced_timestamps(
            max(0.0, float(game_start_offset)),
            duration_sec,
            max_screenshots,
        )
        return {
            "strategy": "focused",
            "focus_profile": focus_profile,
            "video_duration_sec": duration_sec,
            "max_screenshots": max_screenshots,
            "focus_budget": 0,
            "backfill_budget": max_screenshots,
            "focus_windows": [],
            "backfill": {
                "allocated_count": len(backfill_timestamps),
                "selected_timestamps_sec": backfill_timestamps,
            },
            "final_timestamps_sec": sorted(backfill_timestamps),
        }

    reserved_backfill = min(max_screenshots, max(0, global_backfill))
    requested_focus_budget = int(round(max_screenshots * max(0.0, min(1.0, focus_budget_ratio))))
    focus_budget = min(max(0, max_screenshots - reserved_backfill), requested_focus_budget)
    backfill_budget = max(0, max_screenshots - focus_budget)

    allocated_windows, _ = _allocate_focus_counts(windows, focus_budget=focus_budget)
    focus_timestamps: list[float] = []
    focus_window_reports: list[dict] = []

    for window in sorted(allocated_windows, key=lambda item: item["start_sec"]):
        selected_timestamps = _evenly_spaced_timestamps(
            window["start_sec"],
            window["end_sec"],
            window["allocated_count"],
        )
        window["selected_timestamps_sec"] = selected_timestamps
        focus_timestamps.extend(selected_timestamps)
        focus_window_reports.append({
            "id": window["id"],
            "reason": window["reason"],
            "reasons": window["reasons"],
            "priority": window["priority"],
            "start_sec": window["start_sec"],
            "end_sec": window["end_sec"],
            "duration_sec": window["end_sec"] - window["start_sec"],
            "allocated_count": window["allocated_count"],
            "selected_timestamps_sec": selected_timestamps,
            "source_events": window["source_events"],
        })

    backfill_timestamps: list[float] = []
    start_sec = max(0.0, float(game_start_offset))
    if backfill_budget > 0 and duration_sec > start_sec:
        span = duration_sec - start_sec
        step = span / backfill_budget
        backfill_timestamps = [
            start_sec + (step * i) + (step / 2)
            for i in range(backfill_budget)
            if start_sec + (step * i) + (step / 2) < duration_sec
        ]
    final_timestamps = _merge_unique_timestamps(
        focus_timestamps,
        backfill_timestamps,
        limit=max_screenshots,
    )
    if len(final_timestamps) < max_screenshots and duration_sec > start_sec:
        seen_keys = {int(round(ts * 1000)) for ts in final_timestamps}
        candidate_count = max(max_screenshots * 4, 8)
        span = duration_sec - start_sec
        step = span / candidate_count
        refill_candidates: list[float] = []
        for i in range(candidate_count):
            ts = start_sec + (step * i) + (step / 2)
            key = int(round(ts * 1000))
            if ts >= duration_sec or key in seen_keys:
                continue
            refill_candidates.append(ts)
            seen_keys.add(key)
            if len(final_timestamps) + len(refill_candidates) >= max_screenshots:
                break
        if refill_candidates:
            backfill_timestamps.extend(refill_candidates)
            final_timestamps = _merge_unique_timestamps(
                focus_timestamps,
                backfill_timestamps,
                limit=max_screenshots,
            )

    return {
        "strategy": "focused",
        "focus_profile": focus_profile,
        "video_duration_sec": duration_sec,
        "max_screenshots": max_screenshots,
        "focus_budget": focus_budget,
        "backfill_budget": backfill_budget,
        "focus_windows": focus_window_reports,
        "backfill": {
            "allocated_count": len(backfill_timestamps),
            "selected_timestamps_sec": backfill_timestamps,
        },
        "final_timestamps_sec": final_timestamps,
    }


def _build_sampling_plan(
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
    sampling_strategy: str = "fixed",
    focus_window_seconds: int = DEFAULT_FOCUS_WINDOW_SECONDS,
    focus_budget_ratio: float = DEFAULT_FOCUS_BUDGET_RATIO,
    global_backfill: int = DEFAULT_GLOBAL_BACKFILL,
    focus_profile: str | None = None,
    speed: float = 1.0,
) -> dict:
    if duration_sec <= 0 or max_screenshots <= 0:
        return {
            "strategy": sampling_strategy,
            "video_duration_sec": duration_sec,
            "max_screenshots": max_screenshots,
            "final_timestamps_sec": [],
        }

    if sampling_strategy == "focused":
        resolved_focus_profile = _resolve_focus_profile(focus_profile)
        windows = _build_focus_windows(
            duration_sec=duration_sec,
            match_context=match_context,
            game_start_offset=game_start_offset,
            focus_window_seconds=focus_window_seconds,
            focus_profile=resolved_focus_profile,
            speed=speed,
        )
        return _build_focused_sampling_report(
            duration_sec=duration_sec,
            max_screenshots=max_screenshots,
            windows=windows,
            focus_budget_ratio=focus_budget_ratio,
            global_backfill=global_backfill,
            game_start_offset=game_start_offset,
            focus_profile=resolved_focus_profile,
        )

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
        speed=speed,
    )
    momentum_candidates = _momentum_candidate_timestamps(
        match_context,
        game_start_offset=game_start_offset,
        max_count=momentum_budget,
        speed=speed,
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
            _game_time_to_video_time(float(interval_seconds), speed=speed),
            max(max_screenshots, remaining),
        )
        backfill_candidates = [
            ts for ts in adaptive_candidates if ts >= max(0, game_start_offset)
        ]
    else:
        backfill_candidates = _fixed_interval_timestamps(
            duration_sec,
            max(1, int(round(_game_time_to_video_time(interval_seconds, speed=speed)))),
            start_sec=max(0, game_start_offset),
        )

    final_timestamps = _merge_unique_timestamps(
        early_candidates,
        momentum_candidates,
        backfill_candidates,
        limit=max_screenshots,
    )
    return {
        "strategy": sampling_strategy,
        "video_duration_sec": duration_sec,
        "max_screenshots": max_screenshots,
        "early_candidates_sec": early_candidates,
        "momentum_candidates_sec": momentum_candidates,
        "backfill_candidates_sec": backfill_candidates,
        "final_timestamps_sec": final_timestamps,
    }


def plan_screenshot_sampling(
    video_path: Path,
    interval_seconds: int = 10,
    *,
    adaptive: bool = False,
    max_screenshots: int = DEFAULT_MAX_SCREENSHOTS,
    match_context: dict | None = None,
    game_start_offset: int = 0,
    sampling_strategy: str | None = None,
    focus_window_seconds: int = DEFAULT_FOCUS_WINDOW_SECONDS,
    focus_budget_ratio: float = DEFAULT_FOCUS_BUDGET_RATIO,
    global_backfill: int = DEFAULT_GLOBAL_BACKFILL,
    focus_profile: str | None = None,
    speed: float = 1.0,
) -> dict:
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {
            "strategy": _resolve_sampling_strategy(sampling_strategy, adaptive),
            "video_duration_sec": 0,
            "max_screenshots": max_screenshots,
            "final_timestamps_sec": [],
        }

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        return {
            "strategy": _resolve_sampling_strategy(sampling_strategy, adaptive),
            "video_duration_sec": 0,
            "max_screenshots": max_screenshots,
            "final_timestamps_sec": [],
        }

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps
    strategy = _resolve_sampling_strategy(sampling_strategy, adaptive)

    activity_profile: list[tuple[float, float]] = []
    if strategy == "adaptive" and duration_sec > 0:
        cap.release()
        activity_profile = _compute_scene_activity(video_path)
    else:
        cap.release()

    return _build_sampling_plan(
        duration_sec=duration_sec,
        interval_seconds=interval_seconds,
        max_screenshots=max_screenshots,
        adaptive=(strategy == "adaptive"),
        activity_profile=activity_profile,
        match_context=match_context,
        game_start_offset=game_start_offset,
        sampling_strategy=strategy,
        focus_window_seconds=focus_window_seconds,
        focus_budget_ratio=focus_budget_ratio,
        global_backfill=global_backfill,
        focus_profile=focus_profile,
        speed=speed,
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
    sampling_strategy: str | None = None,
    focus_window_seconds: int = DEFAULT_FOCUS_WINDOW_SECONDS,
    focus_budget_ratio: float = DEFAULT_FOCUS_BUDGET_RATIO,
    global_backfill: int = DEFAULT_GLOBAL_BACKFILL,
    focus_profile: str | None = None,
    planned_timestamps: list[float] | None = None,
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

    strategy = _resolve_sampling_strategy(sampling_strategy, adaptive)
    if planned_timestamps is None:
        activity_profile: list[tuple[float, float]] = []
        if strategy == "adaptive" and duration_sec > 0:
            cap.release()
            activity_profile = _compute_scene_activity(video_path)
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return []

        sample_timestamps = _build_sampling_timestamps(
            duration_sec=duration_sec,
            interval_seconds=interval_seconds,
            max_screenshots=max_screenshots,
            adaptive=(strategy == "adaptive"),
            activity_profile=activity_profile,
            match_context=match_context,
            game_start_offset=game_start_offset,
            sampling_strategy=strategy,
            focus_window_seconds=focus_window_seconds,
            focus_budget_ratio=focus_budget_ratio,
            global_backfill=global_backfill,
            focus_profile=focus_profile,
            speed=speed,
        )
    else:
        sample_timestamps = planned_timestamps
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
