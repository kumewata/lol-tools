"""Helpers for cross-platform system tool detection and guidance."""

from __future__ import annotations

import platform
import shutil


def current_platform_family() -> str:
    """Return a normalized platform family name."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    return "other"


def required_local_video_tools(mode: str | None) -> list[str]:
    """Return required external tools for local video analysis."""
    if mode == "gameplay":
        return ["ffprobe"]
    return ["ffprobe", "ffmpeg"]


def missing_tools(tools: list[str]) -> list[str]:
    """Return missing command names from the given tool list."""
    return [tool for tool in tools if shutil.which(tool) is None]


def install_hint(tool: str) -> str:
    """Return a platform-aware install hint for a missing tool."""
    family = current_platform_family()

    if tool in {"ffmpeg", "ffprobe"}:
        if family == "windows":
            return (
                "Windows: `winget install Gyan.FFmpeg` または "
                "`choco install ffmpeg`。通常は ffprobe も同梱されます。"
            )
        if family == "macos":
            return "macOS: `brew install ffmpeg`。通常は ffprobe も同梱されます。"
        if family == "linux":
            return "Linux: ディストリビューションのパッケージマネージャで `ffmpeg` を導入してください。"

    return f"{tool} をインストールして PATH から実行できる状態にしてください。"


def format_missing_tools_message(tools: list[str], context: str) -> str:
    """Format a user-facing message for missing external tools."""
    lines = [f"{context} に必要な外部ツールが不足しています: {', '.join(tools)}"]
    for tool in tools:
        lines.append(f"- {tool}: {install_hint(tool)}")
    lines.append("導入後に `uv run lol-tools doctor` で再確認してください。")
    return "\n".join(lines)
