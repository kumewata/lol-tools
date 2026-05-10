"""Pydantic models for dated practice plans."""

from __future__ import annotations

import re
from datetime import date as date_type, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["critical", "warning", "info"]
Progress = Literal["pending", "in_progress", "done", "keep"]
PlanStatus = Literal["active", "archived"]

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RIOT_ID_PATTERN = re.compile(r"^[^#]+#[^#]+$")


class PlanItem(BaseModel):
    category: str
    severity_at_creation: Severity
    source_finding_message: str
    practice_points: str
    goal: str | None = None
    progress: Progress = "pending"
    user_note: str | None = None


class Plan(BaseModel):
    date: str
    generated_at: datetime
    based_on_snapshot: str
    target_summoner: str
    status: PlanStatus
    items: list[PlanItem] = Field(default_factory=list)

    @field_validator("date")
    @classmethod
    def _validate_date(cls, v: str) -> str:
        if not _DATE_PATTERN.match(v):
            raise ValueError(f"date must match YYYY-MM-DD format, got: {v!r}")
        date_type.fromisoformat(v)
        return v

    @field_validator("target_summoner")
    @classmethod
    def _validate_target_summoner(cls, v: str) -> str:
        if not _RIOT_ID_PATTERN.match(v):
            raise ValueError(f"target_summoner must be 'name#tag' format, got: {v!r}")
        name, tag = v.rsplit("#", 1)
        if not name.strip() or not tag.strip():
            raise ValueError(f"target_summoner name/tag must be non-empty, got: {v!r}")
        return v
