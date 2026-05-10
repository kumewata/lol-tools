"""JSON → DuckDB persistence for lol_dashboard."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import duckdb

from .models import SnapshotPayload
from .schema import init_db

logger = logging.getLogger(__name__)

_QUEUE_MAP: dict[int, tuple[str, bool]] = {
    400: ("normal_draft", False),
    420: ("ranked_solo", True),
    430: ("normal_blind", False),
    440: ("ranked_flex", True),
    450: ("aram", False),
    480: ("normal_quickplay", False),  # Swiftplay/Quickplay (Riot 2024+ normal queue)
    700: ("clash", False),
    1700: ("arena", False),
}


def classify_queue(queue_type: str | int) -> tuple[str, bool]:
    try:
        qid = int(queue_type)
    except (ValueError, TypeError):
        logger.warning("classify_queue: unknown queue_type %r, falling back to 'other'", queue_type)
        return ("other", False)
    result = _QUEUE_MAP.get(qid)
    if result is None:
        logger.warning("classify_queue: unknown queue_id %d, falling back to 'other'", qid)
        return ("other", False)
    return result


def classify_patch(game_version: str | None) -> str | None:
    if not game_version:
        return None
    parts = game_version.split(".")
    if len(parts) < 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        logger.warning("classify_patch: unexpected game_version format %r", game_version)
        return None
    return f"{parts[0]}.{parts[1]}"


def load_snapshot(json_path: str | Path) -> SnapshotPayload:
    path = Path(json_path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    name = path.stem  # e.g. "findings_20260509_181209" or "latest_findings"
    if name.startswith("findings_"):
        snapshot_id = name[len("findings_"):]
    else:
        # latest_findings.json — use generated_at as snapshot_id
        snapshot_id = data.get("generated_at", name)

    return SnapshotPayload(
        snapshot_id=snapshot_id,
        summoner=data["summoner"],
        generated_at=data.get("generated_at", snapshot_id),
        total_games=data.get("total_games", 0),
        wins=data.get("wins", 0),
        losses=data.get("losses", 0),
        win_rate=data.get("win_rate", 0.0),
        avg_kda=data.get("avg_kda", 0.0),
        avg_cs_per_min=data.get("avg_cs_per_min", 0.0),
        matches=data.get("matches", []),
        findings=data.get("findings", []),
        champion_stats=data.get("champion_stats", []),
    )


def upsert_snapshot(con: duckdb.DuckDBPyConnection, payload: SnapshotPayload) -> None:
    sid = payload.snapshot_id
    summ = payload.summoner

    con.execute("BEGIN TRANSACTION")
    try:
        _upsert_snapshot_inner(con, payload, sid, summ)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def _upsert_snapshot_inner(
    con: duckdb.DuckDBPyConnection, payload: SnapshotPayload, sid: str, summ: str
) -> None:
    # DELETE existing data for this (snapshot_id, summoner) pair
    con.execute("DELETE FROM snapshots      WHERE snapshot_id = ? AND summoner = ?", [sid, summ])
    con.execute("DELETE FROM matches        WHERE snapshot_id = ? AND summoner = ?", [sid, summ])
    con.execute("DELETE FROM findings       WHERE snapshot_id = ? AND summoner = ?", [sid, summ])
    con.execute("DELETE FROM champion_stats WHERE snapshot_id = ? AND summoner = ?", [sid, summ])

    # snapshots
    con.execute(
        """
        INSERT INTO snapshots
            (snapshot_id, summoner, generated_at, total_games, wins, losses, win_rate, avg_kda, avg_cs_per_min)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [sid, summ, payload.generated_at, payload.total_games, payload.wins,
         payload.losses, payload.win_rate, payload.avg_kda, payload.avg_cs_per_min],
    )

    # matches
    for m in payload.matches:
        queue_category, is_ranked = classify_queue(m.queue_type)
        patch = classify_patch(m.game_version) if m.game_version else None
        game_version = m.game_version if m.game_version else None
        con.execute(
            """
            INSERT INTO matches (
                snapshot_id, summoner, match_id, champion, role,
                queue_type, queue_category, is_ranked,
                game_version, patch,
                win, kills, deaths, assists, cs, cs_per_min,
                vision_score, kill_participation, game_duration_seconds, timestamp_ms,
                lane_opponents, ally_team, enemy_team,
                damage_physical, damage_magical, damage_true
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?
            )
            """,
            [
                sid, summ, m.match_id, m.champion, m.role,
                m.queue_type, queue_category, is_ranked,
                game_version, patch,
                m.win, m.kills, m.deaths, m.assists, m.cs, m.cs_per_min,
                m.vision_score, m.kill_participation, m.game_duration_seconds, m.timestamp_ms,
                json.dumps(m.lane_opponents), json.dumps(m.ally_team), json.dumps(m.enemy_team),
                m.damage_physical, m.damage_magical, m.damage_true,
            ],
        )

    # findings
    for f in payload.findings:
        con.execute(
            "INSERT INTO findings (snapshot_id, summoner, category, severity, message, detail) VALUES (?, ?, ?, ?, ?, ?)",
            [sid, summ, f.category, f.severity, f.message, f.detail],
        )

    # champion_stats
    for cs in payload.champion_stats:
        con.execute(
            """
            INSERT INTO champion_stats
                (snapshot_id, summoner, champion, games, wins, win_rate, avg_kda, avg_cs_per_min)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [sid, summ, cs.champion, cs.games, cs.wins, cs.win_rate, cs.avg_kda, cs.avg_cs_per_min],
        )


def _open_db_with_retry(db_path: Path) -> duckdb.DuckDBPyConnection:
    delays = [1, 2, 4]
    last_exc: Exception | None = None
    for attempt, delay in enumerate(delays, 1):
        try:
            return init_db(db_path)
        except duckdb.IOException as e:
            last_exc = e
            if attempt < len(delays):
                logger.warning(
                    "DuckDB lock attempt %d/%d failed: %s — retrying in %ds",
                    attempt, len(delays), e, delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "DuckDB lock could not be acquired after %d attempts: %s",
                    len(delays), e,
                )
    raise last_exc  # type: ignore[misc]


def backfill(db_path: str | Path, output_dir: str | Path) -> None:
    output = Path(output_dir)
    files = sorted(output.glob("findings_*.json"))
    if not files:
        logger.warning("backfill: no findings_*.json found in %s", output)
        return

    seen_keys: set[tuple[str, str]] = set()
    con = _open_db_with_retry(Path(db_path))
    try:
        for f in files:
            payload = load_snapshot(f)
            key = (payload.snapshot_id, payload.summoner)
            if key in seen_keys:
                logger.warning(
                    "backfill: duplicate (snapshot_id=%r, summoner=%r) from %s — skipping",
                    payload.snapshot_id, payload.summoner, f.name,
                )
                continue
            seen_keys.add(key)
            upsert_snapshot(con, payload)
            logger.info("backfill: loaded %s (snapshot_id=%s, summoner=%s)", f.name, payload.snapshot_id, payload.summoner)
    finally:
        con.close()


def sync_latest(db_path: str | Path, output_dir: str | Path) -> None:
    latest = Path(output_dir) / "latest_findings.json"
    if not latest.exists():
        logger.warning("sync_latest: %s not found", latest)
        return
    con = _open_db_with_retry(Path(db_path))
    try:
        payload = load_snapshot(latest)
        upsert_snapshot(con, payload)
        logger.info("sync_latest: loaded snapshot_id=%s for summoner=%s", payload.snapshot_id, payload.summoner)
    finally:
        con.close()
