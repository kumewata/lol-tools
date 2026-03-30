import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lol_vod_analyzer.fetcher import (
    fetch_video_metadata,
    parse_caption_events,
    fetch_transcript,
    find_storyboard_format,
    download_storyboard_sprites,
)
from lol_vod_analyzer.models import TranscriptSegment, VideoSource


class TestParseCaption:
    def test_parse_caption_events(self, sample_caption_json3):
        segments = parse_caption_events(sample_caption_json3)
        assert len(segments) == 2
        assert segments[0].text == "こんにちは。"
        assert segments[0].start_ms == 1500
        assert segments[0].end_ms == 5500
        assert segments[1].text == "エリスの解説です。"

    def test_parse_empty_events(self):
        segments = parse_caption_events({"events": []})
        assert segments == []


class TestFindStoryboard:
    def test_find_best_storyboard(self, sample_yt_info):
        sb = find_storyboard_format(sample_yt_info["formats"])
        assert sb is not None
        assert sb["format_id"] == "sb0"

    def test_no_storyboard(self):
        formats = [{"format_id": "18", "ext": "mp4"}]
        sb = find_storyboard_format(formats)
        assert sb is None


class TestFetchVideoMetadata:
    @patch("lol_vod_analyzer.fetcher.yt_dlp.YoutubeDL")
    def test_fetch_metadata(self, mock_ydl_class, sample_yt_info):
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.extract_info.return_value = sample_yt_info
        mock_ydl_class.return_value = mock_instance

        url = "https://www.youtube.com/watch?v=SMsQCnKDzVw"
        source, info = fetch_video_metadata(url)
        assert source.title == "【LoL】エリス完全解説"
        assert source.duration == 2191
        assert source.source_type == "youtube"
