"""Tests for lol_practice.cli (TDD)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner


@pytest.fixture
def sample_plan():
    from lol_practice.models import Plan, PlanItem

    return Plan(
        date="2026-05-10",
        generated_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
        based_on_snapshot="snap_1",
        target_summoner="kumewata#JP1",
        status="active",
        items=[
            PlanItem(
                category="cs",
                severity_at_creation="critical",
                source_finding_message="x",
                practice_points="y",
                progress="pending",
            )
        ],
    )


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    from lol_practice import cli, store

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    db_path = tmp_path / "db.duckdb"

    monkeypatch.setattr(store, "_PLANS_DIR", plans_dir)
    monkeypatch.setattr(cli, "_resolve_db_path", lambda: db_path)
    monkeypatch.setattr(
        cli, "_resolve_target_summoner", lambda: "kumewata#JP1"
    )
    return plans_dir, db_path


def test_list_when_empty(isolated_dirs):
    from lol_practice.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "プラン" in result.stdout or "plans" in result.stdout.lower() or "該当" in result.stdout


def test_list_shows_plans(isolated_dirs, sample_plan):
    from lol_practice import store
    from lol_practice.cli import app

    store.save_plan(sample_plan)
    runner = CliRunner()
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "2026-05-10" in result.stdout


def test_show_displays_active_plan(isolated_dirs, sample_plan):
    from lol_practice import store
    from lol_practice.cli import app

    store.save_plan(sample_plan)
    runner = CliRunner()
    result = runner.invoke(app, ["show"])
    assert result.exit_code == 0
    assert "2026-05-10" in result.stdout
    assert "cs" in result.stdout


def test_show_with_date_option(isolated_dirs, sample_plan):
    from lol_practice import store
    from lol_practice.cli import app

    store.save_plan(sample_plan)
    runner = CliRunner()
    result = runner.invoke(app, ["show", "--date", "2026-05-10"])
    assert result.exit_code == 0
    assert "2026-05-10" in result.stdout


def test_show_with_no_plans_returns_zero(isolated_dirs):
    from lol_practice.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["show"])
    assert result.exit_code == 0


def test_status_json_when_no_plans(isolated_dirs):
    from lol_practice.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {"plans": []}


def test_status_json_when_db_missing(isolated_dirs, sample_plan):
    """DuckDB ファイルが無くてもプラン情報だけ返す（current_findings なし）。"""
    from lol_practice import store
    from lol_practice.cli import app

    store.save_plan(sample_plan)
    runner = CliRunner()
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["plans"][0]["date"] == "2026-05-10"
    # DuckDB がないので verdicts は finding 不在として done になる
    verdicts = payload["plans"][0]["verdicts"]
    assert verdicts[0]["category"] == "cs"
    assert verdicts[0]["status"] == "done"


def test_status_json_with_findings(isolated_dirs, sample_plan, monkeypatch):
    """DuckDB read を mock して、findings に基づく verdict を確認。"""
    from lol_practice import cli, store
    from lol_practice.cli import app
    from lol_practice.compare import FindingRow

    store.save_plan(sample_plan)

    def fake_load(db_path, summoner):
        return [
            FindingRow(
                snapshot_id="snap_new",
                summoner=summoner,
                category="cs",
                severity="warning",
            )
        ]

    monkeypatch.setattr(cli, "_load_current_findings", fake_load)
    monkeypatch.setattr(cli, "_db_exists", lambda p: True)

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["plans"][0]["verdicts"][0]["status"] == "improving"


def test_status_json_with_date_option(isolated_dirs, sample_plan):
    from lol_practice import store
    from lol_practice.cli import app

    store.save_plan(sample_plan)
    runner = CliRunner()
    result = runner.invoke(app, ["status", "--date", "2026-05-10", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["plans"][0]["date"] == "2026-05-10"


def test_status_human_readable_default(isolated_dirs, sample_plan):
    from lol_practice import store
    from lol_practice.cli import app

    store.save_plan(sample_plan)
    runner = CliRunner()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    # 人間可読モード（JSON ではない）
    assert "{" not in result.stdout.split("\n")[0] or "cs" in result.stdout
