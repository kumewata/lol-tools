"""Compress lol_review findings into a compact LLM input.

The raw `latest_findings.json` is several hundred KB, mostly per-frame timelines.
Plan usage is metered against the user's ChatGPT plan, so only signals the advice
prompt actually uses are kept.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

SUMMARY_KEYS = (
    "summoner", "total_games", "wins", "losses", "win_rate", "avg_kda", "avg_cs_per_min",
)
MATCH_DROP_KEYS = {"timestamp_ms", "game_mode", "game_version"}
KEPT_ITEM_TYPES = {"completed", "boots"}
GOLD_DIFF_STEP_MINUTES = 5
EARLY_GAME_SECONDS = 600
DURATION_BUCKETS = ((0, 20, "20分未満"), (20, 30, "20〜30分"), (30, None, "30分以上"))
# Same labels as lol_dashboard.persist._QUEUE_MAP (copied to avoid a duckdb dependency).
QUEUE_LABELS = {
    "400": "normal_draft", "420": "ranked_solo", "430": "normal_blind", "440": "ranked_flex",
    "450": "aram", "480": "normal_quickplay", "700": "clash", "1700": "arena",
}


def _round(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 3)
    return value


def _minutes(match: dict[str, Any]) -> float | None:
    seconds = match.get("game_duration_seconds")
    return seconds / 60 if isinstance(seconds, (int, float)) and seconds > 0 else None


def _compact_match(match: dict[str, Any]) -> dict[str, Any]:
    compact = {k: _round(v) for k, v in match.items() if k not in MATCH_DROP_KEYS}
    minutes = _minutes(match)
    if minutes:
        compact["duration_min"] = round(minutes, 1)
        if isinstance(match.get("vision_score"), (int, float)):
            compact["vision_per_min"] = round(match["vision_score"] / minutes, 2)
    queue = str(match.get("queue_type", ""))
    compact["queue_label"] = QUEUE_LABELS.get(queue, "other")
    return compact


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _group_summary(matches: list[dict[str, Any]], early_deaths: dict[str, int]) -> dict[str, Any]:
    def nums(key: str) -> list[float]:
        return [m[key] for m in matches if isinstance(m.get(key), (int, float))]

    wins = sum(1 for m in matches if m.get("win"))
    vision_per_min = [
        m["vision_score"] / minutes
        for m in matches
        if isinstance(m.get("vision_score"), (int, float)) and (minutes := _minutes(m))
    ]
    summary: dict[str, Any] = {
        "games": len(matches),
        "wins": wins,
        "losses": len(matches) - wins,
        "win_rate": round(wins / len(matches), 3) if matches else None,
        "avg_kda": _mean(nums("kda")),
        "avg_kill_participation": _mean(nums("kill_participation")),
        "avg_vision_score": _mean(nums("vision_score")),
        "avg_vision_per_min": _mean(vision_per_min),
        "avg_cs_per_min": _mean(nums("cs_per_min")),
        "avg_deaths": _mean(nums("deaths")),
    }
    tracked = [m for m in matches if m.get("match_id") in early_deaths]
    if tracked:
        summary["avg_deaths_before_10min"] = _mean([early_deaths[m["match_id"]] for m in tracked])
    return summary


def _grouped(
    matches: list[dict[str, Any]], key: Callable[[dict[str, Any]], str | None], early_deaths: dict[str, int]
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for m in matches:
        label = key(m)
        if label is not None:
            groups.setdefault(label, []).append(m)
    return {label: _group_summary(ms, early_deaths) for label, ms in groups.items()}


def _duration_bucket(match: dict[str, Any]) -> str | None:
    minutes = _minutes(match)
    if minutes is None:
        return None
    for low, high, label in DURATION_BUCKETS:
        if minutes >= low and (high is None or minutes < high):
            return label
    return None


def build_aggregates(findings: dict[str, Any]) -> dict[str, Any]:
    """Pre-computed group stats so the LLM quotes numbers instead of computing them."""
    matches = [m for m in findings.get("matches") or [] if isinstance(m, dict)]
    early_deaths = {
        s["match_id"]: sum(1 for t in s.get("death_timestamps") or [] if t < EARLY_GAME_SECONDS)
        for s in findings.get("player_stats") or []
        if isinstance(s, dict) and s.get("match_id")
    }
    by_duration = _grouped(matches, _duration_bucket, early_deaths)
    return {
        "overall": _group_summary(matches, early_deaths),
        "by_duration": {label: by_duration[label] for _, _, label in DURATION_BUCKETS if label in by_duration},
        "by_champion": _grouped(matches, lambda m: m.get("champion"), early_deaths),
        "by_role": _grouped(matches, lambda m: m.get("role"), early_deaths),
        "by_queue": _grouped(matches, lambda m: QUEUE_LABELS.get(str(m.get("queue_type", "")), "other"), early_deaths),
        "by_ally_champion": {
            k: v for k, v in _grouped_multi(matches, "ally_team", early_deaths).items() if v["games"] >= 2
        },
    }


def _grouped_multi(
    matches: list[dict[str, Any]], list_key: str, early_deaths: dict[str, int]
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for m in matches:
        for name in m.get(list_key) or []:
            groups.setdefault(name, []).append(m)
    return {name: _group_summary(ms, early_deaths) for name, ms in groups.items()}


def _clock(seconds: Any) -> Any:
    """Game time as "m:ss" so the model never converts seconds itself."""
    if not isinstance(seconds, (int, float)):
        return seconds
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _timeline_summary(stats: dict[str, Any]) -> dict[str, Any]:
    items = [
        {"t": _clock(i.get("timestamp")), "item": i.get("item_name")}
        for i in stats.get("item_purchases") or []
        if i.get("item_type") in KEPT_ITEM_TYPES
    ]
    objectives = Counter(
        str(e.get("monsterSubType") or e.get("monsterType") or e.get("buildingType") or e.get("type"))
        for e in stats.get("objective_events") or []
    )
    gold_diff = stats.get("gold_diff_timeline") or []
    return {
        "kill_times": [_clock(t) for t in stats.get("kill_timestamps") or []],
        "death_times": [_clock(t) for t in stats.get("death_timestamps") or []],
        "assist_times": [_clock(t) for t in stats.get("assist_timestamps") or []],
        "item_build": items,
        f"gold_diff_every_{GOLD_DIFF_STEP_MINUTES}min": gold_diff[::GOLD_DIFF_STEP_MINUTES],
        "objective_counts": dict(objectives),
    }


def diff_snapshots(latest: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    def delta(key: str) -> dict[str, Any]:
        before, after = previous.get(key), latest.get(key)
        change = None
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            change = _round(after - before)
        return {"previous": _round(before), "latest": _round(after), "change": change}

    def categories(data: dict[str, Any]) -> set[str]:
        return {f["category"] for f in data.get("findings") or [] if "category" in f}

    before_cats, after_cats = categories(previous), categories(latest)
    return {
        "previous_generated_at": previous.get("generated_at"),
        "win_rate": delta("win_rate"),
        "avg_kda": delta("avg_kda"),
        "avg_cs_per_min": delta("avg_cs_per_min"),
        "findings_resolved": sorted(before_cats - after_cats),
        "findings_new": sorted(after_cats - before_cats),
        "findings_continuing": sorted(before_cats & after_cats),
    }


def build_advice_context(
    findings: dict[str, Any],
    *,
    practice_status: dict[str, Any] | None = None,
    matchup: dict[str, Any] | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stats_by_match = {
        s.get("match_id"): s for s in findings.get("player_stats") or [] if isinstance(s, dict)
    }
    matches = []
    for match in findings.get("matches") or []:
        compact = _compact_match(match)
        stats = stats_by_match.get(match.get("match_id"))
        if stats:
            compact["timeline"] = _timeline_summary(stats)
        matches.append(compact)

    context: dict[str, Any] = {k: _round(findings.get(k)) for k in SUMMARY_KEYS}
    context["findings"] = findings.get("findings") or []
    context["aggregates"] = build_aggregates(findings)
    context["champion_stats"] = [
        {k: _round(v) for k, v in c.items()} for c in findings.get("champion_stats") or []
    ]
    context["matches"] = matches
    context["matchup_summary"] = matchup
    context["practice_status"] = practice_status
    context["comparison_with_previous"] = diff_snapshots(findings, previous) if previous else None
    return context
