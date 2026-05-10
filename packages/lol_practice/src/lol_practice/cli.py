"""Typer subapp for `lol-tools practice` (list / show / status)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from lol_practice import store
from lol_practice.compare import FindingRow, evaluate_progress
from lol_practice.models import Plan

console = Console()
app = typer.Typer(help="練習プラン CLI（生成はスキル側、ここでは閲覧と進捗確認）")

# Repo layout:
# packages/lol_practice/src/lol_practice/cli.py
# 4 parents up = repo root.
_PACKAGE_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _PACKAGE_DIR.parent.parent
_ENV_PATH = _REPO_ROOT / ".env"
_DB_PATH = _REPO_ROOT / "packages" / "lol_dashboard" / "data" / "lol_history.duckdb"


def _resolve_target_summoner() -> str:
    """Return DEFAULT_RIOT_ID from .env, or fail with a clear message."""
    load_dotenv(_ENV_PATH)
    value = os.environ.get("DEFAULT_RIOT_ID", "").strip()
    if not value or "#" not in value:
        console.print(
            "[red]Error:[/] DEFAULT_RIOT_ID が .env に設定されていません。"
            "`uv run lol-tools init` または `.env` に `DEFAULT_RIOT_ID=ゲーム名#タグライン` を追加してください。"
        )
        raise typer.Exit(1)
    return value


def _resolve_db_path() -> Path:
    return _DB_PATH


def _db_exists(path: Path) -> bool:
    return path.exists()


def _load_current_findings(db_path: Path, summoner: str) -> list[FindingRow]:
    """Load latest snapshot's findings for the given summoner from DuckDB.

    Read-only. Returns [] if the DuckDB file does not exist or has no rows.
    """
    if not _db_exists(db_path):
        return []
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            WITH latest AS (
                SELECT snapshot_id
                FROM snapshots
                WHERE summoner = ?
                ORDER BY generated_at DESC
                LIMIT 1
            )
            SELECT f.snapshot_id, f.summoner, f.category, f.severity
            FROM findings f
            JOIN latest l ON f.snapshot_id = l.snapshot_id
            WHERE f.summoner = ?
            """,
            [summoner, summoner],
        ).fetchall()
    finally:
        con.close()
    return [
        FindingRow(snapshot_id=r[0], summoner=r[1], category=r[2], severity=r[3])
        for r in rows
    ]


@app.command("list")
def list_plans_cmd() -> None:
    """plans/ 配下のプランを日付降順で一覧表示する。"""
    files = store.list_plans()
    if not files:
        console.print("[yellow]該当するプランはありません[/]")
        return

    table = Table(title="練習プラン一覧", show_header=True)
    table.add_column("日付")
    table.add_column("ファイル")
    for path in files:
        table.add_row(path.stem, str(path))
    console.print(table)


@app.command("show")
def show_plan(
    date: str | None = typer.Option(None, "--date", help="表示する日付（YYYY-MM-DD）。省略時は最新"),
) -> None:
    """指定日（省略時は最新）のプランを Markdown として表示する。"""
    plan = _find_plan(date)
    if plan is None:
        console.print("[yellow]該当するプランはありません[/]")
        return
    md_text = store.to_markdown(plan)
    console.print(Markdown(md_text))


@app.command("status")
def status(
    date: str | None = typer.Option(None, "--date", help="判定対象の日付。省略時は最新"),
    json_output: bool = typer.Option(False, "--json", help="JSON で出力（スキルが parse する想定）"),
) -> None:
    """active プランと最新 findings を比較し、進捗判定を出力する。"""
    files = store.list_plans()
    if not files:
        if json_output:
            print(json.dumps({"plans": []}, ensure_ascii=False))
        else:
            console.print("[yellow]該当するプランはありません[/]")
        return

    plan = _find_plan(date)
    if plan is None:
        if json_output:
            print(json.dumps({"plans": []}, ensure_ascii=False))
        else:
            console.print(f"[yellow]日付 {date} のプランは見つかりません[/]")
        return

    summoner = _resolve_target_summoner()
    db_path = _resolve_db_path()
    findings = _load_current_findings(db_path, summoner)
    verdicts = evaluate_progress(plan, findings)

    if json_output:
        payload = {
            "plans": [
                {
                    "date": plan.date,
                    "based_on_snapshot": plan.based_on_snapshot,
                    "target_summoner": plan.target_summoner,
                    "verdicts": [v.model_dump() for v in verdicts],
                }
            ]
        }
        print(json.dumps(payload, ensure_ascii=False))
        return

    table = Table(title=f"進捗判定 ({plan.date})", show_header=True)
    table.add_column("category")
    table.add_column("元 severity")
    table.add_column("現在 severity")
    table.add_column("判定")
    for v in verdicts:
        table.add_row(
            v.category,
            v.source_severity,
            v.current_severity or "（消失）",
            v.status,
        )
    console.print(table)


def _find_plan(date: str | None) -> Plan | None:
    if date is None:
        return store.latest_plan()
    files = store.list_plans()
    for path in files:
        if path.stem == date:
            return store.load_plan(path)
    return None


__all__ = ["app"]
