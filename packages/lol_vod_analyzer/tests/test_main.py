from unittest.mock import AsyncMock, patch

import pytest

from lol_vod_analyzer.main import _analyze_local, _build_match_context
from lol_vod_analyzer.models import VideoSource


class TestBuildMatchContext:
    def test_rejects_multiple_matches(self):
        match_context, errors = _build_match_context({
            "matches": [
                {"champion": "Elise", "role": "UTILITY"},
                {"champion": "Elise", "role": "JUNGLE"},
            ],
            "player_stats": [
                {"kill_timestamps": [10]},
                {"kill_timestamps": [20]},
            ],
        })

        assert match_context is None
        assert len(errors) == 1
        assert "1 試合だけ" in errors[0]
        assert "2 試合" in errors[0]
        assert "export-match-data" in errors[0]

    def test_returns_none_for_invalid_findings(self):
        match_context, errors = _build_match_context(["not", "a", "dict"])

        assert match_context is None
        assert errors == ["match-data の形式が不正です"]

    def test_returns_context_for_single_match(self):
        match_context, errors = _build_match_context({
            "matches": [{"champion": "Elise", "role": "JUNGLE"}],
            "player_stats": [{"kill_timestamps": [10]}],
        })

        assert match_context == {
            "champion": "Elise",
            "role": "JUNGLE",
            "kill_timestamps": [10],
            "death_timestamps": [],
            "assist_timestamps": [],
            "objective_events": [],
            "item_purchases": [],
            "skill_level_ups": [],
            "level_ups": [],
            "opponent_level_ups": [],
            "position_timeline": [],
            "jungle_cs_timeline": [],
            "gold_diff_timeline": [],
        }
        assert errors == []


class TestAnalyzeLocalDryRun:
    @pytest.mark.asyncio
    @patch("lol_vod_analyzer.main.required_local_video_tools", return_value=[])
    @patch("lol_vod_analyzer.main.missing_tools", return_value=[])
    @patch("lol_vod_analyzer.main.get_video_metadata")
    @patch("lol_vod_analyzer.main.plan_screenshot_sampling")
    @patch("lol_vod_analyzer.main.extract_screenshots")
    @patch("lol_vod_analyzer.main.analyze_video", new_callable=AsyncMock)
    async def test_dry_run_sampling_skips_extraction_and_analysis(
        self,
        mock_analyze_video,
        mock_extract_screenshots,
        mock_plan_screenshot_sampling,
        mock_get_video_metadata,
        _mock_missing_tools,
        _mock_required_local_video_tools,
        tmp_path,
    ):
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake")
        report_path = tmp_path / "sampling_report.json"

        mock_get_video_metadata.return_value = VideoSource(
            local_path=video_path,
            title="video",
            duration=600,
            source_type="local",
        )
        mock_plan_screenshot_sampling.return_value = {
            "strategy": "focused",
            "final_timestamps_sec": [30.0, 60.0],
            "focus_windows": [],
            "backfill": {"allocated_count": 2, "selected_timestamps_sec": [30.0, 60.0]},
        }

        await _analyze_local(
            video_path=video_path,
            mode="gameplay",
            open_browser=False,
            api_key="test-key",
            match_context={"champion": "Elise"},
            dry_run_sampling=True,
            dump_sampling_report=report_path,
            sampling_strategy="focused",
        )

        assert report_path.exists()
        mock_plan_screenshot_sampling.assert_called_once()
        mock_extract_screenshots.assert_not_called()
        mock_analyze_video.assert_not_awaited()
