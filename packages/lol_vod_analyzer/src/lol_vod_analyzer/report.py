"""HTML report generator for LoL VOD analysis."""

from __future__ import annotations

import base64
import webbrowser
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from lol_vod_analyzer.models import AnalysisResult, SceneSnapshot

# __file__ = packages/lol_vod_analyzer/src/lol_vod_analyzer/report.py
PACKAGE_ROOT = Path(__file__).parent.parent.parent
TEMPLATE_DIR = PACKAGE_ROOT / "templates"
DEFAULT_OUTPUT_DIR = PACKAGE_ROOT / "output"


def _format_timestamp(ms: int) -> str:
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def _build_snapshot_data(
    snapshots: list[SceneSnapshot],
) -> list[dict]:
    """Convert snapshots to base64-encoded data for HTML embedding."""
    data = []
    for s in snapshots:
        if not s.image_path.exists():
            continue
        img_bytes = s.image_path.read_bytes()
        suffix = s.image_path.suffix.lower()
        mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
        b64 = base64.b64encode(img_bytes).decode("ascii")
        data.append({
            "timestamp_ms": s.timestamp_ms,
            "data_uri": f"data:{mime};base64,{b64}",
        })
    return data


def generate_report(
    result: AnalysisResult,
    output_dir: Path | None = None,
    open_browser: bool = True,
) -> Path:
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["format_timestamp"] = _format_timestamp

    # Build base64 encoded snapshot data for embedding in HTML
    snapshot_data = _build_snapshot_data(result.snapshots)

    template = env.get_template("report.html")
    html = template.render(result=result, snapshot_data=snapshot_data)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"vod_analysis_{timestamp}.html"
    output_path.write_text(html, encoding="utf-8")

    if open_browser:
        webbrowser.open(f"file://{output_path.resolve()}")

    return output_path
