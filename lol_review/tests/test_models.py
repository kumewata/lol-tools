"""Tests for Pydantic data models."""

import pytest
from pydantic import ValidationError

from src.models import AnalysisResult, ChampionStats, MatchSummary, PlayerStats


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_match_data():
    return {
        "match_id": "KR_12345",
        "champion": "Jinx",
        "kills": 10,
        "deaths": 2,
        "assists": 5,
        "cs": 200,
        "gold_earned": 15000,
        "total_damage_dealt": 50000,
        "vision_score": 30,
        "win": True,
        "game_mode": "CLASSIC",
        "queue_type": "RANKED_SOLO_5x5",
        "game_duration_seconds": 1800,
        "timestamp_ms": 1700000000000,
    }


@pytest.fixture
def match_zero_deaths_data():
    return {
        "match_id": "KR_99999",
        "champion": "Ashe",
        "kills": 8,
        "deaths": 0,
        "assists": 10,
        "cs": 240,
        "gold_earned": 14000,
        "total_damage_dealt": 40000,
        "vision_score": 25,
        "win": False,
        "game_mode": "CLASSIC",
        "queue_type": "RANKED_SOLO_5x5",
        "game_duration_seconds": 2400,
        "timestamp_ms": 1700001000000,
    }


@pytest.fixture
def match_summary(base_match_data):
    return MatchSummary(**base_match_data)


@pytest.fixture
def match_zero_deaths(match_zero_deaths_data):
    return MatchSummary(**match_zero_deaths_data)


# ---------------------------------------------------------------------------
# MatchSummary tests
# ---------------------------------------------------------------------------

class TestMatchSummary:
    def test_basic_fields(self, match_summary):
        assert match_summary.match_id == "KR_12345"
        assert match_summary.champion == "Jinx"
        assert match_summary.kills == 10
        assert match_summary.deaths == 2
        assert match_summary.assists == 5
        assert match_summary.cs == 200
        assert match_summary.gold_earned == 15000
        assert match_summary.total_damage_dealt == 50000
        assert match_summary.vision_score == 30
        assert match_summary.win is True
        assert match_summary.game_mode == "CLASSIC"
        assert match_summary.queue_type == "RANKED_SOLO_5x5"
        assert match_summary.game_duration_seconds == 1800
        assert match_summary.timestamp_ms == 1700000000000

    def test_kda_with_deaths(self, match_summary):
        # (kills + assists) / deaths = (10 + 5) / 2 = 7.5
        assert match_summary.kda == pytest.approx(7.5)

    def test_kda_zero_deaths_is_inf(self, match_zero_deaths):
        assert match_zero_deaths.kda == float("inf")

    def test_cs_per_min(self, match_summary):
        # cs / (duration / 60) = 200 / (1800 / 60) = 200 / 30 = 6.666...
        assert match_summary.cs_per_min == pytest.approx(200 / 30)

    def test_cs_per_min_different_duration(self, match_zero_deaths):
        # 240 / (2400 / 60) = 240 / 40 = 6.0
        assert match_zero_deaths.cs_per_min == pytest.approx(6.0)

    def test_required_fields_missing(self):
        with pytest.raises(ValidationError):
            MatchSummary(match_id="KR_1")

    def test_negative_kills_rejected(self, base_match_data):
        base_match_data["kills"] = -1
        with pytest.raises(ValidationError):
            MatchSummary(**base_match_data)

    def test_negative_deaths_rejected(self, base_match_data):
        base_match_data["deaths"] = -1
        with pytest.raises(ValidationError):
            MatchSummary(**base_match_data)

    def test_zero_duration_rejected(self, base_match_data):
        base_match_data["game_duration_seconds"] = 0
        with pytest.raises(ValidationError):
            MatchSummary(**base_match_data)

    def test_negative_duration_rejected(self, base_match_data):
        base_match_data["game_duration_seconds"] = -100
        with pytest.raises(ValidationError):
            MatchSummary(**base_match_data)


# ---------------------------------------------------------------------------
# PlayerStats tests
# ---------------------------------------------------------------------------

class TestPlayerStats:
    def test_basic_fields(self):
        stats = PlayerStats(
            match_id="KR_12345",
            gold_timeline=[1000, 2000, 3000],
            gold_diff_timeline=[-100, 50, 200],
            kill_timestamps=[300000, 600000],
            death_timestamps=[150000],
            assist_timestamps=[800000, 900000],
            objective_events=[
                {"type": "DRAGON", "timestamp": 600000, "team": 100},
            ],
            item_purchases=[
                {"item_id": 1001, "timestamp": 120, "item_name": "ブーツ"},
            ],
        )
        assert stats.match_id == "KR_12345"
        assert stats.gold_timeline == [1000, 2000, 3000]
        assert stats.gold_diff_timeline == [-100, 50, 200]
        assert stats.kill_timestamps == [300000, 600000]
        assert stats.death_timestamps == [150000]
        assert stats.assist_timestamps == [800000, 900000]
        assert len(stats.objective_events) == 1
        assert stats.objective_events[0]["type"] == "DRAGON"
        assert len(stats.item_purchases) == 1
        assert stats.item_purchases[0]["item_name"] == "ブーツ"

    def test_empty_lists(self):
        stats = PlayerStats(
            match_id="KR_00000",
            gold_timeline=[],
            gold_diff_timeline=[],
            kill_timestamps=[],
            death_timestamps=[],
            assist_timestamps=[],
            objective_events=[],
            item_purchases=[],
        )
        assert stats.kill_timestamps == []
        assert stats.objective_events == []
        assert stats.item_purchases == []


# ---------------------------------------------------------------------------
# ChampionStats tests
# ---------------------------------------------------------------------------

class TestChampionStats:
    def test_basic_fields(self):
        cs = ChampionStats(
            champion="Jinx",
            games=10,
            wins=6,
            win_rate=0.6,
            avg_kda=5.0,
            avg_cs_per_min=7.0,
        )
        assert cs.champion == "Jinx"
        assert cs.games == 10
        assert cs.wins == 6
        assert cs.win_rate == pytest.approx(0.6)
        assert cs.avg_kda == pytest.approx(5.0)
        assert cs.avg_cs_per_min == pytest.approx(7.0)

    def test_from_matches_aggregation(self, base_match_data):
        match1 = MatchSummary(**base_match_data)  # Jinx, win
        jinx_loss_data = base_match_data.copy()
        jinx_loss_data.update({
            "match_id": "KR_22222",
            "kills": 4,
            "deaths": 6,
            "assists": 2,
            "cs": 180,
            "win": False,
            "game_duration_seconds": 2100,
        })
        match2 = MatchSummary(**jinx_loss_data)

        stats = ChampionStats.from_matches("Jinx", [match1, match2])

        assert stats.champion == "Jinx"
        assert stats.games == 2
        assert stats.wins == 1
        assert stats.win_rate == pytest.approx(0.5)
        expected_avg_kda = (match1.kda + match2.kda) / 2
        assert stats.avg_kda == pytest.approx(expected_avg_kda)
        expected_avg_cs = (match1.cs_per_min + match2.cs_per_min) / 2
        assert stats.avg_cs_per_min == pytest.approx(expected_avg_cs)

    def test_from_matches_single_game(self, match_summary):
        stats = ChampionStats.from_matches("Jinx", [match_summary])
        assert stats.games == 1
        assert stats.wins == 1
        assert stats.win_rate == pytest.approx(1.0)
        assert stats.avg_kda == pytest.approx(match_summary.kda)
        assert stats.avg_cs_per_min == pytest.approx(match_summary.cs_per_min)

    def test_from_matches_zero_deaths_kda(self, match_zero_deaths):
        stats = ChampionStats.from_matches("Ashe", [match_zero_deaths])
        assert stats.avg_kda == float("inf")

    def test_from_matches_filters_by_champion(self, base_match_data, match_zero_deaths_data):
        """Mixed-champion list: only matching champion's matches are aggregated."""
        jinx = MatchSummary(**base_match_data)   # champion=Jinx
        ashe = MatchSummary(**match_zero_deaths_data)  # champion=Ashe

        stats = ChampionStats.from_matches("Jinx", [jinx, ashe])
        assert stats.games == 1
        assert stats.wins == 1

    def test_from_matches_empty_list(self):
        stats = ChampionStats.from_matches("Jinx", [])
        assert stats.games == 0
        assert stats.wins == 0
        assert stats.win_rate == pytest.approx(0.0)
        assert stats.avg_kda == pytest.approx(0.0)
        assert stats.avg_cs_per_min == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# AnalysisResult tests
# ---------------------------------------------------------------------------

class TestAnalysisResult:
    @pytest.fixture
    def sample_analysis(self, match_summary, match_zero_deaths):
        champion_stats = [
            ChampionStats.from_matches("Jinx", [match_summary]),
            ChampionStats.from_matches("Ashe", [match_zero_deaths]),
        ]
        player_stats = [
            PlayerStats(
                match_id="KR_12345",
                gold_timeline=[1000, 2000],
                gold_diff_timeline=[0, 100],
                kill_timestamps=[],
                death_timestamps=[],
                assist_timestamps=[],
                objective_events=[],
                item_purchases=[],
            )
        ]
        return AnalysisResult(
            summoner_name="TestPlayer",
            tag_line="KR1",
            total_games=2,
            wins=1,
            losses=1,
            win_rate=0.5,
            avg_kda=5.0,
            avg_cs_per_min=6.5,
            matches=[match_summary, match_zero_deaths],
            champion_stats=champion_stats,
            player_stats=player_stats,
        )

    def test_basic_fields(self, sample_analysis):
        assert sample_analysis.summoner_name == "TestPlayer"
        assert sample_analysis.tag_line == "KR1"
        assert sample_analysis.total_games == 2
        assert sample_analysis.wins == 1
        assert sample_analysis.losses == 1
        assert sample_analysis.win_rate == pytest.approx(0.5)
        assert sample_analysis.avg_kda == pytest.approx(5.0)
        assert sample_analysis.avg_cs_per_min == pytest.approx(6.5)

    def test_matches_list(self, sample_analysis):
        assert len(sample_analysis.matches) == 2
        assert sample_analysis.matches[0].match_id == "KR_12345"

    def test_champion_stats_list(self, sample_analysis):
        assert len(sample_analysis.champion_stats) == 2
        champions = [c.champion for c in sample_analysis.champion_stats]
        assert "Jinx" in champions
        assert "Ashe" in champions

    def test_player_stats_list(self, sample_analysis):
        assert len(sample_analysis.player_stats) == 1
        assert sample_analysis.player_stats[0].match_id == "KR_12345"

    def test_required_fields_missing(self):
        with pytest.raises(ValidationError):
            AnalysisResult(summoner_name="X")
