from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import lol_review.cli as review_module
import lol_tools.cli as root_cli
import lol_vod_analyzer.main as vod_module


runner = CliRunner()


def test_review_missing_riot_id_mentions_doctor_and_init(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(root_cli, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(review_module, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("DEFAULT_RIOT_ID", raising=False)
    monkeypatch.setenv("RIOT_API_KEY", "dummy-key")

    result = runner.invoke(root_cli.app, ["review"])

    assert result.exit_code != 0
    assert "uv run lol-tools review" in result.output
    assert "uv run lol-tools doctor" in result.output
    assert "uv run lol-tools init" in result.output


def test_review_missing_api_key_mentions_init_and_doctor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(root_cli, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(review_module, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("DEFAULT_RIOT_ID", "Player#JP1")
    monkeypatch.delenv("RIOT_API_KEY", raising=False)

    result = runner.invoke(root_cli.app, ["review"])

    assert result.exit_code != 0
    assert "uv run lol-tools init" in result.output
    assert "uv run lol-tools doctor" in result.output


def test_vod_missing_google_api_key_mentions_init_and_doctor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(vod_module, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    result = runner.invoke(root_cli.app, ["vod", "analyze", "https://youtube.com/watch?v=test"])

    assert result.exit_code != 0
    assert "uv run lol-tools init" in result.output
    assert "uv run lol-tools doctor" in result.output


def test_vod_missing_local_file_mentions_examples(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-key")

    result = runner.invoke(root_cli.app, ["vod", "analyze", "/tmp/does-not-exist.mp4"])

    assert result.exit_code != 0
    assert "uv run lol-tools examples" in result.output


def test_vod_local_analysis_reports_missing_tools(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "replay.mp4"
    video_path.write_text("dummy", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-key")
    monkeypatch.setattr(vod_module, "missing_tools", lambda tools: ["ffprobe", "ffmpeg"])

    result = runner.invoke(root_cli.app, ["vod", "analyze", str(video_path)])

    assert result.exit_code != 0
    assert "ffprobe" in result.output
    assert "ffmpeg" in result.output
    assert "lol-tools doctor" in result.output
