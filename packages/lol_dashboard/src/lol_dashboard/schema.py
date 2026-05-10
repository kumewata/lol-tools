"""DuckDB schema initialization for lol_history."""

from __future__ import annotations

from pathlib import Path

import duckdb

_DDL = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id     TEXT      NOT NULL,
    summoner        TEXT      NOT NULL,
    puuid           TEXT,
    generated_at    TEXT      NOT NULL,
    total_games     INTEGER,
    wins            INTEGER,
    losses          INTEGER,
    win_rate        DOUBLE,
    avg_kda         DOUBLE,
    avg_cs_per_min  DOUBLE,
    PRIMARY KEY (snapshot_id, summoner)
);

CREATE TABLE IF NOT EXISTS matches (
    snapshot_id            TEXT    NOT NULL,
    summoner               TEXT    NOT NULL,
    match_id               TEXT    NOT NULL,
    champion               TEXT,
    role                   TEXT,
    queue_type             TEXT,
    queue_category         TEXT,
    is_ranked              BOOLEAN,
    game_version           TEXT,
    patch                  TEXT,
    win                    BOOLEAN,
    kills                  INTEGER,
    deaths                 INTEGER,
    assists                INTEGER,
    cs                     INTEGER,
    cs_per_min             DOUBLE,
    vision_score           INTEGER,
    kill_participation     DOUBLE,
    game_duration_seconds  INTEGER,
    timestamp_ms           BIGINT,
    lane_opponents         JSON,
    ally_team              JSON,
    enemy_team             JSON,
    damage_physical        INTEGER,
    damage_magical         INTEGER,
    damage_true            INTEGER,
    PRIMARY KEY (snapshot_id, summoner, match_id)
);

CREATE TABLE IF NOT EXISTS findings (
    snapshot_id  TEXT NOT NULL,
    summoner     TEXT NOT NULL,
    category     TEXT NOT NULL,
    severity     TEXT NOT NULL,
    message      TEXT,
    detail       TEXT
);

CREATE TABLE IF NOT EXISTS champion_stats (
    snapshot_id     TEXT    NOT NULL,
    summoner        TEXT    NOT NULL,
    champion        TEXT    NOT NULL,
    games           INTEGER,
    wins            INTEGER,
    win_rate        DOUBLE,
    avg_kda         DOUBLE,
    avg_cs_per_min  DOUBLE,
    PRIMARY KEY (snapshot_id, summoner, champion)
);
"""


def init_db(path: str | Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(path))
    for stmt in _DDL.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)
    migrate_db(con)
    return con


def migrate_db(con: duckdb.DuckDBPyConnection) -> None:
    pass
