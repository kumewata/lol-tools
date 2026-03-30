from __future__ import annotations

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


def test_examples_prints_primary_commands() -> None:
    result = runner.invoke(cli.app, ["examples"])

    assert result.exit_code == 0
    assert "uv run lol-tools init" in result.output
    assert 'uv run lol-tools review "SummonerName#JP1"' in result.output
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
