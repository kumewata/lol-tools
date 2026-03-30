"""Tests for the analysis engine."""

from __future__ import annotations

import pytest

from lol_review.models import AnalysisResult, MatchSummary, PlayerStats
from lol_review.analyzer import analyze_matches


def _make_match(
    match_id: str,
    champion: str,
    kills: int,
    deaths: int,
    assists: int,
    cs: int,
    win: bool,
    queue: str = "420",
) -> MatchSummary:
    """Helper to create MatchSummary with sensible defaults."""
    return MatchSummary(
        match_id=match_id,
        champion=champion,
        kills=kills,
        deaths=deaths,
        assists=assists,
        cs=cs,
        gold_earned=10000,
        total_damage_dealt=20000,
        vision_score=20,
        win=win,
        game_mode="CLASSIC",
        queue_type=queue,
        game_duration_seconds=1800,
        timestamp_ms=1711700000000,
    )


def test_analyze_basic_stats() -> None:
    """3 matches, 2 wins: verify total_games, wins, losses, win_rate."""
    matches = [
        _make_match("m1", "Jinx", 5, 2, 3, 200, win=True),
        _make_match("m2", "Jinx", 3, 4, 1, 180, win=False),
        _make_match("m3", "Lux", 7, 1, 5, 150, win=True),
    ]
    result = analyze_matches("TestPlayer", "EUW", matches, [])

    assert isinstance(result, AnalysisResult)
    assert result.summoner_name == "TestPlayer"
    assert result.tag_line == "EUW"
    assert result.total_games == 3
    assert result.wins == 2
    assert result.losses == 1
    assert pytest.approx(result.win_rate, abs=1e-6) == 2 / 3


def test_analyze_avg_kda() -> None:
    """avg_kda excludes infinite KDA values."""
    matches = [
        # deaths=0 → KDA = inf (excluded)
        _make_match("m1", "Jinx", 5, 0, 3, 200, win=True),
        # KDA = (3+1)/4 = 1.0
        _make_match("m2", "Jinx", 3, 4, 1, 180, win=False),
    ]
    result = analyze_matches("TestPlayer", "EUW", matches, [])

    # Only m2's KDA (1.0) should be averaged
    assert pytest.approx(result.avg_kda, abs=1e-6) == 1.0


def test_analyze_avg_cs_per_min() -> None:
    """avg_cs_per_min averages cs_per_min across all matches."""
    # game_duration_seconds=1800 → 30 min
    # m1: cs=300 → 10.0 cs/min
    # m2: cs=150 → 5.0 cs/min
    matches = [
        _make_match("m1", "Jinx", 5, 2, 3, 300, win=True),
        _make_match("m2", "Lux", 3, 4, 1, 150, win=False),
    ]
    result = analyze_matches("TestPlayer", "EUW", matches, [])

    assert pytest.approx(result.avg_cs_per_min, abs=1e-6) == 7.5


def test_analyze_champion_stats() -> None:
    """2 Jinx + 1 Lux: verify champion grouping and sorting by games desc."""
    matches = [
        _make_match("m1", "Jinx", 5, 2, 3, 200, win=True),
        _make_match("m2", "Jinx", 3, 4, 1, 180, win=False),
        _make_match("m3", "Lux", 7, 1, 5, 150, win=True),
    ]
    result = analyze_matches("TestPlayer", "EUW", matches, [])

    assert len(result.champion_stats) == 2
    # Jinx (2 games) should come first
    assert result.champion_stats[0].champion == "Jinx"
    assert result.champion_stats[0].games == 2
    assert result.champion_stats[1].champion == "Lux"
    assert result.champion_stats[1].games == 1


def test_analyze_empty() -> None:
    """Empty matches: all counts and rates should be zero."""
    result = analyze_matches("TestPlayer", "EUW", [], [])

    assert result.total_games == 0
    assert result.wins == 0
    assert result.losses == 0
    assert result.win_rate == 0.0
    assert result.avg_kda == 0.0
    assert result.avg_cs_per_min == 0.0
    assert result.champion_stats == []
    assert result.matches == []


def test_analyze_all_infinite_kda() -> None:
    """When all KDAs are infinite, avg_kda should be 0.0."""
    matches = [
        _make_match("m1", "Jinx", 5, 0, 3, 200, win=True),
        _make_match("m2", "Lux", 3, 0, 1, 180, win=True),
    ]
    result = analyze_matches("TestPlayer", "EUW", matches, [])

    assert result.avg_kda == 0.0


def test_analyze_player_stats_passthrough() -> None:
    """player_stats should be passed through to AnalysisResult."""
    ps = PlayerStats(
        match_id="m1",
        gold_timeline=[1000, 2000],
        gold_diff_timeline=[100, 200],
        kill_timestamps=[300],
        death_timestamps=[],
        assist_timestamps=[120],
        objective_events=[],
        item_purchases=[],
    )
    result = analyze_matches("TestPlayer", "EUW", [], [ps])

    assert len(result.player_stats) == 1
    assert result.player_stats[0].match_id == "m1"
