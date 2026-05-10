"""Tests for lol_practice.compare (TDD)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def base_plan():
    from lol_practice.models import Plan, PlanItem

    return Plan(
        date="2026-05-10",
        generated_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
        based_on_snapshot="snap_old",
        target_summoner="kumewata#JP1",
        status="active",
        items=[
            PlanItem(
                category="cs",
                severity_at_creation="critical",
                source_finding_message="CS/min が非常に低い（ボット）",
                practice_points="practice",
                progress="pending",
            ),
            PlanItem(
                category="kill_participation",
                severity_at_creation="warning",
                source_finding_message="キル参加率が低い",
                practice_points="practice",
                progress="pending",
            ),
        ],
    )


def make_finding(category: str, severity: str):
    from lol_practice.compare import FindingRow

    return FindingRow(
        snapshot_id="snap_new",
        summoner="kumewata#JP1",
        category=category,
        severity=severity,
    )


def test_severity_rank_function():
    from lol_practice.compare import severity_rank

    assert severity_rank(None) == 0
    assert severity_rank("info") == 1
    assert severity_rank("warning") == 2
    assert severity_rank("critical") == 3


def test_finding_disappeared_marks_done(base_plan):
    """元 critical で最新 findings に該当 category がない → done。"""
    from lol_practice.compare import evaluate_progress

    current = [make_finding("kill_participation", "warning")]
    verdicts = evaluate_progress(base_plan, current)
    by_cat = {v.category: v for v in verdicts}
    assert by_cat["cs"].status == "done"
    assert by_cat["cs"].current_severity is None


def test_severity_lowered_marks_improving(base_plan):
    """元 critical → 最新 warning → improving。"""
    from lol_practice.compare import evaluate_progress

    current = [
        make_finding("cs", "warning"),
        make_finding("kill_participation", "warning"),
    ]
    verdicts = evaluate_progress(base_plan, current)
    by_cat = {v.category: v for v in verdicts}
    assert by_cat["cs"].status == "improving"
    assert by_cat["cs"].current_severity == "warning"


def test_severity_unchanged_marks_continuing(base_plan):
    """元 warning と最新 warning が同じ → continuing。"""
    from lol_practice.compare import evaluate_progress

    current = [
        make_finding("cs", "critical"),
        make_finding("kill_participation", "warning"),
    ]
    verdicts = evaluate_progress(base_plan, current)
    by_cat = {v.category: v for v in verdicts}
    assert by_cat["kill_participation"].status == "continuing"


def test_severity_worsened_marks_continuing(base_plan):
    """元 warning → 最新 critical（悪化）も continuing として扱う（done ではない）。"""
    from lol_practice.compare import evaluate_progress

    current = [
        make_finding("cs", "critical"),
        make_finding("kill_participation", "critical"),
    ]
    verdicts = evaluate_progress(base_plan, current)
    by_cat = {v.category: v for v in verdicts}
    assert by_cat["kill_participation"].status == "continuing"


def test_manual_done_is_preserved(base_plan):
    """手動で progress=done を付けた item は自動判定で上書きされない。"""
    from lol_practice.compare import evaluate_progress

    base_plan.items[0].progress = "done"
    current = [
        make_finding("cs", "critical"),  # まだ critical のまま
        make_finding("kill_participation", "warning"),
    ]
    verdicts = evaluate_progress(base_plan, current)
    by_cat = {v.category: v for v in verdicts}
    assert by_cat["cs"].status == "manual_done"


def test_manual_keep_is_preserved(base_plan):
    """手動で progress=keep を付けた item は自動判定で上書きされない。"""
    from lol_practice.compare import evaluate_progress

    base_plan.items[1].progress = "keep"
    current = [make_finding("cs", "critical")]
    verdicts = evaluate_progress(base_plan, current)
    by_cat = {v.category: v for v in verdicts}
    assert by_cat["kill_participation"].status == "manual_keep"


def test_b_domain_kwargs_do_not_crash(base_plan):
    """将来の B 領域連携用引数（lane_opponents, champion_stats）を渡しても crash しない。"""
    from lol_practice.compare import evaluate_progress

    current = [make_finding("cs", "warning"), make_finding("kill_participation", "warning")]
    verdicts = evaluate_progress(
        base_plan,
        current,
        lane_opponents=[{"champion": "Blitzcrank"}],
        champion_stats=[{"champion": "Thresh", "wins": 2}],
    )
    assert len(verdicts) == 2  # plan 上の項目数


def test_new_findings_not_in_plan_are_ignored(base_plan):
    """プランにない新規 category（vision など）は verdict に含めない（プラン側の項目だけ評価する）。"""
    from lol_practice.compare import evaluate_progress

    current = [
        make_finding("cs", "warning"),
        make_finding("kill_participation", "warning"),
        make_finding("vision", "warning"),  # プランにない
    ]
    verdicts = evaluate_progress(base_plan, current)
    assert {v.category for v in verdicts} == {"cs", "kill_participation"}


def test_in_progress_items_get_auto_evaluated(base_plan):
    """progress=in_progress の項目は自動判定の対象（done でも keep でもない）。"""
    from lol_practice.compare import evaluate_progress

    base_plan.items[0].progress = "in_progress"
    current: list = []  # 全部消失
    verdicts = evaluate_progress(base_plan, current)
    by_cat = {v.category: v for v in verdicts}
    assert by_cat["cs"].status == "done"


def test_verdict_includes_source_severity(base_plan):
    from lol_practice.compare import evaluate_progress

    current = [make_finding("cs", "warning")]
    verdicts = evaluate_progress(base_plan, current)
    by_cat = {v.category: v for v in verdicts}
    assert by_cat["cs"].source_severity == "critical"
