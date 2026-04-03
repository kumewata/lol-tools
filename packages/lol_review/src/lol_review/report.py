"""HTML report generator for LoL match analysis."""

from __future__ import annotations

import json
import math
import webbrowser
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from lol_review.advisor import Finding, analyze_findings
from lol_review.models import AnalysisResult

# Source checkout: packages/lol_review/src/lol_review/report.py -> packages/lol_review/
_PACKAGE_ROOT = Path(__file__).parent.parent.parent
# Installed wheel: templates are included alongside the package
_INSTALLED_TEMPLATE_DIR = Path(__file__).parent / "templates"
_INSTALLED_REPORT_TEMPLATE = _INSTALLED_TEMPLATE_DIR / "report.html"
TEMPLATE_DIR = (
    _INSTALLED_TEMPLATE_DIR
    if _INSTALLED_REPORT_TEMPLATE.is_file()
    else _PACKAGE_ROOT / "templates"
)
OUTPUT_DIR = _PACKAGE_ROOT / "output"


def range_list(n: int) -> list[int]:
    """Jinja2 filter: generate [0, 1, ..., n-1]"""
    return list(range(n))


def _sanitize_for_json(obj: object) -> object:
    """Recursively replace float('inf') / float('-inf') / NaN with None.

    Handles dict and list containers. Tuples and other iterables are left as-is
    (current models only produce dict/list from model_dump()).
    """
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def generate_report(result: AnalysisResult, open_browser: bool = True) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["range_list"] = range_list
    template = env.get_template("report.html")

    # Pass sanitized Python objects to the template.
    # The tojson filter in the template handles final JSON serialization and
    # ensures </script> sequences are escaped within <script> blocks.
    matches_data = _sanitize_for_json([m.model_dump() for m in result.matches])
    champion_stats_data = _sanitize_for_json(
        [c.model_dump() for c in result.champion_stats]
    )
    player_stats_map = {ps.match_id: ps for ps in result.player_stats}

    avg_kda = result.avg_kda
    avg_kda_display = "∞" if not math.isfinite(avg_kda) else f"{avg_kda:.2f}"

    html = template.render(
        result=result,
        avg_kda_display=avg_kda_display,
        matches_data=matches_data,
        champion_stats_data=champion_stats_data,
        player_stats_map=player_stats_map,
    )

    # Generate findings
    findings = analyze_findings(result)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"lol_review_{timestamp}.html"
    output_path.write_text(html, encoding="utf-8")

    # Save findings + summary as JSON for /lol-advice skill
    findings_data = {
        "summoner": f"{result.summoner_name}#{result.tag_line}",
        "total_games": result.total_games,
        "wins": result.wins,
        "losses": result.losses,
        "win_rate": result.win_rate,
        "avg_kda": result.avg_kda if math.isfinite(result.avg_kda) else None,
        "avg_cs_per_min": result.avg_cs_per_min,
        "champion_stats": _sanitize_for_json(
            [c.model_dump() for c in result.champion_stats]
        ),
        "matches": _sanitize_for_json(
            [m.model_dump() for m in result.matches]
        ),
        "player_stats": _sanitize_for_json(
            [ps.model_dump() for ps in result.player_stats]
        ),
        "findings": [f.to_dict() for f in findings],
        "report_html": output_path.name,
        "generated_at": timestamp,
    }
    findings_json = json.dumps(findings_data, ensure_ascii=False, indent=2)
    # Latest (overwritten each time)
    findings_path = OUTPUT_DIR / "latest_findings.json"
    findings_path.write_text(findings_json, encoding="utf-8")
    # Timestamped snapshot
    snapshot_path = OUTPUT_DIR / f"findings_{timestamp}.json"
    snapshot_path.write_text(findings_json, encoding="utf-8")

    if open_browser:
        webbrowser.open(f"file://{output_path.resolve()}")
    return output_path
