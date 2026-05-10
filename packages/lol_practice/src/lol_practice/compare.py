"""Compare an active plan against the latest findings to derive progress verdicts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from lol_practice.models import Plan, Severity

VerdictStatus = Literal["done", "improving", "continuing", "manual_done", "manual_keep"]


class FindingRow(BaseModel):
    """A single row from the DuckDB findings table (read-only view)."""

    snapshot_id: str
    summoner: str
    category: str
    severity: Severity


class ProgressVerdict(BaseModel):
    item_index: int
    category: str
    source_severity: Severity
    current_severity: Severity | None
    status: VerdictStatus


_RANK = {None: 0, "info": 1, "warning": 2, "critical": 3}


def severity_rank(value: Severity | None) -> int:
    return _RANK.get(value, 0)


def _highest_severity_for_category(
    findings: list[FindingRow], category: str
) -> Severity | None:
    """Return the most severe severity present for a category, or None if absent."""
    matching = [f for f in findings if f.category == category]
    if not matching:
        return None
    return max(matching, key=lambda f: severity_rank(f.severity)).severity


def evaluate_progress(
    plan: Plan,
    current_findings: list[FindingRow],
    *,
    lane_opponents: list[dict] | None = None,
    champion_stats: list[dict] | None = None,
) -> list[ProgressVerdict]:
    """Evaluate each plan item against the latest findings.

    The ``lane_opponents`` and ``champion_stats`` keyword arguments exist to
    accommodate B-domain (matchup / meta) integration in a future iteration
    without changing this signature; they are intentionally unused here.
    """
    _ = lane_opponents, champion_stats  # reserved for future use

    verdicts: list[ProgressVerdict] = []
    for index, item in enumerate(plan.items):
        current_severity = _highest_severity_for_category(current_findings, item.category)

        if item.progress == "done":
            status: VerdictStatus = "manual_done"
        elif item.progress == "keep":
            status = "manual_keep"
        else:
            current_rank = severity_rank(current_severity)
            source_rank = severity_rank(item.severity_at_creation)
            if current_severity is None:
                status = "done"
            elif current_rank < source_rank:
                status = "improving"
            else:
                status = "continuing"

        verdicts.append(
            ProgressVerdict(
                item_index=index,
                category=item.category,
                source_severity=item.severity_at_creation,
                current_severity=current_severity,
                status=status,
            )
        )
    return verdicts


__all__ = [
    "FindingRow",
    "ProgressVerdict",
    "VerdictStatus",
    "severity_rank",
    "evaluate_progress",
]
