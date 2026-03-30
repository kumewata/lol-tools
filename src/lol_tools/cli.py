"""Unified CLI entry point for lol-tools."""

from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv

from lol_vod_analyzer.main import app as vod_app

# Repo root = src/lol_tools/cli.py -> src/lol_tools -> src -> lol-tools/
REPO_ROOT = Path(__file__).parent.parent.parent
ENV_PATH = REPO_ROOT / ".env"

app = typer.Typer(help="League of Legends 上達支援ツール群")


# Mount lol_vod_analyzer as "vod" subcommand
app.add_typer(vod_app, name="vod", help="動画分析 (VOD analysis)")


@app.command()
def review(
    riot_id: str = typer.Argument(help="Riot ID（例: SummonerName#JP1）"),
    count: int | None = typer.Option(None, help="取得する試合数"),
    ranked_only: bool = typer.Option(False, "--ranked-only", help="ランク戦のみ"),
    no_open: bool = typer.Option(False, "--no-open", help="ブラウザを開かない"),
) -> None:
    """試合データを分析してレポートを生成します。"""
    load_dotenv(ENV_PATH)

    from lol_review.cli import report as _click_report

    # Build Click-compatible args
    args = [riot_id]
    if count is not None:
        args.extend(["--count", str(count)])
    if ranked_only:
        args.append("--ranked-only")
    if no_open:
        args.append("--no-open")

    _click_report.main(args, standalone_mode=False)


if __name__ == "__main__":
    app()
