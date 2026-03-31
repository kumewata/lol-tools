from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lol_tools import cli


runner = CliRunner()


def test_init_non_interactive_creates_env_from_example(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    example_path = tmp_path / ".env.example"
    example_path.write_text(
        "\n".join(
            [
                "RIOT_API_KEY=your_riot_api_key_here",
                "GOOGLE_API_KEY=your_google_api_key_here",
                "DEFAULT_RIOT_ID=SummonerName#JP1",
                "DEFAULT_COUNT=20",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "ENV_PATH", env_path)
    monkeypatch.setattr(cli, "ENV_EXAMPLE_PATH", example_path)

    result = runner.invoke(
        cli.app,
        [
            "init",
            "--non-interactive",
            "--riot-api-key",
            "riot-test-key",
            "--default-riot-id",
            "Player#JP1",
            "--default-count",
            "5",
        ],
    )

    assert result.exit_code == 0
    content = env_path.read_text(encoding="utf-8")
    assert "RIOT_API_KEY=riot-test-key" in content
    assert "DEFAULT_RIOT_ID=Player#JP1" in content
    assert "DEFAULT_COUNT=5" in content


def test_init_rejects_invalid_default_riot_id(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    example_path = tmp_path / ".env.example"
    example_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(cli, "ENV_PATH", env_path)
    monkeypatch.setattr(cli, "ENV_EXAMPLE_PATH", example_path)

    result = runner.invoke(
        cli.app,
        ["init", "--non-interactive", "--default-riot-id", "invalid-riot-id"],
    )

    assert result.exit_code != 0
    assert "ゲーム名#タグライン" in result.output


def test_doctor_reports_missing_env(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(cli, "ENV_PATH", env_path)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "NG" in result.output
    assert "cp .env.example .env" in result.output
    assert "GOOGLE_API_KEY" in result.output
    assert "ffprobe" in result.output


def test_doctor_mentions_ffprobe_when_google_api_key_is_present(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("GOOGLE_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setattr(cli, "ENV_PATH", env_path)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(
        cli.shutil,
        "which",
        lambda tool: "/usr/bin/ffmpeg" if tool == "ffmpeg" else None,
    )

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "YouTube 字幕分析は使えます" in result.output
    assert "ffprobe" in result.output


def test_examples_prints_primary_commands() -> None:
    result = runner.invoke(cli.app, ["examples"])

    assert result.exit_code == 0
    assert "uv run lol-tools init" in result.output
    assert 'uv run lol-tools review "SummonerName#JP1"' in result.output
    assert "uv run lol-tools replay analyze" in result.output
    assert "uv run lol-tools export-match-data" in result.output
    assert "uv run lol-tools vod analyze" in result.output


def test_review_help_includes_quick_examples() -> None:
    result = runner.invoke(cli.app, ["review", "--help"])

    assert result.exit_code == 0
    assert 'uv run lol-tools review "SummonerName#JP1"' in result.output
    assert "uv run lol-tools doctor" in result.output


def test_vod_analyze_help_includes_quick_examples() -> None:
    result = runner.invoke(cli.app, ["vod", "analyze", "--help"])

    assert result.exit_code == 0
    assert "uv run lol-tools vod analyze" in result.output
    assert "uv run lol-tools examples" in result.output


def test_examples_use_portable_video_paths() -> None:
    result = runner.invoke(cli.app, ["examples"])

    assert result.exit_code == 0
    assert "path/to/replay.mp4" in result.output


def test_replay_analyze_selects_requested_match(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "replay.mov"
    video_path.write_text("dummy", encoding="utf-8")
    findings_path = tmp_path / "latest_findings.json"
    findings_path.write_text(
        json.dumps(
            {
                "matches": [
                    {"match_id": "match-1", "champion": "Ahri", "role": "MIDDLE", "queue_type": "RANKED_SOLO", "timestamp_ms": 1},
                    {"match_id": "match-2", "champion": "Viego", "role": "JUNGLE", "queue_type": "RANKED_SOLO", "timestamp_ms": 2},
                ],
                "player_stats": [
                    {"match_id": "match-1", "kill_timestamps": []},
                    {"match_id": "match-2", "kill_timestamps": [1000]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_resolve_default_riot_id", lambda riot_id: "Player#JP1")
    monkeypatch.setattr(cli, "_run_review_for_replay", lambda riot_id, review_count: findings_path)

    captured: dict[str, object] = {}

    def fake_run_vod(video_path: Path, match_data_path: Path, interval: int, no_open: bool) -> None:
        captured["video_path"] = video_path
        captured["interval"] = interval
        captured["no_open"] = no_open
        captured["match_data"] = json.loads(match_data_path.read_text(encoding="utf-8"))

    monkeypatch.setattr(cli, "_run_vod_gameplay_for_replay", fake_run_vod)

    result = runner.invoke(
        cli.app,
        [
            "replay",
            "analyze",
            str(video_path),
            "--review-count",
            "5",
            "--match-index",
            "1",
            "--interval",
            "7",
            "--no-open",
        ],
    )

    assert result.exit_code == 0
    assert captured["video_path"] == video_path
    assert captured["interval"] == 7
    assert captured["no_open"] is True
    assert captured["match_data"] == {
        "matches": [
            {"match_id": "match-2", "champion": "Viego", "role": "JUNGLE", "queue_type": "RANKED_SOLO", "timestamp_ms": 2},
        ],
        "player_stats": [
            {"match_id": "match-2", "kill_timestamps": [1000]},
        ],
    }


def test_replay_analyze_rejects_out_of_range_match_index(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "replay.mov"
    video_path.write_text("dummy", encoding="utf-8")
    findings_path = tmp_path / "latest_findings.json"
    findings_path.write_text(
        json.dumps(
            {
                "matches": [{"match_id": "match-1"}],
                "player_stats": [{"match_id": "match-1"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_resolve_default_riot_id", lambda riot_id: "Player#JP1")
    monkeypatch.setattr(cli, "_run_review_for_replay", lambda riot_id, review_count: findings_path)

    result = runner.invoke(
        cli.app,
        ["replay", "analyze", str(video_path), "--match-index", "2"],
    )

    assert result.exit_code == 1
    assert "match-index 2 は範囲外" in result.output


def test_export_match_data_selects_requested_match(tmp_path: Path) -> None:
    findings_path = tmp_path / "latest_findings.json"
    findings_path.write_text(
        json.dumps(
            {
                "matches": [
                    {"match_id": "match-1", "champion": "Ahri", "role": "MIDDLE", "queue_type": "RANKED_SOLO", "timestamp_ms": 1},
                    {"match_id": "match-2", "champion": "Viego", "role": "JUNGLE", "queue_type": "RANKED_SOLO", "timestamp_ms": 2},
                ],
                "player_stats": [
                    {"match_id": "match-1", "kill_timestamps": []},
                    {"match_id": "match-2", "kill_timestamps": [1000]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "match_data.json"

    result = runner.invoke(
        cli.app,
        [
            "export-match-data",
            "--input",
            str(findings_path),
            "--match-index",
            "1",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "matches": [
            {"match_id": "match-2", "champion": "Viego", "role": "JUNGLE", "queue_type": "RANKED_SOLO", "timestamp_ms": 2},
        ],
        "player_stats": [
            {"match_id": "match-2", "kill_timestamps": [1000]},
        ],
    }
