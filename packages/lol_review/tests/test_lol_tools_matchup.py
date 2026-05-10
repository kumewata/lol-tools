from __future__ import annotations

import json

from typer.testing import CliRunner

from lol_tools.matchup import app, build_matchup_summary


def _sample_data() -> dict:
    return {
        "summoner": "Player#JP1",
        "generated_at": "20260510_135640",
        "matches": [
            {
                "match_id": "m1",
                "champion": "Zyra",
                "role": "UTILITY",
                "win": True,
                "kda": None,
                "kill_participation": 0.60,
                "vision_score": 97,
                "lane_opponents": ["Caitlyn", "Nautilus"],
            },
            {
                "match_id": "m2",
                "champion": "Zyra",
                "role": "UTILITY",
                "win": False,
                "kda": 2.0,
                "kill_participation": 0.20,
                "vision_score": 40,
                "lane_opponents": ["Lux", "Caitlyn"],
            },
            {
                "match_id": "m3",
                "champion": "Seraphine",
                "role": "UTILITY",
                "win": True,
                "kda": 4.0,
                "kill_participation": 0.55,
                "vision_score": 75,
                "lane_opponents": ["Nautilus", "Caitlyn"],
            },
            {
                "match_id": "m4",
                "champion": "Leona",
                "role": "UTILITY",
                "win": False,
                "kda": 1.0,
                "kill_participation": 0.30,
                "vision_score": 30,
                "lane_opponents": [],
            },
        ],
        "champion_stats": [],
    }


def test_build_matchup_summary_aggregates_champions() -> None:
    summary = build_matchup_summary(_sample_data())

    zyra = next(s for s in summary["champion_summaries"] if s["champion"] == "Zyra")
    assert zyra["games"] == 2
    assert zyra["wins"] == 1
    assert zyra["win_rate"] == 0.5
    # Null KDA from m1 is excluded from the denominator.
    assert zyra["avg_kda"] == 2.0
    assert zyra["avg_kill_participation"] == 0.4
    assert zyra["avg_vision_score"] == 68.5


def test_build_matchup_summary_normalizes_lane_opponent_pairs() -> None:
    summary = build_matchup_summary(_sample_data())

    pair = next(
        p
        for p in summary["lane_opponent_pairs"]
        if p["opponents"] == ["Caitlyn", "Nautilus"]
    )
    assert pair["games"] == 2
    assert pair["wins"] == 2
    assert pair["our_champions"] == ["Seraphine", "Zyra"]


def test_build_matchup_summary_expands_single_opponents() -> None:
    summary = build_matchup_summary(_sample_data())

    caitlyn = next(s for s in summary["opponent_summaries"] if s["opponent"] == "Caitlyn")
    assert caitlyn["games"] == 3
    assert caitlyn["wins"] == 2
    assert caitlyn["losses"] == 1
    assert caitlyn["avg_kill_participation"] == 0.45


def test_build_matchup_summary_handles_missing_lane_opponents() -> None:
    data = _sample_data()
    data["matches"][0].pop("lane_opponents")

    summary = build_matchup_summary(data)

    assert summary["sample_size"] == 4
    assert all("games" in item for item in summary["champion_summaries"])


def test_build_matchup_summary_includes_recommendations() -> None:
    summary = build_matchup_summary(_sample_data())

    recommendations = summary["recommendations"]
    assert recommendations["pick_candidates"][0]["champion"] in {"Zyra", "Seraphine"}
    assert any(item["opponent"] == "Lux" for item in recommendations["watch_opponents"])


def test_matchup_summary_cli_json(tmp_path) -> None:
    findings_path = tmp_path / "latest_findings.json"
    findings_path.write_text(json.dumps(_sample_data()), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["summary", "--findings-json", str(findings_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summoner"] == "Player#JP1"
    assert "champion_summaries" in payload
    assert "lane_opponent_pairs" in payload
    assert "opponent_summaries" in payload
    assert "recommendations" in payload


def test_matchup_summary_cli_human_readable(tmp_path) -> None:
    findings_path = tmp_path / "latest_findings.json"
    findings_path.write_text(json.dumps(_sample_data()), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["summary", "--findings-json", str(findings_path)])

    assert result.exit_code == 0
    assert "Champion Summary" in result.stdout
    assert "Zyra" in result.stdout
