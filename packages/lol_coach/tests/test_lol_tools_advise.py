from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lol_coach.errors import UsageLimitExceeded
from lol_tools import cli, coach

runner = CliRunner()


def _write_findings(root: Path) -> Path:
    out = root / "packages" / "lol_review" / "output"
    out.mkdir(parents=True)
    path = out / "latest_findings.json"
    path.write_text(json.dumps({
        "summoner": "Me#JP1", "total_games": 1, "win_rate": 1.0,
        "matches": [{"match_id": "M1", "champion": "Nautilus", "win": True, "lane_opponents": ["Leona"]}],
        "player_stats": [{"match_id": "M1", "position_timeline": [{"x": 1}]}],
        "findings": [],
    }), encoding="utf-8")
    return path


def _isolate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("LOL_TOOLS_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(coach, "_load_practice_status", lambda summoner: None)


def test_advise_dry_run_needs_no_auth(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    _write_findings(tmp_path)

    result = runner.invoke(cli.app, ["advise", "--no-fetch", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "### 優先して取り組むべきこと（TOP 3）" in result.output
    payload = json.loads(result.output.split("---- input ----\n", 1)[1])
    assert payload["summoner"] == "Me#JP1"
    assert "position_timeline" not in json.dumps(payload)


def test_advise_without_login_fails_with_guidance(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    _write_findings(tmp_path)

    result = runner.invoke(cli.app, ["advise", "--no-fetch", "--model", "gpt-test"])

    assert result.exit_code == 1
    assert "auth chatgpt login" in result.output


def test_advise_reports_usage_limit(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    _write_findings(tmp_path)

    def raise_limit(*args, **kwargs):
        raise UsageLimitExceeded("ChatGPT プランの利用上限に達しました。")

    monkeypatch.setattr(coach, "run_llm_advice", raise_limit)
    result = runner.invoke(cli.app, ["advise", "--no-fetch"])

    assert result.exit_code == 1
    assert "利用上限" in result.output


def test_advise_missing_findings(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, ["advise", "--no-fetch", "--dry-run"])
    assert result.exit_code == 1
    assert "lol-tools review" in result.output


def test_auth_status_when_logged_out(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, ["auth", "chatgpt", "status"])
    assert result.exit_code == 1
    assert "未ログイン" in result.output


def test_default_model_prefers_luna() -> None:
    assert coach.resolve_default_model(["gpt-6-astra", "gpt-5.6-luna"]) == "gpt-5.6-luna"


def test_default_model_falls_back_to_first() -> None:
    assert coach.resolve_default_model(["gpt-6-astra", "gpt-5.5"]) == "gpt-6-astra"
