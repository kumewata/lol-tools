import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lol_vod_analyzer.local_video import (
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


class TestExtractScreenshots:
    def test_extract_from_nonexistent_file(self, tmp_path):
        snapshots = extract_screenshots(
            Path("/nonexistent/video.mp4"), tmp_path / "out", interval_seconds=10
        )
        assert snapshots == []
