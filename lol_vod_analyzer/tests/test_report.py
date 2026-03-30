from pathlib import Path

from lol_vod_analyzer.models import (
    AnalysisResult,
    KeyMoment,
    Topic,
    VideoSource,
)
from lol_vod_analyzer.report import generate_report


class TestGenerateReport:
    def test_generates_html_file(self, tmp_output: Path):
        source = VideoSource(
            url="https://www.youtube.com/watch?v=SMsQCnKDzVw",
            title="エリス完全解説",
            duration=2191,
            source_type="youtube",
        )
        result = AnalysisResult(
            source=source,
            mode="commentary",
            summary="エリスの基本を網羅した解説動画",
            key_moments=[
                KeyMoment(
                    timestamp_ms=60000,
                    label="ルーン解説",
                    analysis="電撃を選ぶ理由の説明",
                ),
            ],
            topics=[
                Topic(
                    name="ルーン選択",
                    content="電撃が最適な理由",
                    timestamps=[60000],
                ),
            ],
            actionable_tips=["レベル3でガンクを狙う"],
        )

        output_path = generate_report(result, output_dir=tmp_output, open_browser=False)

        assert output_path.exists()
        html = output_path.read_text(encoding="utf-8")
        assert "エリス完全解説" in html
        assert "ルーン選択" in html
        assert "レベル3でガンクを狙う" in html
        assert "v=SMsQCnKDzVw&amp;t=60s" in html or "v=SMsQCnKDzVw&t=60s" in html

    def test_empty_result(self, tmp_output: Path):
        source = VideoSource(
            url="https://www.youtube.com/watch?v=test",
            title="Empty",
            duration=100,
            source_type="youtube",
        )
        result = AnalysisResult(
            source=source,
            mode="commentary",
            summary="分析結果なし",
        )
        output_path = generate_report(result, output_dir=tmp_output, open_browser=False)
        assert output_path.exists()
