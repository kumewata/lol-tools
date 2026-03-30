# tests/test_models.py
from lol_vod_analyzer.models import (
    VideoSource,
    TranscriptSegment,
    SceneSnapshot,
    KeyMoment,
    Topic,
    ChunkAnalysis,
    AnalysisResult,
)
from pathlib import Path


class TestVideoSource:
    def test_youtube_source(self):
        source = VideoSource(
            url="https://www.youtube.com/watch?v=SMsQCnKDzVw",
            title="エリス完全解説",
            duration=2191,
            source_type="youtube",
        )
        assert source.source_type == "youtube"
        assert source.local_path is None
        assert source.video_id == "SMsQCnKDzVw"

    def test_local_source(self):
        source = VideoSource(
            local_path=Path("/tmp/replay.mp4"),
            title="My Replay",
            duration=1800,
            source_type="local",
        )
        assert source.url is None
        assert source.video_id is None

    def test_youtube_url_returns_timestamp_link(self):
        source = VideoSource(
            url="https://www.youtube.com/watch?v=SMsQCnKDzVw",
            title="test",
            duration=100,
            source_type="youtube",
        )
        link = source.timestamp_url(65000)  # 65 seconds in ms
        assert link == "https://www.youtube.com/watch?v=SMsQCnKDzVw&t=65s"

    def test_local_source_timestamp_url_is_none(self):
        source = VideoSource(
            local_path=Path("/tmp/replay.mp4"),
            title="test",
            duration=100,
            source_type="local",
        )
        assert source.timestamp_url(5000) is None


class TestTranscriptSegment:
    def test_basic_segment(self):
        seg = TranscriptSegment(start_ms=1500, end_ms=5500, text="こんにちは")
        assert seg.start_ms == 1500
        assert seg.text == "こんにちは"


class TestKeyMoment:
    def test_key_moment(self):
        km = KeyMoment(
            timestamp_ms=120000,
            label="レベル3ガンク",
            analysis="トップレーンへのガンクタイミングが適切",
        )
        assert km.label == "レベル3ガンク"


class TestTopic:
    def test_topic(self):
        topic = Topic(
            name="ルーン選択",
            content="電撃を選択する理由は...",
            timestamps=[10000, 50000],
        )
        assert len(topic.timestamps) == 2


class TestChunkAnalysis:
    def test_chunk_analysis(self):
        chunk = ChunkAnalysis(
            chunk_index=0,
            start_ms=0,
            end_ms=180000,
            summary="序盤のルーン解説",
            key_moments=[
                KeyMoment(
                    timestamp_ms=10000,
                    label="ルーン説明",
                    analysis="電撃の選択理由",
                )
            ],
        )
        assert chunk.chunk_index == 0
        assert len(chunk.key_moments) == 1


class TestAnalysisResult:
    def test_analysis_result(self):
        source = VideoSource(
            url="https://www.youtube.com/watch?v=test",
            title="test",
            duration=100,
            source_type="youtube",
        )
        result = AnalysisResult(
            source=source,
            mode="commentary",
            summary="エリスの基本解説動画",
            key_moments=[],
            topics=[],
            actionable_tips=["レベル3でガンクを狙う"],
        )
        assert result.mode == "commentary"
        assert len(result.actionable_tips) == 1
