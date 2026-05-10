"""Tests for schema.py — idempotent init_db."""

import tempfile
from pathlib import Path

import duckdb

from lol_dashboard.schema import init_db


def test_init_db_creates_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.duckdb"
    con = init_db(db)
    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert tables == {"snapshots", "matches", "findings", "champion_stats"}
    con.close()


def test_init_db_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.duckdb"
    con1 = init_db(db)
    con1.close()
    # Second call should not raise
    con2 = init_db(db)
    tables = {row[0] for row in con2.execute("SHOW TABLES").fetchall()}
    assert "snapshots" in tables
    con2.close()
