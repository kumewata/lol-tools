"""Analysis engine that aggregates match data into AnalysisResult."""

from __future__ import annotations

import math

from lol_review.models import AnalysisResult, ChampionStats, MatchSummary, PlayerStats


def analyze_matches(
    summoner_name: str,
    tag_line: str,
    matches: list[MatchSummary],
    player_stats: list[PlayerStats],
) -> AnalysisResult:
    """Aggregate match data into a structured AnalysisResult.

    Args:
        summoner_name: The summoner's name.
        tag_line: The summoner's tag line (e.g. "EUW", "NA1").
        matches: List of MatchSummary objects to analyse.
        player_stats: Timeline data for each match (passed through).

    Returns:
        AnalysisResult with aggregated statistics.
    """
    total = len(matches)
    wins = sum(1 for m in matches if m.win)
    losses = total - wins
    win_rate = wins / total if total > 0 else 0.0

    # Average KDA, excluding infinite values
    finite_kdas = [m.kda for m in matches if math.isfinite(m.kda)]
    avg_kda = sum(finite_kdas) / len(finite_kdas) if finite_kdas else 0.0

    # Average CS per minute over all matches
    avg_cs_per_min = (
        sum(m.cs_per_min for m in matches) / total if total > 0 else 0.0
    )

    # Champion stats sorted by games descending
    unique_champions = dict.fromkeys(m.champion for m in matches)
    champion_stats: list[ChampionStats] = sorted(
        (ChampionStats.from_matches(champ, matches) for champ in unique_champions),
        key=lambda cs: cs.games,
        reverse=True,
    )

    # Game duration analysis
    game_duration_analysis = _analyze_game_duration(matches)

    return AnalysisResult(
        summoner_name=summoner_name,
        tag_line=tag_line,
        total_games=total,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        avg_kda=avg_kda,
        avg_cs_per_min=avg_cs_per_min,
        matches=matches,
        champion_stats=champion_stats,
        player_stats=player_stats,
        game_duration_analysis=game_duration_analysis,
    )


def _analyze_game_duration(matches: list[MatchSummary]) -> list[dict]:
    """Group matches by duration and calculate win rates."""
    buckets = [
        ("~20min", 0, 1200),
        ("20~30min", 1200, 1800),
        ("30~40min", 1800, 2400),
        ("40min~", 2400, float("inf")),
    ]
    result = []
    for label, lo, hi in buckets:
        bucket_matches = [m for m in matches if lo <= m.game_duration_seconds < hi]
        games = len(bucket_matches)
        if games == 0:
            continue
        wins = sum(1 for m in bucket_matches if m.win)
        result.append({
            "label": label,
            "games": games,
            "wins": wins,
            "win_rate": wins / games,
        })
    return result
