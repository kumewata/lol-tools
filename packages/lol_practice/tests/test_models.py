"""Tests for lol_practice.models (TDD red phase first)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


def test_plan_item_minimum_fields():
    from lol_practice.models import PlanItem

    item = PlanItem(
        category="cs",
        severity_at_creation="critical",
        source_finding_message="CS/min が非常に低い（ボット）",
        practice_points="ウェーブクリアと CS の取りこぼしを意識する",
        goal="10 分時点で 70 CS",
        progress="pending",
        user_note=None,
    )
    assert item.category == "cs"
    assert item.severity_at_creation == "critical"
    assert item.progress == "pending"


def test_plan_item_severity_must_be_enum():
    from lol_practice.models import PlanItem

    with pytest.raises(ValidationError):
        PlanItem(
            category="cs",
            severity_at_creation="major",  # 不正値
            source_finding_message="x",
            practice_points="x",
            goal=None,
            progress="pending",
            user_note=None,
        )


def test_plan_item_progress_must_be_enum():
    from lol_practice.models import PlanItem

    with pytest.raises(ValidationError):
        PlanItem(
            category="cs",
            severity_at_creation="warning",
            source_finding_message="x",
            practice_points="x",
            goal=None,
            progress="halfway",  # 不正値
            user_note=None,
        )


def test_plan_item_optional_fields_default_to_none():
    from lol_practice.models import PlanItem

    item = PlanItem(
        category="cs",
        severity_at_creation="warning",
        source_finding_message="msg",
        practice_points="pp",
    )
    assert item.goal is None
    assert item.progress == "pending"
    assert item.user_note is None


def test_plan_minimum_fields():
    from lol_practice.models import Plan, PlanItem

    plan = Plan(
        date="2026-05-10",
        generated_at=datetime(2026, 5, 10, 12, 34, 56, tzinfo=timezone.utc),
        based_on_snapshot="snap_20260510_001",
        target_summoner="kumewata#JP1",
        status="active",
        items=[
            PlanItem(
                category="cs",
                severity_at_creation="critical",
                source_finding_message="x",
                practice_points="y",
            )
        ],
    )
    assert plan.date == "2026-05-10"
    assert plan.status == "active"
    assert len(plan.items) == 1


def test_plan_date_format_validation():
    from lol_practice.models import Plan, PlanItem

    item = PlanItem(
        category="cs",
        severity_at_creation="warning",
        source_finding_message="x",
        practice_points="y",
    )
    # 不正な date
    for bad in ["2026", "2026-05", "26-05-10", "2026/05/10", "2026-W19"]:
        with pytest.raises(ValidationError):
            Plan(
                date=bad,
                generated_at=datetime.now(timezone.utc),
                based_on_snapshot="s",
                target_summoner="a#b",
                status="active",
                items=[item],
            )


def test_plan_target_summoner_format():
    from lol_practice.models import Plan, PlanItem

    item = PlanItem(
        category="cs",
        severity_at_creation="warning",
        source_finding_message="x",
        practice_points="y",
    )
    # `name#tag` 形式必須
    with pytest.raises(ValidationError):
        Plan(
            date="2026-05-10",
            generated_at=datetime.now(timezone.utc),
            based_on_snapshot="s",
            target_summoner="kumewata",  # # がない
            status="active",
            items=[item],
        )

    with pytest.raises(ValidationError):
        Plan(
            date="2026-05-10",
            generated_at=datetime.now(timezone.utc),
            based_on_snapshot="s",
            target_summoner="#JP1",  # name が空
            status="active",
            items=[item],
        )


def test_plan_status_enum():
    from lol_practice.models import Plan, PlanItem

    item = PlanItem(
        category="cs",
        severity_at_creation="warning",
        source_finding_message="x",
        practice_points="y",
    )
    with pytest.raises(ValidationError):
        Plan(
            date="2026-05-10",
            generated_at=datetime.now(timezone.utc),
            based_on_snapshot="s",
            target_summoner="a#b",
            status="draft",  # 不正値
            items=[item],
        )


def test_plan_allows_empty_items():
    """findings が空のときに plan を空配列で作れる必要がある（運用上のレジリエンス）。"""
    from lol_practice.models import Plan

    plan = Plan(
        date="2026-05-10",
        generated_at=datetime.now(timezone.utc),
        based_on_snapshot="s",
        target_summoner="a#b",
        status="active",
        items=[],
    )
    assert plan.items == []
