from __future__ import annotations

import json
from pathlib import Path

import pytest

from lol_coach.context import build_advice_context, diff_snapshots

REAL_FINDINGS = Path(__file__).parents[2] / "lol_review" / "output" / "latest_findings.json"
HEAVY_KEYS = ("position_timeline", "jungle_cs_timeline", "skill_level_ups", "level_ups", "opponent_level_ups")


def _frames(n: int) -> list[dict]:
    return [{"timestamp": i * 60, "x": i, "y": i, "cs": i} for i in range(n)]


def _synthetic_findings(games: int = 10) -> dict:
    matches, stats = [], []
    for g in range(games):
        mid = f"JP1_{g}"
        matches.append({
            "match_id": mid, "champion": "Nautilus", "kills": 1, "deaths": 2, "assists": 3,
            "cs": 40, "win": g % 2 == 0, "role": "UTILITY", "kill_participation": 0.4545454545,
            "lane_opponents": ["MissFortune", "Leona"], "timestamp_ms": 1, "game_mode": "CLASSIC",
        })
        stats.append({
            "match_id": mid,
            "gold_timeline": list(range(40)),
            "gold_diff_timeline": list(range(40)),
            "position_timeline": _frames(40),
            "jungle_cs_timeline": _frames(40),
            "kill_timestamps": [100], "death_timestamps": [200], "assist_timestamps": [300],
            "objective_events": [
                {"type": "ELITE_MONSTER_KILL", "monsterType": "DRAGON", "monsterSubType": "AIR_DRAGON",
                 "timestamp": 400, "position": {"x": 1, "y": 2}, "killerTeamId": 100}
                for _ in range(30)
            ],
            "item_purchases": [
                {"item_id": 1, "timestamp": t, "item_name": f"item{t}", "item_type": kind, "item_type_label": "x"}
                for t, kind in enumerate(["consumable", "ward", "component", "completed", "boots"] * 8)
            ],
            "skill_level_ups": _frames(18), "level_ups": _frames(18), "opponent_level_ups": _frames(36),
        })
    return {
        "summoner": "Me#JP1", "total_games": games, "wins": 5, "losses": 5, "win_rate": 0.5,
        "avg_kda": 2.0, "avg_cs_per_min": 1.2, "champion_stats": [{"champion": "Nautilus", "games": games}],
        "matches": matches, "player_stats": stats,
        "findings": [{"category": "vision", "severity": "warning", "message": "m", "detail": "d"}],
        "report_html": "<html>" + "x" * 5000, "generated_at": "2026-10-03T00:00:00",
    }


def _size(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False))


def test_context_size_ratio_synthetic() -> None:
    findings = _synthetic_findings()
    assert _size(build_advice_context(findings)) <= _size(findings) * 0.15


@pytest.mark.skipif(not REAL_FINDINGS.exists(), reason="local findings not available")
def test_context_size_ratio_real_data() -> None:
    findings = json.loads(REAL_FINDINGS.read_text(encoding="utf-8"))
    assert _size(build_advice_context(findings)) <= _size(findings) * 0.15


def test_context_drops_heavy_timelines() -> None:
    context = build_advice_context(_synthetic_findings())
    dumped = json.dumps(context)
    for key in HEAVY_KEYS + ("report_html", "player_stats", "position"):
        assert f'"{key}"' not in dumped
    timeline = context["matches"][0]["timeline"]
    assert {i["item"] for i in timeline["item_build"]} <= {f"item{t}" for t in range(40) if t % 5 in (3, 4)}
    assert timeline["item_build"][0]["t"] == "0:03"
    assert timeline["objective_counts"] == {"AIR_DRAGON": 30}
    assert timeline["gold_diff_every_5min"] == list(range(0, 40, 5))
    assert timeline["death_times"] == ["3:20"]


def test_context_tolerates_missing_player_stats() -> None:
    findings = _synthetic_findings(2)
    del findings["player_stats"]
    context = build_advice_context(findings)
    assert len(context["matches"]) == 2
    assert "timeline" not in context["matches"][0]


def test_context_includes_optional_sections() -> None:
    context = build_advice_context(
        _synthetic_findings(1), practice_status={"plans": []}, matchup={"recommendations": {}},
    )
    assert context["practice_status"] == {"plans": []}
    assert context["matchup_summary"] == {"recommendations": {}}
    assert context["comparison_with_previous"] is None


def test_diff_snapshots_categories() -> None:
    previous = {"win_rate": 0.4, "avg_kda": 2.0, "avg_cs_per_min": 1.0, "findings": [
        {"category": "vision"}, {"category": "deaths"},
    ]}
    latest = {"win_rate": 0.6, "avg_kda": None, "avg_cs_per_min": 1.5, "findings": [
        {"category": "deaths"}, {"category": "cs"},
    ]}
    diff = diff_snapshots(latest, previous)
    assert diff["win_rate"]["change"] == 0.2
    assert diff["avg_kda"]["change"] is None
    assert diff["findings_resolved"] == ["vision"]
    assert diff["findings_new"] == ["cs"]
    assert diff["findings_continuing"] == ["deaths"]


def test_aggregates_by_duration_and_early_deaths() -> None:
    from lol_coach.context import build_aggregates

    findings = {
        "matches": [
            {"match_id": "a", "champion": "Senna", "win": True, "game_duration_seconds": 15 * 60, "vision_score": 30},
            {"match_id": "b", "champion": "Senna", "win": False, "game_duration_seconds": 25 * 60, "vision_score": 50},
            {"match_id": "c", "champion": "Leona", "win": False, "game_duration_seconds": 35 * 60, "queue_type": "420"},
        ],
        "player_stats": [
            {"match_id": "a", "death_timestamps": [100, 599, 600]},
            {"match_id": "b", "death_timestamps": []},
        ],
    }
    agg = build_aggregates(findings)
    assert list(agg["by_duration"]) == ["20分未満", "20〜30分", "30分以上"]
    assert agg["by_duration"]["20分未満"]["wins"] == 1
    assert agg["by_champion"]["Senna"]["games"] == 2
    assert agg["by_champion"]["Senna"]["win_rate"] == 0.5
    assert agg["by_champion"]["Senna"]["avg_vision_per_min"] == 2.0
    assert agg["by_champion"]["Senna"]["avg_deaths_before_10min"] == 1.0
    assert "avg_deaths_before_10min" not in agg["by_champion"]["Leona"]
    assert agg["by_queue"]["ranked_solo"]["games"] == 1
    assert agg["by_queue"]["other"]["games"] == 2
