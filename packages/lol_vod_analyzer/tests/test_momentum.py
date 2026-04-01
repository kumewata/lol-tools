"""Tests for momentum impact compression."""

from lol_vod_analyzer.momentum import (
    compress_match_context,
    compute_momentum,
    compute_win_probability,
    filter_important_timestamps,
)


class TestComputeWinProbability:
    def test_zero_diff_gives_fifty_percent(self):
        probs = compute_win_probability([0, 0, 0])
        assert all(abs(p - 0.5) < 1e-9 for p in probs)

    def test_positive_diff_above_fifty(self):
        probs = compute_win_probability([1000])
        assert probs[0] > 0.5

    def test_negative_diff_below_fifty(self):
        probs = compute_win_probability([-1000])
        assert probs[0] < 0.5

    def test_symmetric(self):
        probs = compute_win_probability([2000, -2000])
        assert abs(probs[0] + probs[1] - 1.0) < 1e-9

    def test_empty_input(self):
        assert compute_win_probability([]) == []

    def test_extreme_diff_clamps_near_one(self):
        probs = compute_win_probability([10000])
        assert probs[0] > 0.99


class TestComputeMomentum:
    def test_constant_probs_zero_momentum(self):
        probs = [0.5, 0.5, 0.5, 0.5]
        momentum = compute_momentum(probs)
        assert all(abs(m) < 1e-9 for m in momentum)

    def test_single_spike(self):
        probs = [0.5, 0.5, 0.8, 0.8, 0.8]
        momentum = compute_momentum(probs)
        # momentum should peak around index 2 (the jump)
        assert momentum[2] > momentum[0]
        # index 4 has no new change, so its smoothed momentum should be <= index 2
        assert momentum[2] >= momentum[4]

    def test_empty_input(self):
        assert compute_momentum([]) == []

    def test_single_element(self):
        assert compute_momentum([0.5]) == [0.0]

    def test_two_elements(self):
        momentum = compute_momentum([0.5, 0.7])
        assert len(momentum) == 2
        assert momentum[0] == 0.0
        # window=3 but only 2 elements: mean of [0.0, 0.2] = 0.1
        assert abs(momentum[1] - 0.1) < 1e-9


class TestFilterImportantTimestamps:
    def test_returns_high_momentum_indices(self):
        momentum = [0.0, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0]
        important = filter_important_timestamps(momentum, threshold_percentile=75.0)
        # index 3 and its neighbours (2, 4) should be included
        assert 3 in important
        assert 2 in important
        assert 4 in important

    def test_all_zeros_keeps_everything(self):
        momentum = [0.0, 0.0, 0.0, 0.0]
        important = filter_important_timestamps(momentum, threshold_percentile=75.0)
        assert important == {0, 1, 2, 3}

    def test_empty_input(self):
        assert filter_important_timestamps([]) == set()


class TestCompressMatchContext:
    def _make_context(self):
        """Build a realistic match_context with gold_diff_timeline."""
        # Simulate a 30-min game with 1-min frames (30 entries).
        # Flat early, spike at frame 15 (= 900 sec), flat late.
        gold_diff = [0] * 10 + [500] * 5 + [3000] * 5 + [3000] * 10
        return {
            "champion": "Jinx",
            "role": "BOTTOM",
            "gold_diff_timeline": gold_diff,
            "kill_timestamps": [120, 300, 600, 900, 1200, 1500],
            "death_timestamps": [180, 910],
            "assist_timestamps": [305, 605, 905],
            "objective_events": [
                {"timestamp": 600, "type": "ELITE_MONSTER_KILL"},
                {"timestamp": 900, "type": "ELITE_MONSTER_KILL"},
                {"timestamp": 1800, "type": "BUILDING_KILL"},
            ],
            "item_purchases": [
                {"timestamp": 300, "item_name": "Doran's Blade"},
                {"timestamp": 900, "item_name": "Infinity Edge"},
            ],
            "skill_level_ups": [
                {"timestamp": 120, "skill": "Q"},
                {"timestamp": 900, "skill": "R"},
            ],
            "level_ups": [
                {"timestamp": 120, "level": 2},
                {"timestamp": 900, "level": 6},
            ],
            "opponent_level_ups": [
                {"timestamp": 125, "level": 2},
                {"timestamp": 905, "level": 6},
            ],
            "position_timeline": [
                {"timestamp": 60, "x": 100, "y": 200},
                {"timestamp": 900, "x": 500, "y": 600},
            ],
            "jungle_cs_timeline": [
                {"timestamp": 60, "jungle_cs": 0},
                {"timestamp": 900, "jungle_cs": 10},
            ],
        }

    def test_compression_reduces_events(self):
        ctx = self._make_context()
        original_count = sum(
            len(ctx[k])
            for k in (
                "kill_timestamps",
                "death_timestamps",
                "assist_timestamps",
                "objective_events",
                "item_purchases",
                "skill_level_ups",
                "level_ups",
                "opponent_level_ups",
                "position_timeline",
                "jungle_cs_timeline",
            )
        )

        compressed = compress_match_context(ctx)

        compressed_count = sum(
            len(compressed[k])
            for k in (
                "kill_timestamps",
                "death_timestamps",
                "assist_timestamps",
                "objective_events",
                "item_purchases",
                "skill_level_ups",
                "level_ups",
                "opponent_level_ups",
                "position_timeline",
                "jungle_cs_timeline",
            )
        )

        assert compressed_count < original_count

    def test_preserves_non_event_fields(self):
        ctx = self._make_context()
        compressed = compress_match_context(ctx)
        assert compressed["champion"] == "Jinx"
        assert compressed["role"] == "BOTTOM"

    def test_fallback_when_no_gold_diff(self):
        ctx = {"champion": "Jinx", "kill_timestamps": [100, 200]}
        result = compress_match_context(ctx)
        assert result is ctx  # same object, unmodified

    def test_fallback_when_empty_gold_diff(self):
        ctx = {"champion": "Jinx", "gold_diff_timeline": [], "kill_timestamps": [100]}
        result = compress_match_context(ctx)
        assert result is ctx
