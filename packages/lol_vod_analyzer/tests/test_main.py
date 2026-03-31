from lol_vod_analyzer.main import _build_match_context


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
        }
        assert errors == []
