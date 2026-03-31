"""Riot API client using httpx."""

from __future__ import annotations

import asyncio
from urllib.parse import quote
from typing import Optional

import httpx

from lol_review.models import MatchSummary, PlayerStats

CONTROL_WARD_IDS = {2055, 2056, 2139}  # Control Ward and variants


def _classify_item(info: dict, item_id: int = 0) -> str:
    """Classify an item based on Data Dragon metadata."""
    tags = info.get("tags", [])
    name = info.get("name", "")
    if "Trinket" in tags or item_id in CONTROL_WARD_IDS or "ワード" in name:
        return "ward"
    if info.get("consumed"):
        return "consumable"
    has_from = "from" in info
    has_into = "into" in info
    if "Boots" in tags and has_from:
        return "boots"
    if has_from and not has_into:
        return "completed"
    if has_from and has_into:
        return "component"
    if not has_from and has_into:
        return "component"
    return "component"


ACCOUNT_BASE = "https://asia.api.riotgames.com"
MATCH_BASE = "https://asia.api.riotgames.com"

REQUEST_INTERVAL = 0.06  # seconds between requests


class RiotClient:
    """Async client for Riot Games API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"X-Riot-Token": api_key},
        )
        self._last_request_time: float = 0.0

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make a rate-limited request, retrying once on 429."""
        loop = asyncio.get_running_loop()
        now = loop.time()
        elapsed = now - self._last_request_time
        if elapsed < REQUEST_INTERVAL:
            await asyncio.sleep(REQUEST_INTERVAL - elapsed)

        response = await self._client.request(method, url, **kwargs)
        self._last_request_time = asyncio.get_running_loop().time()

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "1"))
            await asyncio.sleep(retry_after)
            response = await self._client.request(method, url, **kwargs)
            self._last_request_time = asyncio.get_running_loop().time()

        response.raise_for_status()
        return response

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def get_puuid(self, game_name: str, tag_line: str) -> str:
        """Return the PUUID for the given Riot ID."""
        encoded_name = quote(game_name, safe="")
        encoded_tag = quote(tag_line, safe="")
        url = f"{ACCOUNT_BASE}/riot/account/v1/accounts/by-riot-id/{encoded_name}/{encoded_tag}"
        response = await self._request("GET", url)
        return response.json()["puuid"]

    async def get_match_ids(
        self,
        puuid: str,
        count: int = 20,
        queue_type: Optional[int] = None,
    ) -> list[str]:
        """Return a list of match IDs for the given PUUID."""
        url = f"{MATCH_BASE}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params: dict = {"count": count}
        if queue_type is not None:
            params["queue"] = queue_type
        response = await self._request("GET", url, params=params)
        return response.json()

    async def get_match_detail(self, match_id: str) -> dict:
        """Return full match detail JSON."""
        url = f"{MATCH_BASE}/lol/match/v5/matches/{match_id}"
        response = await self._request("GET", url)
        return response.json()

    async def get_match_timeline(self, match_id: str) -> dict:
        """Return match timeline JSON."""
        url = f"{MATCH_BASE}/lol/match/v5/matches/{match_id}/timeline"
        response = await self._request("GET", url)
        return response.json()

    async def get_item_data(self) -> dict[int, dict[str, str]]:
        """Fetch item ID -> {name, type} mapping from Data Dragon."""
        # Get latest version
        resp = await self._request(
            "GET", "https://ddragon.leagueoflegends.com/api/versions.json"
        )
        version = resp.json()[0]
        # Get item data
        resp = await self._request(
            "GET",
            f"https://ddragon.leagueoflegends.com/cdn/{version}/data/ja_JP/item.json",
        )
        items = resp.json()["data"]
        result: dict[int, dict[str, str]] = {}
        for item_id_str, info in items.items():
            item_id = int(item_id_str)
            name = info.get("name", f"Item {item_id}")
            item_type = _classify_item(info, item_id)
            result[item_id] = {"name": name, "type": item_type}
        return result

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def parse_match_summary(self, match_data: dict, puuid: str) -> MatchSummary:
        """Extract a MatchSummary for the given PUUID from match detail JSON."""
        info = match_data["info"]
        match_id: str = match_data["metadata"]["matchId"]

        try:
            participant = next(
                p for p in info["participants"] if p["puuid"] == puuid
            )
        except StopIteration:
            raise ValueError(
                f"Participant with puuid={puuid!r} not found in match {match_id!r}"
            )

        cs = participant["totalMinionsKilled"] + participant["neutralMinionsKilled"]
        queue_type = str(info.get("queueId", ""))

        # Kill participation: (K+A) / team total kills
        my_team_id = participant["teamId"]
        team_kills = sum(
            p["kills"] for p in info["participants"] if p["teamId"] == my_team_id
        )
        my_ka = participant["kills"] + participant["assists"]
        kill_participation = my_ka / team_kills if team_kills > 0 else 0.0

        # Damage breakdown
        damage_physical = participant.get("physicalDamageDealtToChampions", 0)
        damage_magical = participant.get("magicDamageDealtToChampions", 0)
        damage_true = participant.get("trueDamageDealtToChampions", 0)

        # Team compositions and lane opponents
        my_role = participant.get("teamPosition", "")
        ally_team = []
        enemy_team = []
        lane_opponents = []
        # Bot lane is 2v2: BOTTOM and UTILITY face each other as a pair
        bot_lane_roles = {"BOTTOM", "UTILITY"}
        is_bot_lane = my_role in bot_lane_roles
        for p in info["participants"]:
            if p["puuid"] == puuid:
                continue
            if p["teamId"] == my_team_id:
                ally_team.append(p["championName"])
            else:
                enemy_team.append(p["championName"])
                p_role = p.get("teamPosition", "")
                if my_role and is_bot_lane:
                    # Bot lane: opponent is both enemy BOTTOM and UTILITY
                    if p_role in bot_lane_roles:
                        lane_opponents.append(p["championName"])
                elif my_role and p_role == my_role:
                    lane_opponents.append(p["championName"])

        return MatchSummary(
            match_id=match_id,
            champion=participant["championName"],
            kills=participant["kills"],
            deaths=participant["deaths"],
            assists=participant["assists"],
            cs=cs,
            gold_earned=participant["goldEarned"],
            total_damage_dealt=participant["totalDamageDealtToChampions"],
            vision_score=participant["visionScore"],
            win=participant["win"],
            game_mode=info["gameMode"],
            queue_type=queue_type,
            game_duration_seconds=info["gameDuration"],
            timestamp_ms=info["gameCreation"],
            role=my_role,
            lane_opponents=lane_opponents,
            ally_team=ally_team,
            enemy_team=enemy_team,
            kill_participation=kill_participation,
            damage_physical=damage_physical,
            damage_magical=damage_magical,
            damage_true=damage_true,
        )

    def parse_timeline(
        self,
        timeline_data: dict,
        match_id: str,
        puuid: str,  # noqa: ARG002 - reserved for future cross-reference validation
        participant_id: int,
        item_data: dict[int, dict[str, str]] | None = None,
        opponent_ids: list[int] | None = None,
    ) -> PlayerStats:
        """Extract PlayerStats from match timeline JSON."""
        frames = timeline_data["info"]["frames"]

        gold_timeline: list[int] = []
        position_timeline: list[dict] = []
        jungle_cs_timeline: list[dict] = []
        kill_timestamps: list[int] = []
        death_timestamps: list[int] = []
        assist_timestamps: list[int] = []
        objective_events: list[dict] = []
        item_purchases: list[dict] = []
        skill_level_ups: list[dict] = []
        level_ups: list[dict] = []
        opponent_level_ups: list[dict] = []
        opponent_ids = opponent_ids or []

        pid_str = str(participant_id)
        item_data = item_data or {}

        for frame in frames:
            # Gold timeline: gold at each minute frame
            participant_frames = frame.get("participantFrames", {})
            if pid_str in participant_frames:
                participant_frame = participant_frames[pid_str]
                frame_ts_seconds = frame.get("timestamp", 0) // 1000
                gold_timeline.append(participant_frame["totalGold"])

                position = participant_frame.get("position")
                if isinstance(position, dict):
                    x = position.get("x")
                    y = position.get("y")
                    if isinstance(x, int) and isinstance(y, int):
                        position_timeline.append({
                            "timestamp": frame_ts_seconds,
                            "x": x,
                            "y": y,
                        })

                jungle_cs = participant_frame.get("jungleMinionsKilled")
                if isinstance(jungle_cs, int):
                    jungle_cs_timeline.append({
                        "timestamp": frame_ts_seconds,
                        "jungle_cs": jungle_cs,
                    })

            # Events
            for event in frame.get("events", []):
                event_type = event.get("type")
                ts_seconds = event.get("timestamp", 0) // 1000

                if event_type == "CHAMPION_KILL":
                    killer_id = event.get("killerId")
                    victim_id = event.get("victimId")
                    assisting = event.get("assistingParticipantIds", [])

                    if killer_id == participant_id:
                        kill_timestamps.append(ts_seconds)
                    if victim_id == participant_id:
                        death_timestamps.append(ts_seconds)
                    if participant_id in assisting:
                        assist_timestamps.append(ts_seconds)

                elif event_type in ("ELITE_MONSTER_KILL", "BUILDING_KILL"):
                    objective_events.append({
                        "type": event_type,
                        "timestamp": ts_seconds,
                        **{k: v for k, v in event.items() if k not in ("type", "timestamp")},
                    })

                elif event_type == "LEVEL_UP":
                    evt_pid = event.get("participantId")
                    level = event.get("level", 0)
                    if evt_pid == participant_id:
                        level_ups.append({
                            "timestamp": ts_seconds,
                            "level": level,
                        })
                    elif evt_pid in opponent_ids:
                        opponent_level_ups.append({
                            "timestamp": ts_seconds,
                            "level": level,
                            "participant_id": evt_pid,
                        })

                elif event_type == "SKILL_LEVEL_UP":
                    if event.get("participantId") == participant_id:
                        slot = event.get("skillSlot", 0)
                        level_up_type = event.get("levelUpType", "NORMAL")
                        # skillSlot: 1=Q, 2=W, 3=E, 4=R
                        slot_name = {1: "Q", 2: "W", 3: "E", 4: "R"}.get(slot, f"?{slot}")
                        skill_level_ups.append({
                            "timestamp": ts_seconds,
                            "skill": slot_name,
                            "type": level_up_type,
                        })

                elif event_type == "ITEM_PURCHASED":
                    if event.get("participantId") == participant_id:
                        item_id = event.get("itemId", 0)
                        info = item_data.get(item_id, {})
                        item_purchases.append({
                            "item_id": item_id,
                            "timestamp": ts_seconds,
                            "item_name": info.get("name", f"Item {item_id}"),
                            "item_type": info.get("type", "component"),
                        })

        # Number completed items as "コア（N個目）"
        core_count = 0
        type_labels = {
            "ward": "ワード（視界）",
            "consumable": "消費",
            "component": "素材",
            "boots": "ブーツ",
        }
        for item in item_purchases:
            raw_type = item["item_type"]
            if raw_type == "completed":
                core_count += 1
                item["item_type_label"] = f"コア（{core_count}個目）"
            else:
                item["item_type_label"] = type_labels.get(raw_type, raw_type)

        # gold_diff_timeline is simplified to 0 for now
        gold_diff_timeline = [0] * len(gold_timeline)

        return PlayerStats(
            match_id=match_id,
            gold_timeline=gold_timeline,
            gold_diff_timeline=gold_diff_timeline,
            position_timeline=position_timeline,
            jungle_cs_timeline=jungle_cs_timeline,
            kill_timestamps=kill_timestamps,
            death_timestamps=death_timestamps,
            assist_timestamps=assist_timestamps,
            objective_events=objective_events,
            item_purchases=item_purchases,
            skill_level_ups=skill_level_ups,
            level_ups=level_ups,
            opponent_level_ups=opponent_level_ups,
        )
