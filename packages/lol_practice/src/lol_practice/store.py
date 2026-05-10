"""Plan storage: date labels, Markdown round-trip, plans/ directory I/O."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import frontmatter

from lol_practice.models import Plan, PlanItem

_PACKAGE_DIR = Path(__file__).resolve().parent.parent.parent
_PLANS_DIR = _PACKAGE_DIR / "plans"

_HEADING_RE = re.compile(r"^##\s+\d+\.\s+([A-Za-z0-9_]+)\s*/\s*([a-z]+)\s*$")
_FIELD_RE = re.compile(r"^-\s+\*\*([^*]+)\*\*:\s*(.*)$")


def plans_dir() -> Path:
    """Return the plans directory (allow tests to monkeypatch _PLANS_DIR)."""
    return _PLANS_DIR


def date_label(d: date) -> str:
    """Return a stable plan date label `YYYY-MM-DD` for the given date."""
    return d.isoformat()


def _plan_path(plan: Plan) -> Path:
    return plans_dir() / f"{plan.date}.md"


def to_markdown(plan: Plan) -> str:
    """Serialize a Plan to a Markdown document with YAML frontmatter."""
    meta = {
        "date": plan.date,
        "generated_at": plan.generated_at.isoformat(),
        "based_on_snapshot": plan.based_on_snapshot,
        "target_summoner": plan.target_summoner,
        "status": plan.status,
    }
    body_lines: list[str] = [f"# {plan.date} 練習プラン", ""]
    for idx, item in enumerate(plan.items, start=1):
        body_lines.append(f"## {idx}. {item.category} / {item.severity_at_creation}")
        body_lines.append(f"- **元 finding**: {item.source_finding_message}")
        body_lines.append(f"- **練習ポイント**: {item.practice_points}")
        body_lines.append(f"- **目標**: {item.goal or ''}")
        body_lines.append(f"- **進捗**: {item.progress}")
        body_lines.append(f"- **note**: {item.user_note or ''}")
        body_lines.append("")

    body = "\n".join(body_lines).rstrip() + "\n"
    fm = frontmatter.Post(content=body, **meta)
    return frontmatter.dumps(fm) + "\n"


def from_markdown(text: str) -> Plan:
    """Deserialize a Markdown document back into a Plan."""
    fm = frontmatter.loads(text)
    items = _parse_items(fm.content)
    return Plan(
        date=fm["date"],
        generated_at=_coerce_datetime(fm["generated_at"]),
        based_on_snapshot=fm["based_on_snapshot"],
        target_summoner=fm["target_summoner"],
        status=fm["status"],
        items=items,
    )


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"generated_at must be datetime or ISO string, got: {type(value)!r}")


def _parse_items(body: str) -> list[PlanItem]:
    items: list[PlanItem] = []
    current: dict[str, str] | None = None

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            if current is not None:
                items.append(_finalize_item(current))
            current = {
                "category": heading_match.group(1),
                "severity_at_creation": heading_match.group(2),
            }
            continue

        if current is None:
            continue

        field_match = _FIELD_RE.match(line)
        if not field_match:
            continue
        key = field_match.group(1).strip()
        value = field_match.group(2).strip()
        normalized = _FIELD_KEY_MAP.get(key)
        if normalized is None:
            continue
        current[normalized] = value

    if current is not None:
        items.append(_finalize_item(current))

    return items


_FIELD_KEY_MAP = {
    "元 finding": "source_finding_message",
    "練習ポイント": "practice_points",
    "目標": "goal",
    "進捗": "progress",
    "note": "user_note",
}


def _finalize_item(buf: dict[str, str]) -> PlanItem:
    return PlanItem(
        category=buf["category"],
        severity_at_creation=buf["severity_at_creation"],  # type: ignore[arg-type]
        source_finding_message=buf.get("source_finding_message", ""),
        practice_points=buf.get("practice_points", ""),
        goal=buf.get("goal") or None,
        progress=buf.get("progress", "pending"),  # type: ignore[arg-type]
        user_note=buf.get("user_note") or None,
    )


def save_plan(plan: Plan) -> Path:
    """Write the plan as Markdown to plans/{date}.md (overwrites existing)."""
    plans_dir().mkdir(parents=True, exist_ok=True)
    path = _plan_path(plan)
    path.write_text(to_markdown(plan), encoding="utf-8")
    return path


def load_plan(path: Path) -> Plan:
    """Read a plan Markdown file. Raises on invalid frontmatter or model errors."""
    text = path.read_text(encoding="utf-8")
    return from_markdown(text)


def list_plans() -> list[Path]:
    """List plan files in plans/ sorted by date descending (newest first)."""
    directory = plans_dir()
    if not directory.exists():
        return []
    files = [p for p in directory.glob("*.md") if p.name != ".gitkeep"]
    files.sort(key=lambda p: p.stem, reverse=True)
    return files


def latest_plan() -> Plan | None:
    """Return the latest plan (highest date label) or None."""
    files = list_plans()
    if not files:
        return None
    return load_plan(files[0])


__all__ = [
    "date_label",
    "plans_dir",
    "to_markdown",
    "from_markdown",
    "save_plan",
    "load_plan",
    "list_plans",
    "latest_plan",
]
