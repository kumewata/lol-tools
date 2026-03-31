"""CLI entry point for lol-vod-analyzer."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from lol_vod_analyzer.analyzer import analyze_video, chunk_transcript
from lol_vod_analyzer.fetcher import (
    download_storyboard_sprites,
    download_video,
    fetch_transcript,
    fetch_video_metadata,
    find_storyboard_format,
)
from lol_vod_analyzer.local_video import (
    extract_audio,
    extract_screenshots,
    get_video_metadata,
    transcribe_audio,
)
from lol_vod_analyzer.models import SceneSnapshot, VideoSource
from lol_vod_analyzer.report import generate_report
from lol_vod_analyzer.system_tools import (
    format_missing_tools_message,
    missing_tools,
    required_local_video_tools,
)

app = typer.Typer(help="LoL VOD Analysis Tool", rich_markup_mode="markdown")
console = Console()

# __file__ = packages/lol_vod_analyzer/src/lol_vod_analyzer/main.py
PACKAGE_ROOT = Path(__file__).parent.parent.parent
_ENV_PATH = PACKAGE_ROOT.parent.parent / ".env"  # repo root .env


def _build_match_context(findings: object) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    if not isinstance(findings, dict):
        return None, ["match-data の形式が不正です"]

    matches = findings.get("matches", [])
    player_stats = findings.get("player_stats", [])

    if not isinstance(matches, list):
        return None, ["match-data の matches が不正です"]

    if len(matches) != 1:
        return None, [
            "match-data は 1 試合だけを含む JSON である必要があります。"
            f" 現在は {len(matches)} 試合入っています。"
            " `lol-tools export-match-data --match-index <N>` か"
            " `replay analyze --match-index <N>` を使って単一試合 JSON を作ってください。"
        ]

    if player_stats and (not isinstance(player_stats, list) or len(player_stats) > 1):
        return None, [
            "match-data の player_stats も 1 試合分だけを含む必要があります。"
        ]

    match_context = dict(matches[0])
    if player_stats and isinstance(player_stats, list):
        stats = player_stats[0]
        if isinstance(stats, dict):
            match_context["kill_timestamps"] = stats.get("kill_timestamps", [])
            match_context["death_timestamps"] = stats.get("death_timestamps", [])
            match_context["assist_timestamps"] = stats.get("assist_timestamps", [])
            match_context["objective_events"] = stats.get("objective_events", [])
            match_context["item_purchases"] = stats.get("item_purchases", [])
            match_context["skill_level_ups"] = stats.get("skill_level_ups", [])
            match_context["level_ups"] = stats.get("level_ups", [])
            match_context["opponent_level_ups"] = stats.get("opponent_level_ups", [])
            match_context["position_timeline"] = stats.get("position_timeline", [])
            match_context["jungle_cs_timeline"] = stats.get("jungle_cs_timeline", [])

    return match_context, errors


@app.command()
def analyze(
    source: str = typer.Argument(help="YouTube URL or local video file path"),
    mode: Optional[str] = typer.Option(
        None, help="Analysis mode: commentary or gameplay (auto-detected if omitted)"
    ),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open report in browser"),
    lang: str = typer.Option("ja", help="Subtitle language code"),
    interval: int = typer.Option(10, help="Screenshot interval in seconds (local video only)"),
    download: bool = typer.Option(False, "--download", help="Download YouTube video and analyze locally (higher quality screenshots)"),
    match_data: Optional[str] = typer.Option(
        None, "--match-data", help="Path to lol_review findings JSON for match context"
    ),
) -> None:
    """Analyze a LoL video and generate an HTML report.

    Examples:
    `uv run lol-tools vod analyze 'https://youtube.com/watch?v=...' --mode commentary`
    `uv run lol-tools vod analyze ~/Desktop/replay.mov --mode gameplay --interval 5`
    `uv run lol-tools examples`
    """
    load_dotenv(_ENV_PATH)

    # Load match context from lol_review findings JSON if provided
    match_context: dict | None = None
    if match_data:
        data_path = Path(match_data).resolve()
        if not data_path.exists():
            console.print(f"[yellow]Warning:[/] {match_data} が見つかりません")
        elif data_path.suffix != ".json":
            console.print(f"[yellow]Warning:[/] {match_data} は JSON ファイルではありません")
        else:
            with open(data_path) as f:
                findings = json.load(f)
            match_context, errors = _build_match_context(findings)
            if errors:
                for error in errors:
                    console.print(f"[red]Error:[/] {error}")
                raise typer.Exit(1)
            console.print(f"[green]試合データ読み込み:[/] {match_context.get('champion')} ({match_context.get('role')})")

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        console.print(
            "[red]Error:[/] GOOGLE_API_KEY が設定されていません。\n"
            "通常は `.env` に設定してください。\n"
            "1. `uv run lol-tools init`\n"
            "2. `.env` に `GOOGLE_API_KEY=<your_key>` を追記\n"
            "3. 確認は `uv run lol-tools doctor`"
        )
        raise typer.Exit(1)

    parsed_source = urlparse(source)
    if parsed_source.scheme in ("http", "https"):
        if download:
            asyncio.run(
                _download_and_analyze(
                    url=source,
                    mode=mode,
                    open_browser=not no_open,
                    api_key=api_key,
                    interval=interval,
                    match_context=match_context,
                )
            )
        else:
            asyncio.run(
                _analyze_youtube(
                    url=source,
                    mode=mode,
                    open_browser=not no_open,
                    lang=lang,
                    api_key=api_key,
                    match_context=match_context,
                )
            )
    else:
        video_path = Path(source)
        if not video_path.exists():
            console.print(
                f"[red]Error:[/] ファイルが見つかりません: {source}\n"
                "ローカル動画のパスを確認してください。使い方の例は `uv run lol-tools examples` で確認できます。"
            )
            raise typer.Exit(1)
        asyncio.run(
            _analyze_local(
                video_path=video_path,
                mode=mode,
                open_browser=not no_open,
                api_key=api_key,
                interval=interval,
                match_context=match_context,
            )
        )


async def _analyze_youtube(
    url: str,
    mode: str | None,
    open_browser: bool,
    lang: str,
    api_key: str,
    match_context: dict | None = None,
) -> None:
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("動画情報を取得中...", total=None)
        video_source, info = fetch_video_metadata(url)
        console.print(f"[green]Title:[/] {video_source.title}")
        console.print(f"[green]Duration:[/] {video_source.duration // 60}分{video_source.duration % 60}秒")
        progress.update(task, completed=True)

        progress.update(task, description="字幕を取得中...")
        transcript = fetch_transcript(info, lang=lang)
        console.print(f"[green]字幕セグメント:[/] {len(transcript)}件")

        if not transcript:
            console.print(
                "[yellow]字幕が取得できませんでした。分析を中止します。[/]\n"
                "[yellow]字幕がない動画は `--download --mode gameplay` を試してください。[/]"
            )
            return

        progress.update(task, description="ストーリーボードを取得中...")
        sb_format = find_storyboard_format(info.get("formats", []))
        snapshots: list[SceneSnapshot] = []

        if sb_format:
            output_dir = PACKAGE_ROOT / "output" / "storyboards"
            frame_paths = download_storyboard_sprites(sb_format, output_dir)
            console.print(f"[green]ストーリーボード:[/] {len(frame_paths)}フレーム")

            total_frames = len(frame_paths)
            if total_frames > 0:
                interval_ms = (video_source.duration * 1000) // total_frames
                snapshots = [
                    SceneSnapshot(
                        timestamp_ms=i * interval_ms,
                        image_path=path,
                    )
                    for i, path in enumerate(frame_paths)
                ]
        else:
            console.print("[yellow]ストーリーボードが見つかりませんでした。[/]")

        analysis_mode = mode or "commentary"
        console.print(f"[green]分析モード:[/] {analysis_mode}")

        progress.update(task, description="LLMで分析中...")
        chunks = chunk_transcript(transcript)
        console.print(f"[green]チャンク数:[/] {len(chunks)}")

        result = await analyze_video(
            source=video_source,
            transcript=transcript,
            snapshots=snapshots,
            mode=analysis_mode,
            api_key=api_key,
            match_context=match_context,
        )

        progress.update(task, description="レポートを生成中...")
        output_path = generate_report(
            result, open_browser=open_browser
        )
        progress.update(task, completed=True)

    console.print(f"\n[green]レポートを保存しました:[/] {output_path}")


async def _download_and_analyze(
    url: str,
    mode: str | None,
    open_browser: bool,
    api_key: str,
    interval: int = 10,
    match_context: dict | None = None,
) -> None:
    """Download YouTube video and analyze locally."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("動画をダウンロード中（360p）...", total=None)
        download_dir = PACKAGE_ROOT / "output" / "downloads"
        video_path = download_video(url, download_dir)

        if video_path is None or not video_path.exists():
            console.print("[red]Error:[/] 動画のダウンロードに失敗しました")
            return

        console.print(f"[green]ダウンロード完了:[/] {video_path.name} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")
        progress.update(task, completed=True)

    # Delegate to local analysis pipeline, preserving original YouTube URL
    await _analyze_local(
        video_path=video_path,
        mode=mode,
        open_browser=open_browser,
        api_key=api_key,
        interval=interval,
        match_context=match_context,
        original_url=url,
    )


async def _analyze_local(
    video_path: Path,
    mode: str | None,
    open_browser: bool,
    api_key: str,
    interval: int = 10,
    match_context: dict | None = None,
    original_url: str | None = None,
) -> None:
    """Analyze a local video file."""
    needed_tools = required_local_video_tools(mode)
    missing = missing_tools(needed_tools)
    if missing:
        console.print(f"[red]Error:[/] {format_missing_tools_message(missing, 'ローカル動画分析')}")
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("動画情報を取得中...", total=None)
        try:
            video_source = get_video_metadata(video_path)
        except RuntimeError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise typer.Exit(1) from exc
        if original_url:
            video_source.url = original_url
            video_source.source_type = "youtube"
        console.print(f"[green]Title:[/] {video_source.title}")
        console.print(f"[green]Duration:[/] {video_source.duration // 60}分{video_source.duration % 60}秒")
        progress.update(task, completed=True)

        # Extract audio and transcribe (skip for gameplay mode — game SE is noise)
        transcript: list = []
        if mode != "gameplay":
            progress.update(task, description="音声を抽出中...")
            audio_dir = PACKAGE_ROOT / "output" / "audio"
            try:
                audio_path = extract_audio(video_path, audio_dir)
            except RuntimeError as exc:
                console.print(f"[red]Error:[/] {exc}")
                raise typer.Exit(1) from exc

            if audio_path is not None:
                console.print(f"[green]音声抽出:[/] {audio_path.name}")
                progress.update(task, description="音声を文字起こし中（Gemini）...")
                transcript = transcribe_audio(audio_path, api_key=api_key)
                console.print(f"[green]字幕セグメント:[/] {len(transcript)}件")
            else:
                console.print("[yellow]音声トラックなし[/]")
        else:
            console.print("[dim]gameplay モード — 音声文字起こしをスキップ（ゲームSEはノイズのため）[/]")

        # Extract screenshots
        progress.update(task, description="スクリーンショットを抽出中...")
        screenshot_dir = PACKAGE_ROOT / "output" / "screenshots"
        snapshots = extract_screenshots(video_path, screenshot_dir, interval_seconds=interval)
        console.print(f"[green]スクリーンショット:[/] {len(snapshots)}枚")

        # Determine mode (only auto-detect if not specified)
        if mode is None:
            mode = "gameplay" if len(transcript) < 10 else "commentary"
        console.print(f"[green]分析モード:[/] {mode}")

        # Run LLM analysis
        progress.update(task, description="LLMで分析中...")
        chunks = chunk_transcript(transcript)
        console.print(f"[green]チャンク数:[/] {len(chunks)}")

        result = await analyze_video(
            source=video_source,
            transcript=transcript,
            snapshots=snapshots,
            mode=mode,
            api_key=api_key,
            match_context=match_context,
        )

        # Generate report
        progress.update(task, description="レポートを生成中...")
        output_path = generate_report(result, open_browser=open_browser)
        progress.update(task, completed=True)

    console.print(f"\n[green]レポートを保存しました:[/] {output_path}")


if __name__ == "__main__":
    app()
