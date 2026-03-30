"""Tests for advisor module."""

from lol_review.advisor import analyze_findings, Finding
from lol_review.models import AnalysisResult, MatchSummary, PlayerStats, ChampionStats


def _make_match(
    match_id: str,
    champion: str,
    kills: int,
    deaths: int,
    assists: int,
    cs: int,
    win: bool,
    duration: int = 1800,
    vision_score: int = 20,
    damage: int = 20000,
) -> MatchSummary:
    return MatchSummary(
        match_id=match_id,
        champion=champion,
        kills=kills,
        deaths=deaths,
        assists=assists,
        cs=cs,
        gold_earned=10000,
        total_damage_dealt=damage,
        vision_score=vision_score,
        win=win,
        game_mode="CLASSIC",
        queue_type="420",
        game_duration_seconds=duration,
        timestamp_ms=1711700000000,
    )


def _make_player_stats(
    match_id: str,
    kill_ts: list[int] | None = None,
    death_ts: list[int] | None = None,
    assist_ts: list[int] | None = None,
    item_purchases: list[dict] | None = None,
) -> PlayerStats:
    return PlayerStats(
        match_id=match_id,
        gold_timeline=[500 * i for i in range(30)],
        gold_diff_timeline=[0] * 30,
        kill_timestamps=kill_ts or [],
        death_timestamps=death_ts or [],
        assist_timestamps=assist_ts or [],
        objective_events=[],
        item_purchases=item_purchases or [],
    )


def _make_result(
    matches: list[MatchSummary],
    player_stats: list[PlayerStats],
) -> AnalysisResult:
    champions = sorted(set(m.champion for m in matches))
    champion_stats = [ChampionStats.from_matches(c, matches) for c in champions]
    total = len(matches)
    wins = sum(1 for m in matches if m.win)
    import math
    finite_kdas = [m.kda for m in matches if math.isfinite(m.kda)]
    avg_kda = sum(finite_kdas) / len(finite_kdas) if finite_kdas else 0.0
    avg_cs = sum(m.cs_per_min for m in matches) / total if total > 0 else 0.0
    return AnalysisResult(
        summoner_name="test",
        tag_line="JP1",
        total_games=total,
        wins=wins,
        losses=total - wins,
        win_rate=wins / total if total > 0 else 0.0,
        avg_kda=avg_kda,
        avg_cs_per_min=avg_cs,
        matches=matches,
        champion_stats=champion_stats,
        player_stats=player_stats,
    )


def test_finding_model():
    f = Finding(category="cs", severity="warning", message="CS低い", detail="5.0/min")
    assert f.category == "cs"
    assert f.severity == "warning"


def test_low_cs_detected():
    matches = [_make_match("m1", "Jinx", 5, 2, 3, 90, True)]  # 90cs/30min = 3.0/min
    ps = [_make_player_stats("m1")]
    result = _make_result(matches, ps)
    findings = analyze_findings(result)
    cs_findings = [f for f in findings if f.category == "cs"]
    assert len(cs_findings) > 0


def test_good_cs_no_finding():
    matches = [_make_match("m1", "Jinx", 5, 2, 3, 250, True)]  # 250cs/30min = 8.3/min
    ps = [_make_player_stats("m1")]
    result = _make_result(matches, ps)
    findings = analyze_findings(result)
    cs_findings = [f for f in findings if f.category == "cs"]
    assert len(cs_findings) == 0


def test_early_deaths_detected():
    matches = [_make_match("m1", "Jinx", 2, 5, 3, 150, False)]
    # Deaths at 3min and 5min (early game)
    ps = [_make_player_stats("m1", death_ts=[180, 300, 360, 420, 480])]
    result = _make_result(matches, ps)
    findings = analyze_findings(result)
    death_findings = [f for f in findings if f.category == "deaths"]
    assert len(death_findings) > 0


def test_low_vision_detected():
    matches = [_make_match("m1", "Jinx", 5, 2, 3, 200, True, vision_score=5)]
    ps = [_make_player_stats("m1")]
    result = _make_result(matches, ps)
    findings = analyze_findings(result)
    vision_findings = [f for f in findings if f.category == "vision"]
    assert len(vision_findings) > 0


def test_late_core_detected():
    matches = [_make_match("m1", "Jinx", 5, 2, 3, 200, True, duration=2400)]
    # First core at 25min (1500s)
    ps = [_make_player_stats("m1", item_purchases=[
        {"item_id": 1001, "timestamp": 60, "item_name": "素材", "item_type": "component", "item_type_label": "素材"},
        {"item_id": 3031, "timestamp": 1500, "item_name": "IE", "item_type": "completed", "item_type_label": "コア（1個目）"},
    ])]
    result = _make_result(matches, ps)
    findings = analyze_findings(result)
    build_findings = [f for f in findings if f.category == "build"]
    assert len(build_findings) > 0


def test_no_findings_good_game():
    matches = [_make_match("m1", "Jinx", 10, 1, 8, 280, True, vision_score=40)]
    ps = [_make_player_stats("m1", item_purchases=[
        {"item_id": 3031, "timestamp": 600, "item_name": "IE", "item_type": "completed", "item_type_label": "コア（1個目）"},
    ])]
    result = _make_result(matches, ps)
    findings = analyze_findings(result)
    # Should have very few or no findings
    critical = [f for f in findings if f.severity == "critical"]
    assert len(critical) == 0
