"""Typer subapp for `lol-tools practice` (list / show / status)."""

from __future__ import annotations

import json
import os
from datetime import date as date_type, datetime
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from lol_practice import store
from lol_practice.compare import severity_rank
from lol_practice.compare import FindingRow, evaluate_progress
from lol_practice.models import Plan, PlanItem, Severity

console = Console()
app = typer.Typer(help="練習プラン CLI（生成はスキル側、ここでは閲覧と進捗確認）")

# Repo layout:
# packages/lol_practice/src/lol_practice/cli.py
# 4 parents up = repo root.
_PACKAGE_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _PACKAGE_DIR.parent.parent
_ENV_PATH = _REPO_ROOT / ".env"
_DB_PATH = _REPO_ROOT / "packages" / "lol_dashboard" / "data" / "lol_history.duckdb"
_LATEST_FINDINGS_PATH = _REPO_ROOT / "packages" / "lol_review" / "output" / "latest_findings.json"


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


def _resolve_latest_findings_path() -> Path:
    return _LATEST_FINDINGS_PATH


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


def _load_latest_findings(path: Path) -> dict[str, Any]:
    if not path.exists():
        console.print(f"[red]Error:[/] latest_findings.json が見つかりません: {path}")
        raise typer.Exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def _finding_source_message(findings: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for finding in findings:
        message = str(finding.get("message", "")).strip()
        detail = str(finding.get("detail", "")).strip()
        if message and detail:
            parts.append(f"{message}（{detail}）")
        elif message:
            parts.append(message)
        elif detail:
            parts.append(detail)
    return " / ".join(parts)


def _practice_points_for(category: str, severity: Severity, source_message: str) -> str:
    if category == "cs":
        return (
            "次の試合では CS 関連の判断を1つだけ固定して確認する。BOT では10分時点のCSを、"
            "サポートではサポートアイテムのスタック消化とローム前後のウェーブ状態を試合後に見直す。"
        )
    if category == "kill_participation":
        return (
            "レーン後は味方JGとドラゴン周辺の位置を先に確認し、参加できる戦闘だけを選ぶ。"
            "KP が低い試合は、戦闘開始時に自分がどのレーン/川にいたかをリプレイで確認する。"
        )
    severity_label = {"critical": "重大", "warning": "継続", "info": "観察"}[severity]
    return f"{severity_label}課題として、次の試合後に原因を1つだけ記録する: {source_message}"


def _goal_for(category: str, severity: Severity, source_message: str) -> str | None:
    if category == "cs":
        return "BOT は 7.0 CS/min、サポートは 1.5 CS/min を目安に、次回は前回平均を上回る。"
    if category == "kill_participation":
        return "サポート KP 50% 以上、BOT KP 35% 以上を目安に、低参加の試合を減らす。"
    if severity == "critical":
        return "次回レビューで critical から warning 以下に下げる。"
    if severity == "warning":
        return "次回レビューで warning を維持せず、info 以下または消失を目指す。"
    return None


def _items_from_findings(findings: list[dict[str, Any]]) -> list[PlanItem]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        category = str(finding.get("category", "")).strip()
        severity = finding.get("severity")
        if not category or severity not in {"critical", "warning", "info"}:
            continue
        grouped.setdefault(category, []).append(finding)

    items: list[PlanItem] = []
    for category, category_findings in grouped.items():
        category_findings.sort(
            key=lambda f: severity_rank(f.get("severity")), reverse=True
        )
        severity = category_findings[0]["severity"]
        source_message = _finding_source_message(category_findings)
        items.append(
            PlanItem(
                category=category,
                severity_at_creation=severity,
                source_finding_message=source_message,
                practice_points=_practice_points_for(category, severity, source_message),
                goal=_goal_for(category, severity, source_message),
                progress="pending",
                user_note=None,
            )
        )

    items.sort(
        key=lambda item: (severity_rank(item.severity_at_creation), item.category),
        reverse=True,
    )
    return items


def _build_plan_from_latest_findings(
    data: dict[str, Any], *, plan_date: str, generated_at: datetime
) -> Plan:
    summoner = str(data.get("summoner") or _resolve_target_summoner())
    snapshot = str(data.get("generated_at") or generated_at.isoformat())
    findings = data.get("findings")
    if not isinstance(findings, list):
        findings = []
    return Plan(
        date=plan_date,
        generated_at=generated_at,
        based_on_snapshot=snapshot,
        target_summoner=summoner,
        status="active",
        items=_items_from_findings(findings),
    )


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


@app.command("generate")
def generate_plan(
    findings_json: Path | None = typer.Option(
        None,
        "--findings-json",
        help="入力する latest_findings.json。省略時は packages/lol_review/output/latest_findings.json",
    ),
    date: str | None = typer.Option(None, "--date", help="作成する日付（YYYY-MM-DD）。省略時は今日"),
    force: bool = typer.Option(False, "--force", help="同じ日付の既存プランを上書きする"),
    json_output: bool = typer.Option(False, "--json", help="生成結果を JSON で出力"),
) -> None:
    """latest_findings.json から当日プランを作成する。既存同日プランは既定で保持する。"""
    target_date = date or store.date_label(date_type.today())
    existing_path = store.plans_dir() / f"{target_date}.md"
    if existing_path.exists() and not force:
        if json_output:
            print(
                json.dumps(
                    {
                        "created": False,
                        "date": target_date,
                        "path": str(existing_path),
                        "reason": "already_exists",
                    },
                    ensure_ascii=False,
                )
            )
        else:
            console.print(f"[yellow]既存プランを保持しました:[/] {existing_path}")
        return

    source_path = findings_json or _resolve_latest_findings_path()
    data = _load_latest_findings(source_path)
    plan = _build_plan_from_latest_findings(
        data,
        plan_date=target_date,
        generated_at=datetime.now().astimezone(),
    )
    path = store.save_plan(plan)

    if json_output:
        print(
            json.dumps(
                {
                    "created": True,
                    "date": plan.date,
                    "path": str(path),
                    "items": [
                        {
                            "category": item.category,
                            "severity": item.severity_at_creation,
                        }
                        for item in plan.items
                    ],
                },
                ensure_ascii=False,
            )
        )
    else:
        console.print(f"[green]練習プランを作成しました:[/] {path}")


def _find_plan(date: str | None) -> Plan | None:
    if date is None:
        return store.latest_plan()
    files = store.list_plans()
    for path in files:
        if path.stem == date:
            return store.load_plan(path)
    return None


__all__ = ["app"]
