"""Matchup summary CLI for latest lol_review findings."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(help="対面・ピック傾向サマリ")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_LATEST_FINDINGS_PATH = _REPO_ROOT / "packages" / "lol_review" / "output" / "latest_findings.json"


@app.callback()
def matchup() -> None:
    """対面・ピック傾向サマリ。"""


def load_findings(path: Path) -> dict[str, Any]:
    """Load a lol_review findings JSON file."""
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _summarize_group(label_key: str, label: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for match in matches if bool(match.get("win")))
    kdas = [v for match in matches if (v := _as_float(match.get("kda"))) is not None]
    kps = [
        v
        for match in matches
        if (v := _as_float(match.get("kill_participation"))) is not None
    ]
    vision_scores = [
        v for match in matches if (v := _as_float(match.get("vision_score"))) is not None
    ]
    games = len(matches)
    return {
        label_key: label,
        "games": games,
        "wins": wins,
        "losses": games - wins,
        "win_rate": _ratio(wins, games),
        "avg_kda": _avg(kdas),
        "avg_kill_participation": _avg(kps),
        "avg_vision_score": _avg(vision_scores),
    }


def _lane_opponents(match: dict[str, Any]) -> list[str]:
    opponents = match.get("lane_opponents")
    if not isinstance(opponents, list):
        return []
    return sorted(str(opponent) for opponent in opponents if str(opponent).strip())


def _sort_by_games_win_rate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            item["games"],
            item["win_rate"],
            item.get("avg_kill_participation") or 0.0,
            item.get("champion") or item.get("opponent") or "",
        ),
        reverse=True,
    )


def build_matchup_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic matchup summaries from latest_findings.json content."""
    matches = [match for match in data.get("matches", []) if isinstance(match, dict)]

    champion_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pair_groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    opponent_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for match in matches:
        champion = str(match.get("champion", "Unknown"))
        champion_groups[champion].append(match)

        opponents = _lane_opponents(match)
        if opponents:
            pair_groups[tuple(opponents)].append(match)
            for opponent in opponents:
                opponent_groups[opponent].append(match)

    champion_summaries = [
        _summarize_group("champion", champion, group)
        for champion, group in champion_groups.items()
    ]
    champion_summaries = _sort_by_games_win_rate(champion_summaries)

    lane_opponent_pairs: list[dict[str, Any]] = []
    for opponents, group in pair_groups.items():
        item = _summarize_group("pair", " / ".join(opponents), group)
        item["opponents"] = list(opponents)
        item.pop("pair")
        item["our_champions"] = sorted({str(match.get("champion", "Unknown")) for match in group})
        lane_opponent_pairs.append(item)
    lane_opponent_pairs = _sort_by_games_win_rate(lane_opponent_pairs)

    opponent_summaries = [
        _summarize_group("opponent", opponent, group)
        for opponent, group in opponent_groups.items()
    ]
    opponent_summaries = _sort_by_games_win_rate(opponent_summaries)

    pick_candidates = champion_summaries[:5]
    watch_opponents = sorted(
        opponent_summaries,
        key=lambda item: (
            item["losses"],
            -(item.get("avg_kill_participation") or 0.0),
            item["games"],
            item["opponent"],
        ),
        reverse=True,
    )[:5]

    return {
        "summoner": data.get("summoner"),
        "generated_at": data.get("generated_at"),
        "sample_size": len(matches),
        "champion_summaries": champion_summaries,
        "lane_opponent_pairs": lane_opponent_pairs,
        "opponent_summaries": opponent_summaries,
        "recommendations": {
            "pick_candidates": pick_candidates,
            "watch_opponents": watch_opponents,
        },
    }


def _format_optional_float(value: float | None, *, percent: bool = False) -> str:
    if value is None:
        return "-"
    if percent:
        return f"{value * 100:.0f}%"
    return f"{value:.2f}"


def _print_table(title: str, rows: list[dict[str, Any]], label_key: str) -> None:
    table = Table(title=title, show_header=True)
    table.add_column(label_key)
    table.add_column("games", justify="right")
    table.add_column("W-L", justify="right")
    table.add_column("WR", justify="right")
    table.add_column("KDA", justify="right")
    table.add_column("KP", justify="right")
    for row in rows:
        label = row[label_key]
        if isinstance(label, list):
            label = " / ".join(str(part) for part in label)
        table.add_row(
            str(label),
            str(row["games"]),
            f"{row['wins']}-{row['losses']}",
            _format_optional_float(row["win_rate"], percent=True),
            _format_optional_float(row["avg_kda"]),
            _format_optional_float(row["avg_kill_participation"], percent=True),
        )
    console.print(table)


@app.command("summary")
def summary(
    findings_json: Path = typer.Option(
        _LATEST_FINDINGS_PATH,
        "--findings-json",
        exists=True,
        dir_okay=False,
        help="入力となる latest_findings.json",
    ),
    json_output: bool = typer.Option(False, "--json", help="JSON で出力"),
) -> None:
    """latest_findings.json から対面・ピック傾向を要約する。"""
    payload = build_matchup_summary(load_findings(findings_json))

    if json_output:
        print(json.dumps(payload, ensure_ascii=False))
        return

    console.print(f"[bold]Matchup Summary[/] {payload.get('summoner') or '-'}")
    console.print(f"sample: {payload['sample_size']} games")
    _print_table("Champion Summary", payload["champion_summaries"][:8], "champion")
    _print_table("Lane Opponent Pairs", payload["lane_opponent_pairs"][:8], "opponents")
    _print_table("Watch Opponents", payload["recommendations"]["watch_opponents"], "opponent")


__all__ = ["app", "build_matchup_summary", "load_findings"]
