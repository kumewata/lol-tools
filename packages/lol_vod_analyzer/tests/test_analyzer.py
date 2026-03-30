import json
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from lol_vod_analyzer.analyzer import (
    build_chunk_prompt,
    build_synthesis_prompt,
    chunk_transcript,
    parse_chunk_response,
    parse_synthesis_response,
)
from lol_vod_analyzer.models import (
    ChunkAnalysis,
    KeyMoment,
    TranscriptSegment,
    Topic,
)


class TestChunkTranscript:
    def test_chunk_by_duration(self):
        segments = [
            TranscriptSegment(start_ms=0, end_ms=10000, text="segment 1"),
            TranscriptSegment(start_ms=10000, end_ms=60000, text="segment 2"),
            TranscriptSegment(start_ms=60000, end_ms=120000, text="segment 3"),
            TranscriptSegment(start_ms=120000, end_ms=200000, text="segment 4"),
            TranscriptSegment(start_ms=200000, end_ms=300000, text="segment 5"),
        ]
        chunks = chunk_transcript(segments, chunk_duration_ms=120_000)
        assert len(chunks) == 2
        # First chunk: 0-120s (segments 1,2,3)
        assert len(chunks[0]) == 3
        # Second chunk: 120-240s (segments 4,5)
        assert len(chunks[1]) == 2

    def test_empty_transcript(self):
        chunks = chunk_transcript([], chunk_duration_ms=180_000)
        assert chunks == []


class TestBuildChunkPrompt:
    def test_commentary_prompt(self):
        segments = [
            TranscriptSegment(start_ms=0, end_ms=5000, text="ルーンの説明です"),
        ]
        prompt = build_chunk_prompt(
            segments=segments,
            chunk_index=0,
            total_chunks=3,
            mode="commentary",
        )
        assert "ルーンの説明です" in prompt
        assert "チャンク 1/3" in prompt


class TestParseChunkResponse:
    def test_parse_valid_json(self):
        response_text = json.dumps({
            "summary": "ルーン選択の解説",
            "key_moments": [
                {
                    "timestamp_ms": 10000,
                    "label": "ルーン紹介",
                    "analysis": "電撃を選ぶ理由",
                }
            ],
        })
        chunk = parse_chunk_response(response_text, chunk_index=0, start_ms=0, end_ms=180000)
        assert chunk.summary == "ルーン選択の解説"
        assert len(chunk.key_moments) == 1

    def test_parse_invalid_json_returns_raw_summary(self):
        response_text = "This is not JSON but a useful summary."
        chunk = parse_chunk_response(response_text, chunk_index=0, start_ms=0, end_ms=180000)
        assert "This is not JSON" in chunk.summary
        assert chunk.key_moments == []


class TestParseSynthesisResponse:
    def test_parse_valid_synthesis(self):
        response_text = json.dumps({
            "summary": "エリスの総合解説動画",
            "key_moments": [
                {"timestamp_ms": 10000, "label": "ルーン", "analysis": "電撃推奨"},
            ],
            "topics": [
                {"name": "ルーン", "content": "電撃が最適", "timestamps": [10000]},
            ],
            "actionable_tips": ["レベル3でガンクを狙う"],
        })
        result = parse_synthesis_response(response_text)
        assert result["summary"] == "エリスの総合解説動画"
        assert len(result["topics"]) == 1
        assert len(result["actionable_tips"]) == 1


class TestBuildSynthesisPrompt:
    def test_synthesis_prompt_includes_chunks(self):
        chunks = [
            ChunkAnalysis(
                chunk_index=0,
                start_ms=0,
                end_ms=180000,
                summary="ルーン解説",
                key_moments=[],
            ),
        ]
        prompt = build_synthesis_prompt(chunks, mode="commentary")
        assert "ルーン解説" in prompt
