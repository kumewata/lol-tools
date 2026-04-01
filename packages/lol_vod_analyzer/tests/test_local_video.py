import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lol_vod_analyzer.local_video import (
    _adaptive_timestamps,
    _compute_scene_activity,
    get_video_metadata,
    extract_audio,
    extract_screenshots,
)


class TestGetVideoMetadata:
    @patch("lol_vod_analyzer.local_video.subprocess.run")
    def test_get_metadata(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({
                "format": {"duration": "1234.56"}
            })
        )
        source = get_video_metadata(Path("/tmp/test.mp4"))
        assert source.title == "test"
        assert source.duration == 1234
        assert source.source_type == "local"
        assert source.local_path == Path("/tmp/test.mp4")

    @patch("lol_vod_analyzer.local_video.subprocess.run", side_effect=FileNotFoundError)
    def test_get_metadata_missing_ffprobe(self, mock_run):
        with pytest.raises(RuntimeError) as excinfo:
            get_video_metadata(Path("/tmp/test.mp4"))

        assert "ffprobe" in str(excinfo.value)
        mock_run.assert_called_once()


class TestExtractAudio:
    @patch("lol_vod_analyzer.local_video.subprocess.run")
    def test_extract_audio(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        audio_path = extract_audio(Path("/tmp/test.mp4"), tmp_path)
        assert audio_path == tmp_path / "test.m4a"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "ffmpeg"
        assert "-vn" in args

    @patch("lol_vod_analyzer.local_video.subprocess.run", side_effect=FileNotFoundError)
    def test_extract_audio_missing_ffmpeg(self, mock_run, tmp_path):
        with pytest.raises(RuntimeError) as excinfo:
            extract_audio(Path("/tmp/test.mp4"), tmp_path)

        assert "ffmpeg" in str(excinfo.value)
        mock_run.assert_called_once()


class TestExtractScreenshots:
    def test_extract_from_nonexistent_file(self, tmp_path):
        snapshots = extract_screenshots(
            Path("/nonexistent/video.mp4"), tmp_path / "out", interval_seconds=10
        )
        assert snapshots == []

    def test_extract_adaptive_from_nonexistent_file(self, tmp_path):
        snapshots = extract_screenshots(
            Path("/nonexistent/video.mp4"), tmp_path / "out", interval_seconds=10, adaptive=True
        )
        assert snapshots == []


class TestComputeSceneActivity:
    def test_returns_empty_for_nonexistent_file(self):
        profile = _compute_scene_activity(Path("/nonexistent/video.mp4"))
        assert profile == []


class TestAdaptiveTimestamps:
    def test_empty_profile(self):
        assert _adaptive_timestamps([], 10.0, 100) == []

    def test_high_activity_gets_denser_sampling(self):
        # Low activity at 0-50s, high activity at 50-100s
        profile = [(float(i), 0.01) for i in range(50)] + [
            (float(i), 0.9) for i in range(50, 100)
        ]
        timestamps = _adaptive_timestamps(profile, 10.0, 100)

        # Count samples in each half
        low_half = [t for t in timestamps if t < 50]
        high_half = [t for t in timestamps if t >= 50]

        # High activity region should have more samples
        assert len(high_half) > len(low_half)

    def test_max_frames_respected(self):
        profile = [(float(i), 0.5) for i in range(200)]
        timestamps = _adaptive_timestamps(profile, 5.0, 10)
        assert len(timestamps) <= 10

    def test_timestamps_sorted(self):
        profile = [(float(i), 0.1 * (i % 5)) for i in range(100)]
        timestamps = _adaptive_timestamps(profile, 5.0, 50)
        assert timestamps == sorted(timestamps)
