"""Tests for lol_practice.store (TDD)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def sample_plan():
    from lol_practice.models import Plan, PlanItem

    return Plan(
        date="2026-05-10",
        generated_at=datetime(2026, 5, 10, 12, 34, 56, tzinfo=timezone.utc),
        based_on_snapshot="snap_20260510_001",
        target_summoner="kumewata#JP1",
        status="active",
        items=[
            PlanItem(
                category="cs",
                severity_at_creation="critical",
                source_finding_message="CS/min が非常に低い（ボット）",
                practice_points="ウェーブクリアと CS の取りこぼしを意識する",
                goal="10 分時点で 70 CS",
                progress="pending",
                user_note=None,
            ),
            PlanItem(
                category="kill_participation",
                severity_at_creation="warning",
                source_finding_message="キル参加率が低い（ボット）",
                practice_points="ローテーションを意識する",
                goal="KP 50% 以上",
                progress="pending",
                user_note=None,
            ),
        ],
    )


def test_date_label_returns_iso_date():
    from lol_practice.store import date_label

    assert date_label(date(2026, 5, 10)) == "2026-05-10"
    assert date_label(date(2026, 1, 5)) == "2026-01-05"


def test_date_label_year_boundary():
    """年またぎでもカレンダー日付をそのまま使う。"""
    from lol_practice.store import date_label

    assert date_label(date(2025, 12, 29)) == "2025-12-29"
    assert date_label(date(2026, 1, 1)) == "2026-01-01"
    assert date_label(date(2024, 12, 30)) == "2024-12-30"
    assert date_label(date(2020, 12, 28)) == "2020-12-28"


def test_to_markdown_round_trip(sample_plan):
    """Plan → Markdown → Plan で内容が一致する。"""
    from lol_practice.store import from_markdown, to_markdown

    md = to_markdown(sample_plan)
    restored = from_markdown(md)

    assert restored.date == sample_plan.date
    assert restored.based_on_snapshot == sample_plan.based_on_snapshot
    assert restored.target_summoner == sample_plan.target_summoner
    assert restored.status == sample_plan.status
    assert len(restored.items) == len(sample_plan.items)
    for r, s in zip(restored.items, sample_plan.items):
        assert r.category == s.category
        assert r.severity_at_creation == s.severity_at_creation
        assert r.source_finding_message == s.source_finding_message
        assert r.practice_points == s.practice_points
        assert r.goal == s.goal
        assert r.progress == s.progress
        assert r.user_note == s.user_note


def test_save_and_load_plan_roundtrip(tmp_path, monkeypatch, sample_plan):
    from lol_practice import store

    monkeypatch.setattr(store, "_PLANS_DIR", tmp_path)

    saved_path = store.save_plan(sample_plan)
    assert saved_path.exists()
    assert saved_path.name == "2026-05-10.md"

    loaded = store.load_plan(saved_path)
    assert loaded.date == sample_plan.date
    assert len(loaded.items) == 2


def test_list_plans_returns_empty_when_no_plans(tmp_path, monkeypatch):
    from lol_practice import store

    monkeypatch.setattr(store, "_PLANS_DIR", tmp_path)
    assert store.list_plans() == []


def test_latest_plan_returns_none_when_no_plans(tmp_path, monkeypatch):
    from lol_practice import store

    monkeypatch.setattr(store, "_PLANS_DIR", tmp_path)
    assert store.latest_plan() is None


def test_list_plans_sorted_by_date_descending(tmp_path, monkeypatch, sample_plan):
    from lol_practice import store
    from lol_practice.models import Plan

    monkeypatch.setattr(store, "_PLANS_DIR", tmp_path)

    # 3 つのプランを作成
    p1 = sample_plan.model_copy(update={"date": "2026-05-10"})
    p2 = sample_plan.model_copy(update={"date": "2026-05-17"})
    p3 = sample_plan.model_copy(update={"date": "2026-05-24"})
    for p in (p1, p2, p3):
        store.save_plan(p)

    plans = store.list_plans()
    assert [p.name for p in plans] == ["2026-05-24.md", "2026-05-17.md", "2026-05-10.md"]


def test_latest_plan_returns_most_recent_date(tmp_path, monkeypatch, sample_plan):
    from lol_practice import store

    monkeypatch.setattr(store, "_PLANS_DIR", tmp_path)
    p1 = sample_plan.model_copy(update={"date": "2026-05-10"})
    p2 = sample_plan.model_copy(update={"date": "2026-05-24"})
    p3 = sample_plan.model_copy(update={"date": "2026-05-17"})
    for p in (p1, p2, p3):
        store.save_plan(p)

    latest = store.latest_plan()
    assert latest is not None
    assert latest.date == "2026-05-24"


def test_manual_progress_done_is_preserved_on_load(tmp_path, monkeypatch, sample_plan):
    """ユーザーが Markdown を手で `**進捗**: done` に書き換えた場合、
    load_plan が done を読み戻せること。"""
    from lol_practice import store

    monkeypatch.setattr(store, "_PLANS_DIR", tmp_path)
    saved_path = store.save_plan(sample_plan)

    text = saved_path.read_text(encoding="utf-8")
    text = text.replace(
        "- **進捗**: pending",
        "- **進捗**: done",
        1,  # 最初の 1 件だけ書き換え
    )
    saved_path.write_text(text, encoding="utf-8")

    loaded = store.load_plan(saved_path)
    assert loaded.items[0].progress == "done"
    assert loaded.items[1].progress == "pending"


def test_save_plan_is_idempotent_for_same_date(tmp_path, monkeypatch, sample_plan):
    """同じ日付で save_plan を 2 回呼んでもファイルは 1 つで上書きされる。"""
    from lol_practice import store

    monkeypatch.setattr(store, "_PLANS_DIR", tmp_path)

    store.save_plan(sample_plan)
    updated = sample_plan.model_copy(update={"based_on_snapshot": "snap_xxx"})
    store.save_plan(updated)

    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    loaded = store.load_plan(files[0])
    assert loaded.based_on_snapshot == "snap_xxx"


def test_invalid_frontmatter_raises_on_load(tmp_path, monkeypatch):
    """壊れた frontmatter のファイルは load_plan で例外を上げる。"""
    from lol_practice import store

    monkeypatch.setattr(store, "_PLANS_DIR", tmp_path)
    bad = tmp_path / "broken.md"
    bad.write_text("---\ndate: nope\n---\n# broken\n", encoding="utf-8")

    with pytest.raises(Exception):
        store.load_plan(bad)


def test_yaml_implicit_scalar_types_are_coerced(tmp_path, monkeypatch):
    """YAML が date/int として読んだ frontmatter も Plan では文字列に戻す。"""
    from lol_practice import store

    monkeypatch.setattr(store, "_PLANS_DIR", tmp_path)
    path = tmp_path / "2026-05-10.md"
    path.write_text(
        """---
date: 2026-05-10
generated_at: 2026-05-10T13:57:42+09:00
based_on_snapshot: 20260510135640
target_summoner: apililili#3197
status: active
---

# 2026-05-10 練習プラン
""",
        encoding="utf-8",
    )

    loaded = store.load_plan(path)
    assert loaded.date == "2026-05-10"
    assert loaded.based_on_snapshot == "20260510135640"


def test_user_note_round_trip(tmp_path, monkeypatch, sample_plan):
    """user_note に書いた内容も round-trip する。"""
    from lol_practice import store
    from lol_practice.models import PlanItem

    monkeypatch.setattr(store, "_PLANS_DIR", tmp_path)
    sample_plan.items[0] = PlanItem(
        category="cs",
        severity_at_creation="critical",
        source_finding_message="x",
        practice_points="y",
        goal=None,
        progress="in_progress",
        user_note="今週はジャングルに集中",
    )
    path = store.save_plan(sample_plan)
    loaded = store.load_plan(path)
    assert loaded.items[0].user_note == "今週はジャングルに集中"
    assert loaded.items[0].progress == "in_progress"
