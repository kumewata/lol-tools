from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from lol_coach import advise
from lol_coach.errors import UsageLimitExceeded


class FakeProvider:
    model = "fake-model"

    def __init__(self, deltas: list[str], fail: Exception | None = None) -> None:
        self.deltas = deltas
        self.fail = fail
        self.calls: list[dict] = []

    def stream(self, *, instructions: str, input_text: str):
        self.calls.append({"instructions": instructions, "input_text": input_text})
        yield from self.deltas
        if self.fail:
            raise self.fail


def test_instructions_are_packaged() -> None:
    text = advise.load_instructions()
    assert "### 優先して取り組むべきこと（TOP 3）" in text
    assert "practice_status" in text


def test_build_input_is_compact_json() -> None:
    raw = advise.build_input(
        {"summoner": "Me#JP1", "matches": [], "findings": []},
        practice_status={"plans": []}, matchup=None, previous=None,
    )
    data = json.loads(raw)
    assert data["summoner"] == "Me#JP1"
    assert data["practice_status"] == {"plans": []}
    assert ", " not in raw


def test_find_previous_snapshot(tmp_path: Path) -> None:
    assert advise.find_previous_snapshot(tmp_path) is None
    for name in ("findings_20260101_000000.json", "findings_20260102_000000.json", "findings_20260103_000000.json"):
        (tmp_path / name).write_text("{}")
    assert advise.find_previous_snapshot(tmp_path).name == "findings_20260102_000000.json"


def test_advise_saves_markdown(tmp_path: Path) -> None:
    provider = FakeProvider(["# 概要\n", "本文"])
    streamed: list[str] = []
    path = advise.generate_advice(
        provider, instructions="sys", input_text="{}", output_dir=tmp_path,
        on_delta=streamed.append, now=lambda: datetime(2026, 10, 3, 12, 0, 0),
    )
    assert path.name == "advice_20261003_120000.md"
    assert path.read_text(encoding="utf-8").endswith("# 概要\n本文")
    assert "fake-model" in path.read_text(encoding="utf-8")
    assert streamed == ["# 概要\n", "本文"]


def test_advise_does_not_save_on_failure(tmp_path: Path) -> None:
    provider = FakeProvider(["partial"], fail=UsageLimitExceeded("limit"))
    with pytest.raises(UsageLimitExceeded):
        advise.generate_advice(provider, instructions="s", input_text="{}", output_dir=tmp_path)
    assert not list(tmp_path.glob("advice_*.md"))
