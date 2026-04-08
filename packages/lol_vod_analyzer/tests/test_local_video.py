import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lol_vod_analyzer.local_video import (
    _build_sampling_plan,
    _adaptive_timestamps,
    _compress_focus_windows,
    _build_focus_windows,
    _build_focused_sampling_report,
    _build_sampling_timestamps,
    _compute_scene_activity,
    extract_screenshots,
    get_video_metadata,
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


class TestBuildSamplingTimestamps:
    def test_limits_total_screenshots(self):
        timestamps = _build_sampling_timestamps(
            duration_sec=1800,
            interval_seconds=10,
            max_screenshots=12,
            adaptive=False,
        )

        assert len(timestamps) <= 12
        assert timestamps == sorted(timestamps)

    def test_reserves_early_game_samples(self):
        timestamps = _build_sampling_timestamps(
            duration_sec=1800,
            interval_seconds=10,
            max_screenshots=12,
            adaptive=False,
            game_start_offset=30,
        )

        assert timestamps[0] >= 30
        assert any(ts <= 210 for ts in timestamps)

    def test_uses_momentum_windows_when_match_context_exists(self):
        timestamps = _build_sampling_timestamps(
            duration_sec=1800,
            interval_seconds=10,
            max_screenshots=12,
            adaptive=False,
            match_context={
                "gold_diff_timeline": [0] * 5 + [2000] * 3 + [0] * 10,
            },
        )

        assert any(270 <= ts <= 450 for ts in timestamps)

    def test_focused_sampling_uses_focus_windows_and_backfill(self):
        timestamps = _build_sampling_timestamps(
            duration_sec=1800,
            interval_seconds=10,
            max_screenshots=12,
            adaptive=False,
            sampling_strategy="focused",
            match_context={
                "death_timestamps": [400],
                "objective_events": [{"timestamp": 900, "type": "ELITE_MONSTER_KILL"}],
                "level_ups": [{"timestamp": 600, "level": 6}],
                "gold_diff_timeline": [0] * 4 + [2000] * 3 + [0] * 20,
            },
            global_backfill=2,
        )

        assert len(timestamps) <= 12
        assert any(345 <= ts <= 445 for ts in timestamps)
        assert any(845 <= ts <= 945 for ts in timestamps)
        assert timestamps == sorted(timestamps)

    def test_speed_scales_focused_timestamps_to_video_time(self):
        timestamps = _build_sampling_timestamps(
            duration_sec=1200,
            interval_seconds=10,
            max_screenshots=8,
            adaptive=False,
            sampling_strategy="focused",
            speed=2.0,
            match_context={
                "death_timestamps": [400],
                "objective_events": [{"timestamp": 900, "type": "ELITE_MONSTER_KILL"}],
                "gold_diff_timeline": [0] * 4 + [2000] * 3 + [0] * 20,
            },
            global_backfill=2,
        )

        assert any(155 <= ts <= 245 for ts in timestamps)
        assert any(405 <= ts <= 495 for ts in timestamps)


class TestFocusedSampling:
    def test_build_focus_windows_includes_key_reasons(self):
        windows = _build_focus_windows(
            duration_sec=1800,
            match_context={
                "death_timestamps": [400],
                "kill_timestamps": [450],
                "assist_timestamps": [470],
                "objective_events": [{"timestamp": 900, "type": "ELITE_MONSTER_KILL"}],
                "level_ups": [{"timestamp": 600, "level": 6}],
                "gold_diff_timeline": [0] * 4 + [2000] * 3 + [0] * 20,
            },
            game_start_offset=0,
            focus_window_seconds=45,
        )

        reasons = {reason for window in windows for reason in window["reasons"]}
        assert "death" in reasons
        assert "objective" in reasons
        assert "momentum" in reasons
        assert "level_6" in reasons

    def test_lane_profile_adds_lane_focus_windows(self):
        windows = _build_focus_windows(
            duration_sec=1800,
            match_context={
                "death_timestamps": [400],
                "item_purchases": [{"timestamp": 210, "item_name": "Boots"}],
                "gold_diff_timeline": [0] * 4 + [2000] * 3 + [0] * 20,
            },
            game_start_offset=0,
            focus_window_seconds=45,
            focus_profile="lane",
        )

        reasons = {reason for window in windows for reason in window["reasons"]}
        assert "lane" in reasons
        assert "lane_reset" in reasons

    def test_roam_profile_adds_movement_windows(self):
        windows = _build_focus_windows(
            duration_sec=1800,
            match_context={
                "assist_timestamps": [600],
                "position_timeline": [
                    {"timestamp": 420, "x": 1200, "y": 1300},
                    {"timestamp": 540, "x": 7000, "y": 7600},
                ],
                "gold_diff_timeline": [0] * 30,
            },
            game_start_offset=0,
            focus_window_seconds=45,
            focus_profile="roam",
        )

        reasons = {reason for window in windows for reason in window["reasons"]}
        assert "roam" in reasons

    def test_compress_focus_windows_merges_nearby_objectives(self):
        windows = _compress_focus_windows([
            {
                "id": "objective_538",
                "reason": "objective",
                "reasons": ["objective"],
                "priority": 90,
                "start_sec": 493.0,
                "end_sec": 583.0,
                "source_events": [{"type": "ELITE_MONSTER_KILL", "timestamp_sec": 538}],
            },
            {
                "id": "objective_656",
                "reason": "objective",
                "reasons": ["objective"],
                "priority": 90,
                "start_sec": 611.0,
                "end_sec": 701.0,
                "source_events": [{"type": "ELITE_MONSTER_KILL", "timestamp_sec": 656}],
            },
            {
                "id": "objective_669",
                "reason": "objective",
                "reasons": ["objective"],
                "priority": 90,
                "start_sec": 624.0,
                "end_sec": 714.0,
                "source_events": [{"type": "ELITE_MONSTER_KILL", "timestamp_sec": 669}],
            },
            {
                "id": "objective_900",
                "reason": "objective",
                "reasons": ["objective"],
                "priority": 90,
                "start_sec": 855.0,
                "end_sec": 945.0,
                "source_events": [{"type": "ELITE_MONSTER_KILL", "timestamp_sec": 900}],
            },
        ])

        assert len(windows) == 2
        assert windows[0]["reason"] == "objective"
        assert windows[0]["start_sec"] == 493.0
        assert windows[0]["end_sec"] == 714.0
        assert len(windows[0]["source_events"]) == 3
        assert windows[1]["start_sec"] == 855.0

    def test_compress_focus_windows_caps_momentum_duration(self):
        windows = _compress_focus_windows([
            {
                "id": "momentum_0",
                "reason": "momentum",
                "reasons": ["momentum"],
                "priority": 80,
                "start_sec": 210.0,
                "end_sec": 690.0,
                "source_events": [{"type": "momentum", "start_sec": 210, "end_sec": 690}],
            },
        ])

        assert len(windows) == 1
        assert windows[0]["end_sec"] == 390.0
        assert windows[0]["source_events"][0]["original_end_sec"] == 690
        assert windows[0]["source_events"][0]["end_sec"] == 390

    def test_build_focused_sampling_report_respects_budget(self):
        windows = [
            {
                "id": "death_400",
                "reason": "death",
                "reasons": ["death"],
                "priority": 100,
                "start_sec": 355.0,
                "end_sec": 445.0,
                "source_events": [{"type": "death", "timestamp_sec": 400}],
            },
            {
                "id": "objective_900",
                "reason": "objective",
                "reasons": ["objective"],
                "priority": 90,
                "start_sec": 855.0,
                "end_sec": 945.0,
                "source_events": [{"type": "ELITE_MONSTER_KILL", "timestamp_sec": 900}],
            },
        ]
        report = _build_focused_sampling_report(
            duration_sec=1800,
            max_screenshots=8,
            windows=windows,
            focus_budget_ratio=0.75,
            global_backfill=2,
            game_start_offset=0,
        )

        assert report["strategy"] == "focused"
        assert len(report["focus_windows"]) == 2
        assert len(report["final_timestamps_sec"]) == 8
        assert report["backfill_budget"] >= 2
        assert report["backfill"]["allocated_count"] >= 2
        assert all(window["allocated_count"] >= 2 for window in report["focus_windows"])

    def test_focused_sampling_report_includes_profile(self):
        report = _build_focused_sampling_report(
            duration_sec=1800,
            max_screenshots=6,
            windows=[],
            focus_budget_ratio=0.75,
            global_backfill=2,
            game_start_offset=0,
            focus_profile="lane",
        )

        assert report["strategy"] == "focused"
        assert report["focus_profile"] == "lane"

    def test_lane_profile_increases_early_density_over_balanced(self):
        match_context = {
            "death_timestamps": [980],
            "assist_timestamps": [860],
            "objective_events": [
                {"timestamp": 900, "type": "ELITE_MONSTER_KILL"},
                {"timestamp": 1260, "type": "BUILDING_KILL"},
            ],
            "item_purchases": [{"timestamp": 240, "item_name": "Boots"}],
            "level_ups": [{"timestamp": 360, "level": 6}],
            "gold_diff_timeline": [0] * 10 + [2000] * 3 + [0] * 8 + [2500] * 4,
        }
        balanced = _build_sampling_plan(
            duration_sec=1800,
            interval_seconds=10,
            max_screenshots=12,
            adaptive=False,
            match_context=match_context,
            sampling_strategy="focused",
            focus_profile="balanced",
            global_backfill=2,
        )
        lane = _build_sampling_plan(
            duration_sec=1800,
            interval_seconds=10,
            max_screenshots=12,
            adaptive=False,
            match_context=match_context,
            sampling_strategy="focused",
            focus_profile="lane",
            global_backfill=2,
        )

        balanced_early = sum(ts <= 720 for ts in balanced["final_timestamps_sec"])
        lane_early = sum(ts <= 720 for ts in lane["final_timestamps_sec"])

        assert lane["focus_profile"] == "lane"
        assert any(window["reason"] == "lane" for window in lane["focus_windows"])
        assert lane_early > balanced_early

    def test_speed_scales_lane_windows_for_fast_replays(self):
        lane = _build_sampling_plan(
            duration_sec=1200,
            interval_seconds=10,
            max_screenshots=12,
            adaptive=False,
            match_context={
                "item_purchases": [{"timestamp": 240, "item_name": "Boots"}],
                "gold_diff_timeline": [0] * 20,
            },
            sampling_strategy="focused",
            focus_profile="lane",
            speed=2.0,
            global_backfill=2,
        )

        lane_windows = [w for w in lane["focus_windows"] if w["reason"] == "lane"]
        assert lane_windows
        assert lane_windows[0]["end_sec"] <= 120.0
