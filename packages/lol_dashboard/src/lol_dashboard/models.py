"""Pydantic models for parsing findings JSON into DuckDB payload."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MatchRecord(BaseModel):
    match_id: str
    champion: str
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    cs: int = 0
    vision_score: int = 0
    win: bool = False
    queue_type: str = ""
    game_duration_seconds: int = 1
    timestamp_ms: int = 0
    role: str = ""
    lane_opponents: list[str] = []
    ally_team: list[str] = []
    enemy_team: list[str] = []
    kill_participation: float = 0.0
    damage_physical: int = 0
    damage_magical: int = 0
    damage_true: int = 0
    game_version: str = ""
    cs_per_min: float = 0.0


class FindingRecord(BaseModel):
    category: str
    severity: str
    message: str = ""
    detail: str = ""


class ChampionStatRecord(BaseModel):
    champion: str
    games: int = 0
    wins: int = 0
    win_rate: float = 0.0
    avg_kda: float | None = None
    avg_cs_per_min: float = 0.0


class SnapshotPayload(BaseModel):
    snapshot_id: str
    summoner: str
    generated_at: str
    total_games: int = Field(default=0, ge=0)
    wins: int = Field(default=0, ge=0)
    losses: int = Field(default=0, ge=0)
    win_rate: float = 0.0
    avg_kda: float = 0.0
    avg_cs_per_min: float = 0.0
    matches: list[MatchRecord] = []
    findings: list[FindingRecord] = []
    champion_stats: list[ChampionStatRecord] = []
