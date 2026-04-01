"""Tests for RiotClient."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lol_review.riot_client import RiotClient
from lol_review.models import MatchSummary, PlayerStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client() -> RiotClient:
    return RiotClient(api_key="test-api-key")


def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


def _make_mock_response(json_data, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    mock.headers = {}
    return mock


# ---------------------------------------------------------------------------
# _request: rate limiting and 429 retry
# ---------------------------------------------------------------------------

class TestRequest:
    def test_429_retry_once(self):
        """_request should sleep on 429 and retry once."""
        client = make_client()

        first = _make_mock_response({}, 429)
        first.headers = {"Retry-After": "0"}
        second = _make_mock_response({"ok": True}, 200)

        async def run():
            with patch.object(
                client._client, "request",
                new=AsyncMock(side_effect=[first, second])
            ):
                return await client._request("GET", "https://example.com")

        response = _run(run())
        assert response.status_code == 200

    def test_non_429_error_propagates(self):
        """Non-429 errors should be raised via raise_for_status."""
        client = make_client()

        mock_resp = _make_mock_response({}, 404)
        mock_resp.raise_for_status.side_effect = Exception("404 Not Found")

        async def run():
            with patch.object(
                client._client, "request",
                new=AsyncMock(return_value=mock_resp)
            ):
                return await client._request("GET", "https://example.com")

        with pytest.raises(Exception, match="404"):
            _run(run())


# ---------------------------------------------------------------------------
# get_puuid
# ---------------------------------------------------------------------------

class TestGetPuuid:
    def test_get_puuid_returns_puuid(self):
        """get_puuid should return the puuid field from the API response."""
        client = make_client()
        mock_resp = _make_mock_response({
            "puuid": "test-puuid-abc123",
            "gameName": "TestPlayer",
            "tagLine": "KR1",
        })

        async def run():
            with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)):
                return await client.get_puuid("TestPlayer", "KR1")

        puuid = _run(run())
        assert puuid == "test-puuid-abc123"

    def test_get_puuid_calls_correct_url(self):
        """get_puuid should call the correct Riot account API URL."""
        client = make_client()
        mock_resp = _make_mock_response({"puuid": "abc"})
        mock_request = AsyncMock(return_value=mock_resp)

        async def run():
            with patch.object(client, "_request", new=mock_request):
                return await client.get_puuid("PlayerName", "TAG")

        _run(run())
        call_url = mock_request.call_args[0][1]
        assert "PlayerName" in call_url
        assert "TAG" in call_url
        assert "accounts/by-riot-id" in call_url

    def test_get_puuid_url_encodes_special_chars(self):
        """get_puuid should percent-encode game_name and tag_line."""
        client = make_client()
        mock_resp = _make_mock_response({"puuid": "abc"})
        mock_request = AsyncMock(return_value=mock_resp)

        async def run():
            with patch.object(client, "_request", new=mock_request):
                return await client.get_puuid("Player Name", "KR 1")

        _run(run())
        call_url = mock_request.call_args[0][1]
        assert "Player%20Name" in call_url
        assert "KR%201" in call_url


# ---------------------------------------------------------------------------
# get_match_ids
# ---------------------------------------------------------------------------

class TestGetMatchIds:
    def test_get_match_ids_returns_list(self):
        """get_match_ids should return a list of match ID strings."""
        client = make_client()
        match_ids = ["KR_1111", "KR_2222", "KR_3333"]
        mock_resp = _make_mock_response(match_ids)

        async def run():
            with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)):
                return await client.get_match_ids("some-puuid")

        result = _run(run())
        assert result == match_ids
        assert isinstance(result, list)
        assert all(isinstance(m, str) for m in result)

    def test_get_match_ids_default_count(self):
        """get_match_ids should pass count=20 by default."""
        client = make_client()
        mock_resp = _make_mock_response([])
        mock_request = AsyncMock(return_value=mock_resp)

        async def run():
            with patch.object(client, "_request", new=mock_request):
                return await client.get_match_ids("some-puuid")

        _run(run())
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["params"]["count"] == 20

    def test_get_match_ids_with_queue_type(self):
        """get_match_ids should pass queue parameter when queue_type is provided."""
        client = make_client()
        mock_resp = _make_mock_response([])
        mock_request = AsyncMock(return_value=mock_resp)

        async def run():
            with patch.object(client, "_request", new=mock_request):
                return await client.get_match_ids("some-puuid", count=10, queue_type=420)

        _run(run())
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["params"]["count"] == 10
        assert call_kwargs["params"]["queue"] == 420

    def test_get_match_ids_no_queue_when_none(self):
        """get_match_ids should not include 'queue' param when queue_type is None."""
        client = make_client()
        mock_resp = _make_mock_response([])
        mock_request = AsyncMock(return_value=mock_resp)

        async def run():
            with patch.object(client, "_request", new=mock_request):
                return await client.get_match_ids("some-puuid")

        _run(run())
        call_kwargs = mock_request.call_args[1]
        assert "queue" not in call_kwargs["params"]


# ---------------------------------------------------------------------------
# parse_match_summary
# ---------------------------------------------------------------------------

class TestParseMatchSummary:
    def _make_match_data(self) -> dict:
        return {
            "metadata": {"matchId": "KR_99999"},
            "info": {
                "queueId": 420,
                "gameMode": "CLASSIC",
                "gameDuration": 1800,
                "gameCreation": 1700000000000,
                "participants": [
                    {
                        "puuid": "target-puuid",
                        "championName": "Jinx",
                        "kills": 8,
                        "deaths": 3,
                        "assists": 5,
                        "totalMinionsKilled": 150,
                        "neutralMinionsKilled": 20,
                        "goldEarned": 14000,
                        "totalDamageDealtToChampions": 40000,
                        "physicalDamageDealtToChampions": 30000,
                        "magicDamageDealtToChampions": 5000,
                        "trueDamageDealtToChampions": 5000,
                        "visionScore": 25,
                        "win": True,
                        "teamId": 100,
                        "teamPosition": "BOTTOM",
                    },
                    {
                        "puuid": "other-puuid",
                        "championName": "Ahri",
                        "kills": 5,
                        "deaths": 5,
                        "assists": 5,
                        "totalMinionsKilled": 120,
                        "neutralMinionsKilled": 10,
                        "goldEarned": 12000,
                        "totalDamageDealtToChampions": 30000,
                        "physicalDamageDealtToChampions": 5000,
                        "magicDamageDealtToChampions": 22000,
                        "trueDamageDealtToChampions": 3000,
                        "visionScore": 20,
                        "win": True,
                        "teamId": 100,
                        "teamPosition": "MIDDLE",
                    },
                    {
                        "puuid": "enemy-bot",
                        "championName": "Caitlyn",
                        "kills": 3,
                        "deaths": 4,
                        "assists": 2,
                        "totalMinionsKilled": 130,
                        "neutralMinionsKilled": 5,
                        "goldEarned": 11000,
                        "totalDamageDealtToChampions": 25000,
                        "visionScore": 15,
                        "win": False,
                        "teamId": 200,
                        "teamPosition": "BOTTOM",
                    },
                    {
                        "puuid": "enemy-sup",
                        "championName": "Lulu",
                        "kills": 1,
                        "deaths": 3,
                        "assists": 6,
                        "totalMinionsKilled": 20,
                        "neutralMinionsKilled": 0,
                        "goldEarned": 7000,
                        "totalDamageDealtToChampions": 8000,
                        "visionScore": 40,
                        "win": False,
                        "teamId": 200,
                        "teamPosition": "UTILITY",
                    },
                ],
            },
        }

    def test_parse_match_summary_returns_match_summary(self):
        client = make_client()
        data = self._make_match_data()
        result = client.parse_match_summary(data, "target-puuid")
        assert isinstance(result, MatchSummary)

    def test_parse_match_summary_fields(self):
        client = make_client()
        data = self._make_match_data()
        result = client.parse_match_summary(data, "target-puuid")
        assert result.match_id == "KR_99999"
        assert result.champion == "Jinx"
        assert result.kills == 8
        assert result.deaths == 3
        assert result.assists == 5
        assert result.cs == 170  # 150 + 20
        assert result.gold_earned == 14000
        assert result.total_damage_dealt == 40000
        assert result.vision_score == 25
        assert result.win is True
        assert result.game_mode == "CLASSIC"
        # Kill participation: (8+5) / (8+5) team kills = 13/13 = 1.0
        assert result.kill_participation == 13 / 13
        assert result.damage_physical == 30000
        assert result.damage_magical == 5000
        assert result.damage_true == 5000
        assert result.queue_type == "420"
        assert result.game_duration_seconds == 1800
        assert result.timestamp_ms == 1700000000000

    def test_parse_match_summary_selects_correct_participant(self):
        """Should use other-puuid's data when requested."""
        client = make_client()
        data = self._make_match_data()
        result = client.parse_match_summary(data, "other-puuid")
        assert result.champion == "Ahri"
        assert result.kills == 5

    def test_parse_match_summary_missing_participant_raises(self):
        """Should raise ValueError with a helpful message when puuid not found."""
        client = make_client()
        data = self._make_match_data()
        with pytest.raises(ValueError, match="unknown-puuid"):
            client.parse_match_summary(data, "unknown-puuid")


# ---------------------------------------------------------------------------
# parse_timeline
# ---------------------------------------------------------------------------

class TestParseTimeline:
    def _make_timeline_data(self) -> dict:
        return {
            "metadata": {"matchId": "KR_99999"},
            "info": {
                "frames": [
                    {
                        "timestamp": 0,
                        "participantFrames": {
                            "1": {
                                "participantId": 1,
                                "totalGold": 500,
                                "position": {"x": 500, "y": 600},
                                "jungleMinionsKilled": 0,
                            },
                            "2": {"participantId": 2, "totalGold": 500},
                        },
                        "events": [],
                    },
                    {
                        "timestamp": 60000,
                        "participantFrames": {
                            "1": {
                                "participantId": 1,
                                "totalGold": 1500,
                                "position": {"x": 2000, "y": 2500},
                                "jungleMinionsKilled": 8,
                            },
                            "2": {"participantId": 2, "totalGold": 1200},
                        },
                        "events": [
                            {
                                "type": "CHAMPION_KILL",
                                "timestamp": 45000,
                                "killerId": 1,
                                "victimId": 2,
                                "assistingParticipantIds": [],
                            },
                        ],
                    },
                    {
                        "timestamp": 120000,
                        "participantFrames": {
                            "1": {
                                "participantId": 1,
                                "totalGold": 3000,
                                "position": {"x": 9800, "y": 4400},
                                "jungleMinionsKilled": 16,
                            },
                            "2": {"participantId": 2, "totalGold": 2500},
                        },
                        "events": [
                            {
                                "type": "ELITE_MONSTER_KILL",
                                "timestamp": 100000,
                                "killerId": 1,
                                "monsterType": "DRAGON",
                            },
                            {
                                "type": "CHAMPION_KILL",
                                "timestamp": 110000,
                                "killerId": 2,
                                "victimId": 1,
                                "assistingParticipantIds": [],
                            },
                            {
                                "type": "CHAMPION_KILL",
                                "timestamp": 115000,
                                "killerId": 3,
                                "victimId": 4,
                                "assistingParticipantIds": [1, 5],
                            },
                            {
                                "type": "ITEM_PURCHASED",
                                "timestamp": 105000,
                                "participantId": 1,
                                "itemId": 1001,
                            },
                            {
                                "type": "ITEM_PURCHASED",
                                "timestamp": 106000,
                                "participantId": 2,
                                "itemId": 3006,
                            },
                        ],
                    },
                ]
            },
        }

    def test_parse_timeline_returns_player_stats(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        assert isinstance(result, PlayerStats)

    def test_parse_timeline_match_id(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        assert result.match_id == "KR_99999"

    def test_parse_timeline_gold_timeline(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        assert result.gold_timeline == [500, 1500, 3000]

    def test_parse_timeline_kill_timestamps(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        # Participant 1 killed at timestamp 45000ms → 45s
        assert 45 in result.kill_timestamps

    def test_parse_timeline_death_timestamps(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        # Participant 1 died at timestamp 110000ms → 110s
        assert 110 in result.death_timestamps

    def test_parse_timeline_assist_timestamps(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        # Participant 1 assisted at 115000ms → 115s
        assert 115 in result.assist_timestamps

    def test_parse_timeline_objective_events(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        assert len(result.objective_events) >= 1
        types = [e.get("type") for e in result.objective_events]
        assert "ELITE_MONSTER_KILL" in types
        assert result.objective_events[0]["timestamp"] == 100

    def test_parse_timeline_position_timeline(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        assert result.position_timeline == [
            {"timestamp": 0, "x": 500, "y": 600},
            {"timestamp": 60, "x": 2000, "y": 2500},
            {"timestamp": 120, "x": 9800, "y": 4400},
        ]

    def test_parse_timeline_jungle_cs_timeline(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        assert result.jungle_cs_timeline == [
            {"timestamp": 0, "jungle_cs": 0},
            {"timestamp": 60, "jungle_cs": 8},
            {"timestamp": 120, "jungle_cs": 16},
        ]

    def test_parse_timeline_gold_diff_computed_from_team_totals(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        # Test data has pid 1 and 2 (both team 1), no team 2 participants.
        # So my_team gold = pid1 + pid2, enemy_gold = 0 for each frame.
        assert result.gold_diff_timeline == [1000, 2700, 5500]
        assert len(result.gold_diff_timeline) == len(result.gold_timeline)

    def test_parse_timeline_item_purchases(self):
        client = make_client()
        data = self._make_timeline_data()
        item_data = {
            1001: {"name": "ブーツ", "type": "component"},
            3006: {"name": "バーサーカー ブーツ", "type": "completed"},
        }
        result = client.parse_timeline(
            data, "KR_99999", "target-puuid", 1, item_data=item_data
        )
        # Only participant 1's purchase (itemId 1001) should be included
        assert len(result.item_purchases) == 1
        assert result.item_purchases[0]["item_id"] == 1001
        assert result.item_purchases[0]["item_name"] == "ブーツ"
        assert result.item_purchases[0]["item_type"] == "component"
        assert result.item_purchases[0]["item_type_label"] == "素材"
        assert result.item_purchases[0]["timestamp"] == 105

    def test_parse_timeline_item_purchases_no_data(self):
        client = make_client()
        data = self._make_timeline_data()
        result = client.parse_timeline(data, "KR_99999", "target-puuid", 1)
        assert len(result.item_purchases) == 1
        assert result.item_purchases[0]["item_name"] == "Item 1001"
        assert result.item_purchases[0]["item_type_label"] == "素材"

    def test_parse_timeline_core_numbering(self):
        """Completed items should be numbered as コア（N個目）."""
        client = make_client()
        # Build timeline with 2 completed item purchases by participant 1
        data = {
            "metadata": {"matchId": "KR_11111"},
            "info": {
                "frames": [
                    {
                        "timestamp": 0,
                        "participantFrames": {"1": {"participantId": 1, "totalGold": 500}},
                        "events": [
                            {"type": "ITEM_PURCHASED", "timestamp": 600000, "participantId": 1, "itemId": 3031},
                            {"type": "ITEM_PURCHASED", "timestamp": 900000, "participantId": 1, "itemId": 3094},
                        ],
                    }
                ]
            },
        }
        item_data = {
            3031: {"name": "インフィニティ エッジ", "type": "completed"},
            3094: {"name": "ストームレイザー", "type": "completed"},
        }
        result = client.parse_timeline(data, "KR_11111", "p", 1, item_data=item_data)
        assert result.item_purchases[0]["item_type_label"] == "コア（1個目）"
        assert result.item_purchases[1]["item_type_label"] == "コア（2個目）"
