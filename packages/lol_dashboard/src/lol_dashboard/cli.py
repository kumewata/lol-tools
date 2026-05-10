"""Dashboard subcommand group for lol-tools."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

console = Console()
app = typer.Typer(help="成長トレンドダッシュボード（DuckDB + Evidence.dev）")

# packages/lol_dashboard/src/lol_dashboard/cli.py → 3 parents up = packages/lol_dashboard/
_PACKAGE_DIR = Path(__file__).parent.parent.parent
_REPO_ROOT = _PACKAGE_DIR.parent.parent
_ENV_PATH = _REPO_ROOT / ".env"
_OUTPUT_DIR = _REPO_ROOT / "packages" / "lol_review" / "output"
_DB_PATH = _PACKAGE_DIR / "data" / "lol_history.duckdb"
_EVIDENCE_DIR = _PACKAGE_DIR / "evidence"
_TARGET_SUMMONER_SQL = _EVIDENCE_DIR / "sources" / "lol_history" / "target_summoner.sql"


def _ensure_db_dir() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)


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


def _write_target_summoner_sql() -> None:
    """Generate sources/lol_history/target_summoner.sql from DEFAULT_RIOT_ID.

    Pages reference the resulting one-row table via a subquery. The file is
    gitignored because it embeds a per-user identifier.
    """
    summoner = _resolve_target_summoner()
    # Single-quote escape: SQL standard doubles single quotes.
    safe = summoner.replace("'", "''")
    _TARGET_SUMMONER_SQL.parent.mkdir(parents=True, exist_ok=True)
    _TARGET_SUMMONER_SQL.write_text(
        f"-- Auto-generated from .env DEFAULT_RIOT_ID by lol-tools dashboard CLI.\n"
        f"-- Do NOT commit this file (it embeds a per-user summoner ID).\n"
        f"SELECT '{safe}' AS summoner\n",
        encoding="utf-8",
    )


@app.command()
def backfill() -> None:
    """既存の findings_*.json を全件 DuckDB に取り込みます（冪等）。"""
    from lol_dashboard.persist import backfill as _backfill

    _ensure_db_dir()
    _write_target_summoner_sql()
    console.print(f"[bold]backfill[/] {_OUTPUT_DIR} → {_DB_PATH}")
    _backfill(_DB_PATH, _OUTPUT_DIR)
    console.print("[green]完了[/]")


@app.command()
def sync() -> None:
    """latest_findings.json を DuckDB に取り込みます。"""
    from lol_dashboard.persist import sync_latest

    _ensure_db_dir()
    _write_target_summoner_sql()
    console.print(f"[bold]sync[/] → {_DB_PATH}")
    sync_latest(_DB_PATH, _OUTPUT_DIR)
    console.print("[green]完了[/]")


@app.command()
def serve() -> None:
    """Evidence.dev の開発サーバを起動します（Ctrl+C で停止）。"""
    _check_evidence_setup()
    _write_target_summoner_sql()
    console.print(f"[bold]serve[/] {_EVIDENCE_DIR}")
    try:
        result = subprocess.run(["npm", "run", "dev"], cwd=_EVIDENCE_DIR)
    except KeyboardInterrupt:
        return
    if result.returncode != 0:
        console.print(f"[red]Error:[/] `npm run dev` が失敗しました（exit code {result.returncode}）。ログを確認してください。")
        raise typer.Exit(result.returncode)


@app.command()
def build() -> None:
    """Evidence.dev の静的サイトをビルドします。"""
    _check_evidence_setup()
    _write_target_summoner_sql()
    console.print(f"[bold]build[/] {_EVIDENCE_DIR}")
    result = subprocess.run(["npm", "run", "build"], cwd=_EVIDENCE_DIR)
    if result.returncode != 0:
        console.print(
            f"[red]Error:[/] `npm run build` が失敗しました（exit code {result.returncode}）。"
            "事前に `npm run sources` が成功しているか、DuckDB が backfill 済みかを確認してください。"
        )
        raise typer.Exit(result.returncode)
    console.print("[green]ビルド完了[/]: evidence/build/")


def _check_evidence_setup() -> None:
    """Verify Node ≥ 18, npm, and node_modules before invoking npm scripts."""
    _check_node()
    if not _EVIDENCE_DIR.exists():
        console.print(f"[red]Error:[/] {_EVIDENCE_DIR} が見つかりません。")
        raise typer.Exit(1)
    if not (_EVIDENCE_DIR / "node_modules").exists():
        console.print(
            f"[red]Error:[/] {_EVIDENCE_DIR}/node_modules が見つかりません。"
            "先に `cd packages/lol_dashboard/evidence && npm install` を実行してください。"
        )
        raise typer.Exit(1)


def _check_node() -> None:
    import shutil

    if shutil.which("node") is None:
        console.print("[red]Error:[/] node が見つかりません。Node.js (>=18) をインストールしてください。")
        console.print("  brew install node  # macOS / または mise install")
        raise typer.Exit(1)
    if shutil.which("npm") is None:
        console.print("[red]Error:[/] npm が見つかりません。Node.js (>=18) をインストールしてください。")
        raise typer.Exit(1)
    major = _node_major_version()
    if major is not None and major < 18:
        console.print(
            f"[red]Error:[/] Node.js v{major} は古すぎます。Evidence.dev は Node >= 18 を要求します。"
        )
        raise typer.Exit(1)


def _node_major_version() -> int | None:
    """Return Node.js major version, or None if it cannot be determined."""
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    raw = result.stdout.strip().lstrip("v")  # e.g. "22.22.2"
    head = raw.split(".", 1)[0]
    return int(head) if head.isdigit() else None
