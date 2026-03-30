"""Unified CLI entry point for lol-tools."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable

import typer
from dotenv import load_dotenv
from rich.console import Console

from lol_vod_analyzer.main import app as vod_app

# Repo root = src/lol_tools/cli.py -> src/lol_tools -> src -> lol-tools/
REPO_ROOT = Path(__file__).parent.parent.parent
ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
console = Console()

app = typer.Typer(
    help="League of Legends 上達支援ツール群",
    rich_markup_mode="markdown",
)


# Mount lol_vod_analyzer as "vod" subcommand
app.add_typer(vod_app, name="vod", help="動画分析（解説動画・プレイ動画）")


def _load_env() -> None:
    load_dotenv(ENV_PATH)


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    ordered_keys: Iterable[str] = (
        "RIOT_API_KEY",
        "GOOGLE_API_KEY",
        "DEFAULT_RIOT_ID",
        "DEFAULT_COUNT",
    )
    lines: list[str] = []
    seen: set[str] = set()

    for key in ordered_keys:
        if key in values:
            lines.append(f"{key}={values[key]}")
            seen.add(key)

    for key, value in values.items():
        if key in seen:
            continue
        lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _upsert_env_values(path: Path, updates: dict[str, str]) -> dict[str, str]:
    values = _read_env_file(path)
    values.update({k: v for k, v in updates.items() if v != ""})
    _write_env_file(path, values)
    return values


def _status_icon(ok: bool) -> str:
    return "[green]OK[/]" if ok else "[red]NG[/]"


def _is_valid_riot_id(value: str) -> bool:
    if "#" not in value:
        return False
    game_name, tag_line = value.rsplit("#", 1)
    return bool(game_name.strip()) and bool(tag_line.strip())


def _doctor_checks() -> list[tuple[str, bool, str]]:
    env_values = _read_env_file(ENV_PATH)
    _load_env()

    ffmpeg_path = shutil.which("ffmpeg")
    review_output_dir = REPO_ROOT / "packages" / "lol_review" / "output"
    vod_output_dir = REPO_ROOT / "packages" / "lol_vod_analyzer" / "output"

    return [
        (
            ".env",
            ENV_PATH.exists(),
            f"見つかりません。`cp .env.example .env` または `uv run lol-tools init` を実行してください。"
            if not ENV_PATH.exists()
            else f"設定ファイル: {ENV_PATH}",
        ),
        (
            "RIOT_API_KEY",
            bool(os.environ.get("RIOT_API_KEY")),
            "未設定です。試合データ分析には `.env` に RIOT_API_KEY が必要です。"
            if not os.environ.get("RIOT_API_KEY")
            else "試合データ分析を実行できます。",
        ),
        (
            "GOOGLE_API_KEY",
            bool(os.environ.get("GOOGLE_API_KEY")),
            "未設定です。動画分析には `.env` に GOOGLE_API_KEY が必要です。"
            if not os.environ.get("GOOGLE_API_KEY")
            else "動画分析を実行できます。",
        ),
        (
            "DEFAULT_RIOT_ID",
            bool(env_values.get("DEFAULT_RIOT_ID")),
            "未設定です。`lol-tools review` を引数なしで使うなら DEFAULT_RIOT_ID を設定してください。"
            if not env_values.get("DEFAULT_RIOT_ID")
            else f"既定の Riot ID: {env_values['DEFAULT_RIOT_ID']}",
        ),
        (
            "ffmpeg",
            ffmpeg_path is not None,
            "見つかりません。ローカル動画分析を使うなら ffmpeg をインストールしてください。"
            if ffmpeg_path is None
            else f"実行ファイル: {ffmpeg_path}",
        ),
        (
            "出力先",
            True,
            f"review: {review_output_dir} / vod: {vod_output_dir}",
        ),
    ]


@app.command()
def review(
    riot_id: str | None = typer.Argument(None, help="Riot ID（例: SummonerName#JP1）省略時は .env の DEFAULT_RIOT_ID"),
    count: int | None = typer.Option(None, help="取得する試合数"),
    ranked_only: bool = typer.Option(False, "--ranked-only", help="ランク戦のみ"),
    no_open: bool = typer.Option(False, "--no-open", help="ブラウザを開かない"),
) -> None:
    """試合データを分析してレポートを生成します。

    例:
    `uv run lol-tools review "SummonerName#JP1"`
    `uv run lol-tools review --count 1 --no-open`
    `uv run lol-tools doctor`
    """
    _load_env()

    from lol_review.cli import report as _click_report

    # Build Click-compatible args
    args: list[str] = []
    if riot_id is not None:
        args.append(riot_id)
    if count is not None:
        args.extend(["--count", str(count)])
    if ranked_only:
        args.append("--ranked-only")
    if no_open:
        args.append("--no-open")

    _click_report.main(args, standalone_mode=False)


@app.command()
def init(
    riot_api_key: str | None = typer.Option(None, help="Riot API Key を直接設定"),
    google_api_key: str | None = typer.Option(None, help="Google API Key を直接設定"),
    default_riot_id: str | None = typer.Option(None, help="既定の Riot ID を設定"),
    default_count: int | None = typer.Option(None, min=1, help="既定の試合数を設定"),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="未指定の値を質問せず、渡されたオプションだけで更新する",
    ),
) -> None:
    """初回セットアップ用に .env を作成・更新します。"""
    if not ENV_PATH.exists():
        if ENV_EXAMPLE_PATH.exists():
            ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            console.print(f"[green].env を作成しました[/]: {ENV_PATH}")
        else:
            _write_env_file(ENV_PATH, {})
            console.print(f"[green]空の .env を作成しました[/]: {ENV_PATH}")

    values = _read_env_file(ENV_PATH)
    updates: dict[str, str] = {}

    if riot_api_key is not None:
        updates["RIOT_API_KEY"] = riot_api_key
    elif not non_interactive and not values.get("RIOT_API_KEY"):
        entered = typer.prompt(
            "Riot API Key（不要なら空 Enter）",
            default="",
            show_default=False,
            hide_input=True,
        )
        if entered:
            updates["RIOT_API_KEY"] = entered

    if google_api_key is not None:
        updates["GOOGLE_API_KEY"] = google_api_key
    elif not non_interactive and not values.get("GOOGLE_API_KEY"):
        entered = typer.prompt(
            "Google API Key（不要なら空 Enter）",
            default="",
            show_default=False,
            hide_input=True,
        )
        if entered:
            updates["GOOGLE_API_KEY"] = entered

    if default_riot_id is not None:
        if default_riot_id and not _is_valid_riot_id(default_riot_id):
            raise typer.BadParameter("DEFAULT_RIOT_ID は `ゲーム名#タグライン` 形式で指定してください。")
        updates["DEFAULT_RIOT_ID"] = default_riot_id
    elif not non_interactive and not values.get("DEFAULT_RIOT_ID"):
        entered = typer.prompt(
            "DEFAULT_RIOT_ID（例: SummonerName#JP1、不要なら空 Enter）",
            default="",
            show_default=False,
        )
        if entered:
            if not _is_valid_riot_id(entered):
                raise typer.BadParameter("DEFAULT_RIOT_ID は `ゲーム名#タグライン` 形式で指定してください。")
            updates["DEFAULT_RIOT_ID"] = entered

    if default_count is not None:
        updates["DEFAULT_COUNT"] = str(default_count)
    elif not non_interactive and not values.get("DEFAULT_COUNT"):
        entered = typer.prompt("DEFAULT_COUNT", default="20", show_default=True)
        if entered:
            updates["DEFAULT_COUNT"] = entered

    merged = _upsert_env_values(ENV_PATH, updates)

    console.print("\n[bold]現在の設定[/]")
    for key in ("RIOT_API_KEY", "GOOGLE_API_KEY", "DEFAULT_RIOT_ID", "DEFAULT_COUNT"):
        value = merged.get(key, "")
        masked = value
        if key.endswith("API_KEY") and value:
            masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "設定済み"
        console.print(f"- {key}: {masked or '未設定'}")

    console.print("\n次の確認: `uv run lol-tools doctor`")


@app.command()
def doctor() -> None:
    """初回セットアップに必要な設定と依存を診断します。"""
    checks = _doctor_checks()
    has_review_ready = all(ok for name, ok, _ in checks if name in {".env", "RIOT_API_KEY"})
    has_vod_ready = all(ok for name, ok, _ in checks if name in {".env", "GOOGLE_API_KEY"})
    has_default_riot_id = any(ok for name, ok, _ in checks if name == "DEFAULT_RIOT_ID")

    console.print("[bold]lol-tools doctor[/]")
    for name, ok, detail in checks:
        console.print(f"- {_status_icon(ok)} {name}: {detail}")

    console.print("\n[bold]次に使うコマンド[/]")
    if has_review_ready and has_default_riot_id:
        console.print("- 試合データ分析: `uv run lol-tools review`")
    else:
        console.print("- 試合データ分析: `uv run lol-tools review \"SummonerName#JP1\"`")
    if has_vod_ready:
        console.print("- 動画分析: `uv run lol-tools vod analyze ~/Desktop/replay.mov --mode gameplay`")
    else:
        console.print("- 動画分析の前に: `.env` に `GOOGLE_API_KEY` を設定")


@app.command()
def examples() -> None:
    """代表的な実行例を表示します。"""
    console.print("[bold]Quick Start[/]")
    console.print("uv sync")
    console.print("cp .env.example .env")
    console.print("uv run lol-tools init")
    console.print("uv run lol-tools doctor")
    console.print("\n[bold]Match Review[/]")
    console.print('uv run lol-tools review "SummonerName#JP1"')
    console.print("uv run lol-tools review --count 1 --no-open")
    console.print("\n[bold]VOD Analysis: Commentary[/]")
    console.print("uv run lol-tools vod analyze 'https://youtube.com/watch?v=...' --mode commentary")
    console.print("\n[bold]VOD Analysis: Gameplay[/]")
    console.print("uv run lol-tools vod analyze ~/Desktop/replay.mov --mode gameplay --interval 5")
    console.print("uv run lol-tools vod analyze ~/Desktop/replay.mov --mode gameplay --interval 5 --match-data packages/lol_review/output/latest_findings.json")


if __name__ == "__main__":
    app()
