"""Dashboard subcommand group for lol-tools."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="成長トレンドダッシュボード（DuckDB + Evidence.dev）")

# packages/lol_dashboard/src/lol_dashboard/cli.py → 3 parents up = packages/lol_dashboard/
_PACKAGE_DIR = Path(__file__).parent.parent.parent
_REPO_ROOT = _PACKAGE_DIR.parent.parent
_OUTPUT_DIR = _REPO_ROOT / "packages" / "lol_review" / "output"
_DB_PATH = _PACKAGE_DIR / "data" / "lol_history.duckdb"
_EVIDENCE_DIR = _PACKAGE_DIR / "evidence"


def _ensure_db_dir() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@app.command()
def backfill() -> None:
    """既存の findings_*.json を全件 DuckDB に取り込みます（冪等）。"""
    from lol_dashboard.persist import backfill as _backfill

    _ensure_db_dir()
    console.print(f"[bold]backfill[/] {_OUTPUT_DIR} → {_DB_PATH}")
    _backfill(_DB_PATH, _OUTPUT_DIR)
    console.print("[green]完了[/]")


@app.command()
def sync() -> None:
    """latest_findings.json を DuckDB に取り込みます。"""
    from lol_dashboard.persist import sync_latest

    _ensure_db_dir()
    console.print(f"[bold]sync[/] → {_DB_PATH}")
    sync_latest(_DB_PATH, _OUTPUT_DIR)
    console.print("[green]完了[/]")


@app.command()
def serve() -> None:
    """Evidence.dev の開発サーバを起動します（Ctrl+C で停止）。"""
    _check_node()
    if not _EVIDENCE_DIR.exists():
        console.print(f"[red]Error:[/] {_EVIDENCE_DIR} が見つかりません。`npm install` を実行してください。")
        raise typer.Exit(1)
    console.print(f"[bold]serve[/] {_EVIDENCE_DIR}")
    try:
        subprocess.run(["npm", "run", "dev"], cwd=_EVIDENCE_DIR, check=True)
    except KeyboardInterrupt:
        pass


@app.command()
def build() -> None:
    """Evidence.dev の静的サイトをビルドします。"""
    _check_node()
    if not _EVIDENCE_DIR.exists():
        console.print(f"[red]Error:[/] {_EVIDENCE_DIR} が見つかりません。`npm install` を実行してください。")
        raise typer.Exit(1)
    console.print(f"[bold]build[/] {_EVIDENCE_DIR}")
    subprocess.run(["npm", "run", "build"], cwd=_EVIDENCE_DIR, check=True)
    console.print("[green]ビルド完了[/]: evidence/build/")


def _check_node() -> None:
    if not _npm_available():
        console.print("[red]Error:[/] npm が見つかりません。Node.js (>=18) をインストールしてください。")
        console.print("  brew install node  # macOS")
        raise typer.Exit(1)


def _npm_available() -> bool:
    import shutil
    return shutil.which("npm") is not None
