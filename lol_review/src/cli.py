"""CLI entry point for lol-review."""

from __future__ import annotations

import asyncio
import os
import sys

import click
from dotenv import load_dotenv

from src.analyzer import analyze_matches
from src.report import generate_report
from src.riot_client import RiotClient


@click.group()
def cli() -> None:
    """LoL match review tool."""


@cli.command()
@click.argument("riot_id")
@click.option("--count", default=None, type=int, help="取得する試合数 (default: .envのDEFAULT_COUNTまたは20)")
@click.option("--ranked-only", is_flag=True, help="ランク戦のみ")
@click.option("--no-open", is_flag=True, help="ブラウザを開かない")
def report(riot_id: str, count: int, ranked_only: bool, no_open: bool) -> None:
    """指定した Riot ID のマッチレポートを生成します。

    RIOT_ID は "ゲーム名#タグライン" の形式で指定してください。
    例: lol-review report "SummonerName#JP1"
    """
    if "#" not in riot_id:
        click.echo(
            "エラー: Riot ID は 'ゲーム名#タグライン' の形式で指定してください。",
            err=True,
        )
        click.echo("例: lol-review report \"SummonerName#JP1\"", err=True)
        sys.exit(1)

    game_name, tag_line = riot_id.rsplit("#", 1)

    load_dotenv()
    api_key = os.environ.get("RIOT_API_KEY")
    if not api_key:
        click.echo("エラー: RIOT_API_KEY が設定されていません。", err=True)
        click.echo("次のいずれかの方法で API キーを設定してください:", err=True)
        click.echo("  1. lol-review config set-api-key", err=True)
        click.echo("  2. .env ファイルに RIOT_API_KEY=<your_key> を追記", err=True)
        click.echo("  3. 環境変数として export RIOT_API_KEY=<your_key>", err=True)
        sys.exit(1)

    if count is None:
        count = int(os.environ.get("DEFAULT_COUNT", "20"))

    queue_type = 420 if ranked_only else None
    asyncio.run(
        _generate_report(
            api_key=api_key,
            game_name=game_name,
            tag_line=tag_line,
            count=count,
            queue_type=queue_type,
            open_browser=not no_open,
        )
    )


async def _generate_report(
    api_key: str,
    game_name: str,
    tag_line: str,
    count: int,
    queue_type: int | None,
    open_browser: bool,
) -> None:
    """Async implementation of report generation."""
    client = RiotClient(api_key)
    try:
        click.echo(f"Riot ID を検索中: {game_name}#{tag_line}")
        puuid = await client.get_puuid(game_name, tag_line)
        click.echo(f"PUUID 取得完了: {puuid[:8]}...")

        click.echo("アイテムデータを取得中...")
        item_data = await client.get_item_data()

        click.echo(f"マッチ履歴を取得中 (最大 {count} 件)...")
        match_ids = await client.get_match_ids(puuid, count, queue_type=queue_type)
        click.echo(f"{len(match_ids)} 件のマッチを取得しました。")

        matches = []
        player_stats = []
        for i, match_id in enumerate(match_ids, start=1):
            click.echo(f"[{i}/{len(match_ids)}] {match_id} を解析中...")

            detail = await client.get_match_detail(match_id)
            summary = client.parse_match_summary(detail, puuid)

            # Skip remakes (< 5 minutes)
            if summary.game_duration_seconds < 300:
                click.echo(f" → リメイク（{summary.game_duration_seconds}秒）のためスキップ")
                continue

            matches.append(summary)

            timeline = await client.get_match_timeline(match_id)
            participants = detail["metadata"]["participants"]
            participant_id = participants.index(puuid) + 1

            # Find opponent participant IDs for level-up tracking
            my_role = summary.role
            my_team_id = detail["info"]["participants"][participant_id - 1]["teamId"]
            bot_lane_roles = {"BOTTOM", "UTILITY"}
            is_bot_lane = my_role in bot_lane_roles
            opponent_ids = []
            for p in detail["info"]["participants"]:
                if p["teamId"] != my_team_id:
                    p_role = p.get("teamPosition", "")
                    if is_bot_lane and p_role in bot_lane_roles:
                        opponent_ids.append(participants.index(p["puuid"]) + 1)
                    elif p_role == my_role:
                        opponent_ids.append(participants.index(p["puuid"]) + 1)

            stats = client.parse_timeline(
                timeline, match_id, puuid, participant_id,
                item_data=item_data, opponent_ids=opponent_ids,
            )
            player_stats.append(stats)

        click.echo("分析中...")
        result = analyze_matches(game_name, tag_line, matches, player_stats)

        click.echo("レポートを生成中...")
        output_path = generate_report(result, open_browser=open_browser)
        click.echo(f"レポートを保存しました: {output_path}")

    finally:
        await client.close()


@cli.group()
def config() -> None:
    """設定を管理します。"""


@config.command("set-api-key")
def set_api_key() -> None:
    """Riot API キーを .env ファイルに保存します。"""
    api_key = click.prompt("Riot API Key を入力してください", hide_input=True)

    env_path = ".env"
    lines: list[str] = []

    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()

    key_line = f"RIOT_API_KEY={api_key}\n"
    found = False
    for i, line in enumerate(lines):
        if line.startswith("RIOT_API_KEY="):
            lines[i] = key_line
            found = True
            break

    if not found:
        lines.append(key_line)

    with open(env_path, "w") as f:
        f.writelines(lines)

    click.echo(f"API キーを {env_path} に保存しました。")


@config.command("set-default-count")
@click.argument("count", type=int)
def set_default_count(count: int) -> None:
    """デフォルトの試合取得数を設定します。"""
    env_path = ".env"
    lines: list[str] = []

    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()

    key_line = f"DEFAULT_COUNT={count}\n"
    found = False
    for i, line in enumerate(lines):
        if line.startswith("DEFAULT_COUNT="):
            lines[i] = key_line
            found = True
            break

    if not found:
        lines.append(key_line)

    with open(env_path, "w") as f:
        f.writelines(lines)

    click.echo(f"デフォルト試合数を {count} に設定しました。")


if __name__ == "__main__":
    cli()
