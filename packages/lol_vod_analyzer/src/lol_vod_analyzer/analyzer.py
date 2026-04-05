"""Gemini LLM analysis engine for LoL VOD analysis."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from google import genai
from PIL import Image
from pydantic import ValidationError

from lol_vod_analyzer.models import (
    AnalysisResult,
    ChunkAnalysis,
    KeyMoment,
    SceneSnapshot,
    Topic,
    TranscriptSegment,
    VideoSource,
)

MODEL_NAME = "gemini-2.5-flash"


def _parse_key_moments(items: list[dict] | None) -> list[KeyMoment]:
    key_moments: list[KeyMoment] = []

    for item in items or []:
        try:
            key_moments.append(KeyMoment(**item))
        except (TypeError, ValidationError):
            continue

    return key_moments


def _format_position(position: dict | None) -> str:
    if not isinstance(position, dict):
        return ""

    x = position.get("x")
    y = position.get("y")
    if not isinstance(x, int) or not isinstance(y, int):
        return ""

    return f"座標=({x}, {y})"


def _format_monster_label(event: dict) -> str:
    monster_type = event.get("monsterType", "UNKNOWN")
    monster_subtype = event.get("monsterSubType")
    if monster_subtype:
        return f"{monster_type}/{monster_subtype}"
    return str(monster_type)


def chunk_transcript(
    segments: list[TranscriptSegment],
    chunk_duration_ms: int = 180_000,
) -> list[list[TranscriptSegment]]:
    if not segments:
        return []

    chunks: list[list[TranscriptSegment]] = []
    current_chunk: list[TranscriptSegment] = []
    chunk_start = 0
    chunk_end = chunk_duration_ms

    for seg in segments:
        if seg.start_ms >= chunk_end and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            chunk_start = chunk_end
            chunk_end = chunk_start + chunk_duration_ms
        current_chunk.append(seg)

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def build_chunk_prompt(
    segments: list[TranscriptSegment],
    chunk_index: int,
    total_chunks: int,
    mode: Literal["commentary", "gameplay"],
) -> str:
    transcript_text = "\n".join(
        f"[{s.start_ms // 1000}s] {s.text}" for s in segments
    )

    if mode == "commentary":
        focus = (
            "この動画はLoLの解説・コーチング動画です。"
            "解説者が伝えている知識やアドバイスを正確に抽出してください。"
        )
    else:
        focus = (
            "この動画はLoLのゲームプレイ動画です。"
            "プレイヤーの判断や動きのポイントを分析してください。"
        )

    return f"""あなたはLeague of Legendsの分析エキスパートです。
{focus}

以下はチャンク {chunk_index + 1}/{total_chunks} の字幕テキストです。

---
{transcript_text}
---

以下のJSON形式で回答してください:
{{
  "summary": "このチャンクの内容要約（2-3文）",
  "key_moments": [
    {{
      "timestamp_ms": <タイムスタンプ（ミリ秒）>,
      "label": "場面の短いラベル",
      "analysis": "何が説明/実行されているか、なぜ重要か"
    }}
  ]
}}

重要なポイントのみをkey_momentsに含めてください。些末な内容は省略してください。
JSON以外のテキストは含めないでください。"""


def build_synthesis_prompt(
    chunks: list[ChunkAnalysis],
    mode: Literal["commentary", "gameplay"],
) -> str:
    chunk_summaries = "\n\n".join(
        f"### チャンク {c.chunk_index + 1} ({c.start_ms // 1000}s - {c.end_ms // 1000}s)\n"
        f"要約: {c.summary}\n"
        f"キーモーメント: {json.dumps([km.model_dump() for km in c.key_moments], ensure_ascii=False)}"
        for c in chunks
    )

    return f"""あなたはLeague of Legendsの分析エキスパートです。
以下は動画を時間チャンクに分割して分析した結果です。
これらを統合して、動画全体の分析レポートを作成してください。

{chunk_summaries}

以下のJSON形式で回答してください:
{{
  "summary": "動画全体の要約（3-5文）",
  "key_moments": [
    {{
      "timestamp_ms": <ミリ秒>,
      "label": "場面ラベル",
      "analysis": "分析内容"
    }}
  ],
  "topics": [
    {{
      "name": "トピック名（例: ルーン選択、ジャングルルート、ガンクタイミング）",
      "content": "トピックの詳細解説",
      "timestamps": [<関連タイムスタンプ（ミリ秒）のリスト>]
    }}
  ],
  "actionable_tips": [
    "すぐに実践できる具体的なアドバイス1",
    "すぐに実践できる具体的なアドバイス2"
  ]
}}

トピックは内容に応じて3-8個程度に整理してください。
actionable_tipsは最も重要な実践的アドバイスを5個以内で。
JSON以外のテキストは含めないでください。"""


def parse_chunk_response(
    response_text: str,
    chunk_index: int,
    start_ms: int,
    end_ms: int,
) -> ChunkAnalysis:
    try:
        data = json.loads(_extract_json(response_text))
        key_moments = _parse_key_moments(data.get("key_moments", []))
        return ChunkAnalysis(
            chunk_index=chunk_index,
            start_ms=start_ms,
            end_ms=end_ms,
            summary=data.get("summary", ""),
            key_moments=key_moments,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return ChunkAnalysis(
            chunk_index=chunk_index,
            start_ms=start_ms,
            end_ms=end_ms,
            summary=response_text.strip(),
            key_moments=[],
        )


def parse_synthesis_response(response_text: str) -> dict:
    try:
        data = json.loads(_extract_json(response_text))
        return {
            "summary": data.get("summary", ""),
            "key_moments": _parse_key_moments(data.get("key_moments", [])),
            "topics": [Topic(**t) for t in data.get("topics", [])],
            "actionable_tips": data.get("actionable_tips", []),
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValidationError):
        return {
            "summary": response_text.strip(),
            "key_moments": [],
            "topics": [],
            "actionable_tips": [],
        }


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                continue
            if line.strip() == "```" and in_block:
                break
            if in_block:
                json_lines.append(line)
        return "\n".join(json_lines)
    return text


def _build_chunk_timeline(
    match_context: dict,
    start_sec: int,
    end_sec: int,
) -> str:
    """Build a timeline of trusted Riot events for a time range."""
    timeline_entries: list[tuple[int, str]] = []

    def add_entry(ts: int, text: str) -> None:
        if start_sec <= ts < end_sec:
            timeline_entries.append((ts, text))

    # Kill/Death/Assist timestamps
    for ts in match_context.get("kill_timestamps", []):
        add_entry(ts, "キル獲得")
    for ts in match_context.get("death_timestamps", []):
        add_entry(ts, "デス")
    for ts in match_context.get("assist_timestamps", []):
        add_entry(ts, "アシスト")

    # Objective events from Riot timeline, including map position when present.
    for event in match_context.get("objective_events", []):
        ts = event.get("timestamp", 0)
        if not isinstance(ts, int) or not (start_sec <= ts < end_sec):
            continue

        event_type = event.get("type")
        position_text = _format_position(event.get("position"))
        if event_type == "ELITE_MONSTER_KILL":
            monster_label = _format_monster_label(event)
            killer_id = event.get("killerId", "?")
            suffix = f" {position_text}" if position_text else ""
            add_entry(ts, f"中立モンスター撃破: {monster_label}（killerId={killer_id}）{suffix}")
        elif event_type == "BUILDING_KILL":
            building_type = event.get("buildingType", "BUILDING")
            lane_type = event.get("laneType")
            lane_text = f"/{lane_type}" if lane_type else ""
            suffix = f" {position_text}" if position_text else ""
            add_entry(ts, f"建造物破壊: {building_type}{lane_text}{suffix}")

    # Item purchases
    for item in match_context.get("item_purchases", []):
        ts = item.get("timestamp", 0)
        if start_sec <= ts < end_sec:
            name = item.get("item_name", "不明")
            label = item.get("item_type_label", "")
            add_entry(ts, f"アイテム購入: {name}（{label}）")

    # Level ups
    for lvl in match_context.get("level_ups", []):
        ts = lvl.get("timestamp", 0)
        if start_sec <= ts < end_sec:
            level = lvl.get("level", "?")
            add_entry(ts, f"レベル{level}到達")

    # Opponent level ups
    opponents = ", ".join(match_context.get("lane_opponents", []))
    for lvl in match_context.get("opponent_level_ups", []):
        ts = lvl.get("timestamp", 0)
        if start_sec <= ts < end_sec:
            level = lvl.get("level", "?")
            add_entry(ts, f"対面({opponents})レベル{level}到達")

    # Skill level ups
    for skill in match_context.get("skill_level_ups", []):
        ts = skill.get("timestamp", 0)
        if start_sec <= ts < end_sec:
            slot = skill.get("skill", "?")
            evolve = "（進化）" if skill.get("type") == "EVOLVE" else ""
            add_entry(ts, f"スキルレベルアップ: {slot}{evolve}")

    # Frame-level position snapshots help anchor route reconstruction.
    for frame in match_context.get("position_timeline", []):
        ts = frame.get("timestamp", 0)
        if not isinstance(ts, int) or not (start_sec <= ts < end_sec):
            continue

        position_text = _format_position(frame)
        jungle_cs = next(
            (
                point.get("jungle_cs")
                for point in match_context.get("jungle_cs_timeline", [])
                if point.get("timestamp") == ts
            ),
            None,
        )
        jungle_text = f", jungleCS={jungle_cs}" if isinstance(jungle_cs, int) else ""
        suffix = f": {position_text}{jungle_text}" if position_text else f": jungleCS={jungle_cs}" if isinstance(jungle_cs, int) else ""
        add_entry(ts, f"位置スナップショット{suffix}")

    if not timeline_entries:
        return ""

    lines = [f"  - {ts // 60}:{ts % 60:02d} {text}" for ts, text in sorted(timeline_entries, key=lambda entry: entry[0])]
    return "\n## このチャンクの時間帯に発生したイベント（確定データ）\n" + "\n".join(lines) + "\n"


def build_gameplay_image_prompt(
    chunk_index: int,
    total_chunks: int,
    start_ms: int,
    end_ms: int,
    match_context: dict | None = None,
    game_start_offset: int = 0,
) -> str:
    """Build a prompt for analyzing gameplay from screenshots only."""
    role_map = {
        "UTILITY": "サポート（BOTレーン）",
        "BOTTOM": "ADC（BOTレーン）",
        "MIDDLE": "ミッドレーン",
        "TOP": "トップレーン",
        "JUNGLE": "ジャングル",
    }

    context_block = ""
    if match_context:
        champion = match_context.get('champion', '不明')
        role = match_context.get('role', '不明')
        role_ja = role_map.get(role, role)

        # Build timeline events for this chunk's time range (convert video time to game time)
        game_start_sec = start_ms // 1000 - game_start_offset
        game_end_sec = end_ms // 1000 - game_start_offset
        timeline_block = _build_chunk_timeline(match_context, game_start_sec, game_end_sec)

        context_block = f"""
## 試合データ（Riot API から取得済み — この情報は正確です）

**録画対象のプレイヤー: {champion}（{role_ja}）**
この動画は {champion} の視点で録画されています。画面中央に映っているチャンピオンが {champion} です。

- 味方チーム: {champion}({role_ja}), {', '.join(match_context.get('ally_team', []))}
- 敵チーム: {', '.join(match_context.get('enemy_team', []))}
- レーン対面: {', '.join(match_context.get('lane_opponents', []))}
- 試合時間: {match_context.get('game_duration_seconds', 0) // 60}分{match_context.get('game_duration_seconds', 0) % 60}秒
- 結果: {'勝利' if match_context.get('win') else '敗北'}
- 最終KDA: {match_context.get('kills', 0)}/{match_context.get('deaths', 0)}/{match_context.get('assists', 0)}
{timeline_block}
**この情報は確定事実です。** 画像から推測したロールやチャンピオン名で上書きしないでください。
{champion} は {role_ja} であり、ジャングラーではありません。
"""

    game_start_sec = start_ms // 1000 - game_start_offset
    game_end_sec = end_ms // 1000 - game_start_offset
    time_label = f"ゲーム内時間 {game_start_sec}秒 - {game_end_sec}秒" if game_start_offset else f"{start_ms // 1000}秒 - {end_ms // 1000}秒"

    return f"""あなたはLeague of Legendsの分析エキスパートです。
この動画はLoLのゲームプレイ動画です。字幕・解説はありません。
{context_block}
これはチャンク {chunk_index + 1}/{total_chunks}（{time_label}）のスクリーンショットです。

{champion if match_context else "プレイヤー"}の視点から、以下を分析してください:
- {champion if match_context else "プレイヤー"}のポジショニングと動き
- レーン状況（CS、レベル、キルスコア — 画面UIから読み取れる場合のみ）
- マップ状態（タワー、オブジェクト）
- 重要な判断やプレイ

**重要な制約:**
- 画像から確実に読み取れる情報のみを記述してください
- 読み取れないアイテム名やチャンピオン名を推測で出力しないでください
- 不明な場合は「不明」または「読み取り不可」と記載してください

以下のJSON形式で回答してください:
{{
  "summary": "このチャンクのゲーム状況要約（2-3文）",
  "key_moments": [
    {{
      "timestamp_ms": <推定タイムスタンプ（ミリ秒）>,
      "label": "場面の短いラベル",
      "analysis": "何が起きているか、なぜ重要か"
    }}
  ]
}}

JSON以外のテキストは含めないでください。"""


async def _analyze_snapshots_only(
    client: genai.Client,
    snapshots: list[SceneSnapshot],
    duration: int,
    chunk_duration_ms: int,
    match_context: dict | None = None,
    game_start_offset: int = 0,
) -> list[ChunkAnalysis]:
    """Analyze video from snapshots only (no transcript)."""
    total_duration_ms = duration * 1000
    num_chunks = max(1, total_duration_ms // chunk_duration_ms)
    chunk_analyses: list[ChunkAnalysis] = []

    for i in range(num_chunks):
        start_ms = i * chunk_duration_ms
        end_ms = min((i + 1) * chunk_duration_ms, total_duration_ms)

        chunk_snapshots = [
            s for s in snapshots if start_ms <= s.timestamp_ms < end_ms
        ]
        if not chunk_snapshots:
            continue

        prompt = build_gameplay_image_prompt(i, num_chunks, start_ms, end_ms, match_context, game_start_offset)
        contents: list = [prompt]

        # Use up to 6 images per chunk for gameplay (more visual context needed)
        step = max(1, len(chunk_snapshots) // 6)
        for s in chunk_snapshots[::step][:6]:
            if s.image_path.exists():
                img = Image.open(s.image_path)
                contents.append(img)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
        )
        chunk_analysis = parse_chunk_response(
            response.text, i, start_ms, end_ms
        )
        chunk_analyses.append(chunk_analysis)

    return chunk_analyses


async def analyze_video(
    source: VideoSource,
    transcript: list[TranscriptSegment],
    snapshots: list[SceneSnapshot],
    mode: Literal["commentary", "gameplay"],
    api_key: str | None = None,
    match_context: dict | None = None,
    game_start_offset: int = 0,
) -> AnalysisResult:
    if api_key is None:
        api_key = os.environ.get("GOOGLE_API_KEY", "")

    client = genai.Client(api_key=api_key)

    chunk_duration_ms = 180_000
    transcript_chunks = chunk_transcript(transcript, chunk_duration_ms)

    # gameplay mode with no transcript: analyze from snapshots only
    if not transcript_chunks:
        if mode == "gameplay" and snapshots:
            chunk_analyses = await _analyze_snapshots_only(
                client, snapshots, source.duration, chunk_duration_ms, match_context, game_start_offset
            )
        else:
            return AnalysisResult(
                source=source,
                mode=mode,
                summary="字幕データが取得できなかったため、分析できませんでした。",
                snapshots=snapshots,
            )
    else:
        chunk_analyses = []
        for i, chunk_segments in enumerate(transcript_chunks):
            start_ms = chunk_segments[0].start_ms
            end_ms = chunk_segments[-1].end_ms

            prompt = build_chunk_prompt(
                segments=chunk_segments,
                chunk_index=i,
                total_chunks=len(transcript_chunks),
                mode=mode,
            )

            contents: list = [prompt]
            chunk_snapshots = [
                s for s in snapshots if start_ms <= s.timestamp_ms < end_ms
            ]
            step = max(1, len(chunk_snapshots) // 4)
            for s in chunk_snapshots[::step][:4]:
                if s.image_path.exists():
                    img = Image.open(s.image_path)
                    contents.append(img)

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
            )
            chunk_analysis = parse_chunk_response(
                response.text, i, start_ms, end_ms
            )
            chunk_analyses.append(chunk_analysis)

    synthesis_prompt = build_synthesis_prompt(chunk_analyses, mode)
    synthesis_response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[synthesis_prompt],
    )
    synthesis = parse_synthesis_response(synthesis_response.text)

    return AnalysisResult(
        source=source,
        mode=mode,
        summary=synthesis["summary"],
        key_moments=synthesis["key_moments"],
        topics=synthesis["topics"],
        actionable_tips=synthesis["actionable_tips"],
        snapshots=snapshots,
    )
