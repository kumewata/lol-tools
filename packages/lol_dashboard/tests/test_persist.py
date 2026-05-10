"""Tests for persist.py — classify functions, upsert idempotency, backfill."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lol_dashboard.models import SnapshotPayload, MatchRecord, FindingRecord, ChampionStatRecord
from lol_dashboard.persist import classify_queue, classify_patch, load_snapshot, upsert_snapshot, backfill, sync_latest
from lol_dashboard.schema import init_db


# ---------------------------------------------------------------------------
# classify_queue
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("queue_id,expected", [
    (420, ("ranked_solo", True)),
    ("420", ("ranked_solo", True)),
    (400, ("normal_draft", False)),
    (430, ("normal_blind", False)),
    (440, ("ranked_flex", True)),
    (450, ("aram", False)),
    (700, ("clash", False)),
    (1700, ("arena", False)),
    (9999, ("other", False)),
    ("", ("other", False)),
    (None, ("other", False)),
])
def test_classify_queue(queue_id, expected):
    assert classify_queue(queue_id) == expected


# ---------------------------------------------------------------------------
# classify_patch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gv,expected", [
    ("15.9.123.4567", "15.9"),
    ("14.24.456.7890", "14.24"),
    ("", None),
    (None, None),
    ("bad", None),
    ("1", None),
])
def test_classify_patch(gv, expected):
    assert classify_patch(gv) == expected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(snapshot_id: str = "20260509_181209", summoner: str = "alice#1234") -> SnapshotPayload:
    return SnapshotPayload(
        snapshot_id=snapshot_id,
        summoner=summoner,
        generated_at=snapshot_id,
        total_games=2,
        wins=1,
        losses=1,
        win_rate=0.5,
        avg_kda=2.0,
        avg_cs_per_min=1.5,
        matches=[
            MatchRecord(
                match_id="JP1_100001",
                champion="Zyra",
                kills=0, deaths=2, assists=10,
                cs=20, vision_score=30,
                win=True,
                queue_type="420",
                game_duration_seconds=1800,
                timestamp_ms=1000000,
                role="UTILITY",
                game_version="15.9.123.4567",
                cs_per_min=0.67,
            ),
        ],
        findings=[FindingRecord(category="cs", severity="warning", message="CS low", detail="")],
        champion_stats=[ChampionStatRecord(champion="Zyra", games=2, wins=1, win_rate=0.5, avg_kda=2.0, avg_cs_per_min=0.67)],
    )


# ---------------------------------------------------------------------------
# upsert_snapshot — idempotency
# ---------------------------------------------------------------------------

def test_upsert_idempotent(tmp_path: Path) -> None:
    con = init_db(tmp_path / "test.duckdb")
    payload = _make_payload()
    upsert_snapshot(con, payload)
    upsert_snapshot(con, payload)  # second upsert must not duplicate

    count = con.execute("SELECT COUNT(*) FROM snapshots WHERE snapshot_id = '20260509_181209'").fetchone()[0]
    assert count == 1
    match_count = con.execute("SELECT COUNT(*) FROM matches WHERE snapshot_id = '20260509_181209'").fetchone()[0]
    assert match_count == 1
    con.close()


def test_upsert_multi_summoner(tmp_path: Path) -> None:
    con = init_db(tmp_path / "test.duckdb")
    p1 = _make_payload(summoner="alice#1234")
    p2 = _make_payload(summoner="bob#5678")
    upsert_snapshot(con, p1)
    upsert_snapshot(con, p2)

    count = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    assert count == 2
    con.close()


def test_upsert_derived_columns(tmp_path: Path) -> None:
    con = init_db(tmp_path / "test.duckdb")
    upsert_snapshot(con, _make_payload())
    row = con.execute(
        "SELECT queue_category, is_ranked, patch FROM matches WHERE match_id = 'JP1_100001'"
    ).fetchone()
    assert row == ("ranked_solo", True, "15.9")
    con.close()


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------

def _write_findings(path: Path, snapshot_id: str, summoner: str = "alice#1234") -> None:
    data = {
        "summoner": summoner,
        "total_games": 1, "wins": 1, "losses": 0,
        "win_rate": 1.0, "avg_kda": 3.0, "avg_cs_per_min": 2.0,
        "generated_at": snapshot_id,
        "matches": [],
        "findings": [],
        "champion_stats": [],
    }
    (path / f"findings_{snapshot_id}.json").write_text(json.dumps(data))


def test_backfill_loads_all(tmp_path: Path) -> None:
    db = tmp_path / "lol.duckdb"
    output = tmp_path / "output"
    output.mkdir()
    _write_findings(output, "20260501_120000")
    _write_findings(output, "20260502_120000")

    backfill(db, output)
    con = init_db(db)
    count = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    assert count == 2
    con.close()


def test_backfill_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "lol.duckdb"
    output = tmp_path / "output"
    output.mkdir()
    _write_findings(output, "20260501_120000")

    backfill(db, output)
    backfill(db, output)

    con = init_db(db)
    count = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    assert count == 1
    con.close()


def test_backfill_multi_summoner(tmp_path: Path) -> None:
    db = tmp_path / "lol.duckdb"
    output = tmp_path / "output"
    output.mkdir()
    _write_findings(output, "20260501_120000", summoner="alice#1234")
    # second file for different summoner reuses same snapshot_id — both are valid in different summoner rows
    # but backfill deduplicates by snapshot_id; use different ids
    _write_findings(output, "20260501_130000", summoner="bob#5678")

    backfill(db, output)
    con = init_db(db)
    count = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    assert count == 2
    con.close()


# ---------------------------------------------------------------------------
# sync_latest
# ---------------------------------------------------------------------------

def test_sync_latest(tmp_path: Path) -> None:
    db = tmp_path / "lol.duckdb"
    output = tmp_path / "output"
    output.mkdir()
    data = {
        "summoner": "alice#1234",
        "total_games": 5, "wins": 3, "losses": 2,
        "win_rate": 0.6, "avg_kda": 2.5, "avg_cs_per_min": 1.8,
        "generated_at": "20260510_090000",
        "matches": [], "findings": [], "champion_stats": [],
    }
    (output / "latest_findings.json").write_text(json.dumps(data))

    sync_latest(db, output)
    con = init_db(db)
    count = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    assert count == 1
    con.close()


# ---------------------------------------------------------------------------
# DuckDB lock retry (mock)
# ---------------------------------------------------------------------------

def test_lock_retry_succeeds(tmp_path: Path) -> None:
    db = tmp_path / "lol.duckdb"
    call_count = {"n": 0}

    original_init = init_db

    def mock_init(path):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise duckdb.IOException("lock")
        return original_init(path)

    import duckdb
    with patch("lol_dashboard.persist.init_db", side_effect=mock_init), \
         patch("lol_dashboard.persist.time.sleep"):
        output = tmp_path / "output"
        output.mkdir()
        _write_findings(output, "20260501_120000")
        backfill(db, output)

    assert call_count["n"] == 3


def test_lock_retry_exhausted(tmp_path: Path) -> None:
    import duckdb

    def always_fail(path):
        raise duckdb.IOException("lock")

    with patch("lol_dashboard.persist.init_db", side_effect=always_fail), \
         patch("lol_dashboard.persist.time.sleep"):
        output = tmp_path / "output"
        output.mkdir()
        _write_findings(output, "20260501_120000")
        with pytest.raises(duckdb.IOException):
            backfill(tmp_path / "lol.duckdb", output)
