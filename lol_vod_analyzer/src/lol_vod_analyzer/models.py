# src/lol_vod_analyzer/models.py
"""Pydantic data models for LoL VOD analysis."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class VideoSource(BaseModel):
    """Video source metadata."""

    url: str | None = None
    local_path: Path | None = None
    title: str
    duration: int = Field(gt=0, description="Duration in seconds")
    source_type: Literal["youtube", "local", "twitch"]

    @property
    def video_id(self) -> str | None:
        """Extract YouTube video ID from URL."""
        if self.url is None:
            return None
        match = re.search(r"[?&]v=([^&]+)", self.url)
        return match.group(1) if match else None

    def timestamp_url(self, timestamp_ms: int) -> str | None:
        """Return a YouTube URL with timestamp parameter, or None for local."""
        if self.source_type != "youtube" or self.url is None:
            return None
        vid = self.video_id
        if vid is None:
            return None
        seconds = timestamp_ms // 1000
        return f"https://www.youtube.com/watch?v={vid}&t={seconds}s"


class TranscriptSegment(BaseModel):
    """A single subtitle segment with timestamps."""

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str


class SceneSnapshot(BaseModel):
    """A screenshot or storyboard frame at a specific timestamp."""

    timestamp_ms: int = Field(ge=0)
    image_path: Path
    description: str | None = None


class KeyMoment(BaseModel):
    """An important moment identified in the video."""

    timestamp_ms: int = Field(ge=0)
    label: str
    analysis: str


class Topic(BaseModel):
    """A topic or theme extracted from the video."""

    name: str
    content: str
    timestamps: list[int] = Field(default_factory=list)


class ChunkAnalysis(BaseModel):
    """Analysis result for a single time chunk."""

    chunk_index: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    summary: str
    key_moments: list[KeyMoment] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Complete analysis result for a video."""

    source: VideoSource
    mode: Literal["commentary", "gameplay"]
    summary: str
    key_moments: list[KeyMoment] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)
    actionable_tips: list[str] = Field(default_factory=list)
    snapshots: list[SceneSnapshot] = Field(default_factory=list)
