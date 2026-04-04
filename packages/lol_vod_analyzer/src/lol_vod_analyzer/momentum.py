"""Momentum Impact: filter match events by win-probability swing.

Compresses match_context by keeping only events near timestamps where
the estimated win-probability changed significantly.  This reduces token
consumption when the context is sent to the LLM.
"""

from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)

# Base gold per team used to anchor the Pythagorean win-probability
# approximation (5 players * 500 starting gold).
_BASE_GOLD = 2500

# Exponent for generalised Pythagorean expectation.
# Lower values produce smoother probability curves (less saturation at 0%/100%).
# α=3.0 keeps ~60% of frames in the mid-range vs ~49% at α=5.0.
_ALPHA = 3.0


def compute_win_probability(
    gold_diff_timeline: Sequence[int],
    *,
    alpha: float = _ALPHA,
    base_gold: int = _BASE_GOLD,
) -> list[float]:
    """Approximate win probability from a gold-difference timeline.

    Uses a generalised Pythagorean expectation:
        G1 = base_gold + diff,  G2 = base_gold - diff
        P  = G1^α / (G1^α + G2^α)

    Returns a list of probabilities in [0, 1] with the same length as
    *gold_diff_timeline*.
    """
    probabilities: list[float] = []
    for diff in gold_diff_timeline:
        g1 = max(base_gold + diff, 1)
        g2 = max(base_gold - diff, 1)
        g1a = g1**alpha
        g2a = g2**alpha
        probabilities.append(g1a / (g1a + g2a))
    return probabilities


def compute_momentum(
    win_probs: Sequence[float],
    *,
    window: int = 3,
) -> list[float]:
    """Compute momentum-impact as a smoothed absolute derivative.

    For each frame index *i*, the momentum is the mean of
    ``|P(i) - P(i-1)|`` over a sliding window of size *window*.
    The first element is always 0.
    """
    if len(win_probs) < 2:
        return [0.0] * len(win_probs)

    deltas = [0.0] + [abs(win_probs[i] - win_probs[i - 1]) for i in range(1, len(win_probs))]

    smoothed: list[float] = []
    for i in range(len(deltas)):
        start = max(0, i - window + 1)
        smoothed.append(sum(deltas[start : i + 1]) / (i - start + 1))
    return smoothed


def filter_important_timestamps(
    momentum: Sequence[float],
    *,
    threshold_percentile: float = 75.0,
) -> set[int]:
    """Return frame indices where momentum exceeds the given percentile.

    Indices are expanded by ±1 so that neighbouring frames (which usually
    share the same real-game event window) are also retained.
    """
    if not momentum:
        return set()

    sorted_vals = sorted(momentum)
    rank = int(len(sorted_vals) * threshold_percentile / 100)
    rank = min(rank, len(sorted_vals) - 1)
    threshold = sorted_vals[rank]

    # When all values are identical (e.g. all zeros), keep everything.
    if threshold <= 0:
        return set(range(len(momentum)))

    important: set[int] = set()
    for i, val in enumerate(momentum):
        if val >= threshold:
            for offset in (-1, 0, 1):
                idx = i + offset
                if 0 <= idx < len(momentum):
                    important.add(idx)
    return important


def _frame_index_to_seconds(index: int, frame_interval_sec: int = 60) -> int:
    """Convert a timeline frame index to game-seconds."""
    return index * frame_interval_sec


def important_time_windows(
    match_context: dict,
    *,
    expansion_seconds: int = 30,
    frame_interval_sec: int = 60,
    threshold_percentile: float = 75.0,
) -> list[tuple[int, int]]:
    """Return important game-time windows derived from momentum swings."""
    gold_diff = match_context.get("gold_diff_timeline")
    if not gold_diff or not isinstance(gold_diff, list):
        return []

    win_probs = compute_win_probability(gold_diff)
    momentum = compute_momentum(win_probs)
    important_indices = sorted(
        filter_important_timestamps(
            momentum,
            threshold_percentile=threshold_percentile,
        )
    )
    if not important_indices:
        return []

    windows: list[tuple[int, int]] = []
    for idx in important_indices:
        centre = _frame_index_to_seconds(idx, frame_interval_sec=frame_interval_sec)
        start = max(0, centre - expansion_seconds)
        end = centre + expansion_seconds

        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))

    return windows


def compress_match_context(match_context: dict) -> dict:
    """Filter match_context events to keep only those near high-momentum timestamps.

    If gold_diff_timeline is missing or empty, returns the original context
    unchanged (fallback).
    """
    windows = important_time_windows(match_context)
    if not windows:
        logger.debug("gold_diff_timeline unavailable — skipping compression")
        return match_context

    # gold_diff_timeline entries are per-frame (typically 1 frame = 60 sec).
    # Build a set of game-seconds that are "important", ±30 sec around each.
    important_seconds: set[int] = set()
    for start, end in windows:
        for ts in range(start, end + 1):
            important_seconds.add(ts)

    # --- filter timestamp-bearing event lists --------------------------------
    event_keys = (
        "kill_timestamps",
        "death_timestamps",
        "assist_timestamps",
    )
    list_event_keys = (
        "objective_events",
        "item_purchases",
        "skill_level_ups",
        "level_ups",
        "opponent_level_ups",
    )

    compressed = dict(match_context)

    total_before = 0
    total_after = 0

    for key in event_keys:
        events = match_context.get(key, [])
        total_before += len(events)
        filtered = [ts for ts in events if ts in important_seconds]
        total_after += len(filtered)
        compressed[key] = filtered

    for key in list_event_keys:
        events = match_context.get(key, [])
        total_before += len(events)
        filtered = [e for e in events if e.get("timestamp", 0) in important_seconds]
        total_after += len(filtered)
        compressed[key] = filtered

    # Position and jungle-CS timelines are also filtered.
    for key in ("position_timeline", "jungle_cs_timeline"):
        events = match_context.get(key, [])
        total_before += len(events)
        filtered = [e for e in events if e.get("timestamp", 0) in important_seconds]
        total_after += len(filtered)
        compressed[key] = filtered

    logger.info(
        "momentum compression: %d → %d events (%.0f%% reduction)",
        total_before,
        total_after,
        (1 - total_after / total_before) * 100 if total_before else 0,
    )

    return compressed
