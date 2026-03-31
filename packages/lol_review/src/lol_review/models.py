"""Pydantic data models for LoL match review."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, computed_field


class MatchSummary(BaseModel):
    """Summary of a single match."""

    match_id: str
    champion: str
    kills: int = Field(ge=0)
    deaths: int = Field(ge=0)
    assists: int = Field(ge=0)
    cs: int = Field(ge=0)
    gold_earned: int = Field(ge=0)
    total_damage_dealt: int = Field(ge=0)
    vision_score: int = Field(ge=0)
    win: bool
    game_mode: str
    queue_type: str
    game_duration_seconds: int = Field(gt=0)
    timestamp_ms: int = Field(ge=0)
    role: str = ""  # TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY
    lane_opponents: list[str] = []  # 対面チャンピオン（BOT/UTILITYは2人）
    ally_team: list[str] = []  # 味方チャンピオン一覧
    enemy_team: list[str] = []  # 敵チャンピオン一覧
    kill_participation: float = 0.0  # (K+A) / チーム全キル
    damage_physical: int = Field(default=0, ge=0)
    damage_magical: int = Field(default=0, ge=0)
    damage_true: int = Field(default=0, ge=0)

    @computed_field  # type: ignore[misc]
    @property
    def kda(self) -> float:
        """(kills + assists) / deaths; infinity when deaths == 0."""
        if self.deaths == 0:
            return float("inf")
        return (self.kills + self.assists) / self.deaths

    @computed_field  # type: ignore[misc]
    @property
    def cs_per_min(self) -> float:
        """CS per minute."""
        minutes = self.game_duration_seconds / 60
        return self.cs / minutes


class PlayerStats(BaseModel):
    """Timeline data for a single match."""

    match_id: str
    gold_timeline: list[int]
    gold_diff_timeline: list[int]
    position_timeline: list[dict[str, Any]] = []  # {"timestamp": int, "x": int, "y": int}
    jungle_cs_timeline: list[dict[str, Any]] = []  # {"timestamp": int, "jungle_cs": int}
    kill_timestamps: list[int]
    death_timestamps: list[int]
    assist_timestamps: list[int]
    objective_events: list[dict[str, Any]]
    item_purchases: list[dict[str, Any]]  # {"item_id": int, "timestamp": int, "item_name": str}
    skill_level_ups: list[dict[str, Any]] = []  # {"timestamp": int, "skill": "Q/W/E/R", "type": str}
    level_ups: list[dict[str, Any]] = []  # {"timestamp": int, "level": int}
    opponent_level_ups: list[dict[str, Any]] = []  # {"timestamp": int, "level": int, "participant_id": int}


class ChampionStats(BaseModel):
    """Aggregated statistics for a single champion."""

    champion: str
    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    win_rate: float
    avg_kda: float
    avg_cs_per_min: float

    @classmethod
    def from_matches(cls, champion: str, matches: list[MatchSummary]) -> "ChampionStats":
        """Aggregate stats from a list of MatchSummary objects.

        Only matches whose champion field equals `champion` are used.
        """
        filtered = [m for m in matches if m.champion == champion]
        games = len(filtered)
        wins = sum(1 for m in filtered if m.win)
        win_rate = wins / games if games > 0 else 0.0

        kdas = [m.kda for m in filtered]
        if any(k == float("inf") for k in kdas):
            avg_kda = float("inf")
        else:
            avg_kda = sum(kdas) / games if games > 0 else 0.0

        avg_cs_per_min = (
            sum(m.cs_per_min for m in filtered) / games if games > 0 else 0.0
        )

        return cls(
            champion=champion,
            games=games,
            wins=wins,
            win_rate=win_rate,
            avg_kda=avg_kda,
            avg_cs_per_min=avg_cs_per_min,
        )


class AnalysisResult(BaseModel):
    """Full analysis result for a summoner."""

    summoner_name: str
    tag_line: str
    total_games: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    win_rate: float
    avg_kda: float
    avg_cs_per_min: float
    matches: list[MatchSummary]
    champion_stats: list[ChampionStats]
    player_stats: list[PlayerStats]
    game_duration_analysis: list[dict[str, Any]] = []  # [{"label": "~20min", "games": 3, "wins": 2, "win_rate": 0.67}]
