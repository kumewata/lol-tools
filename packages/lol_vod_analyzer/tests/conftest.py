import pytest
from pathlib import Path


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def sample_yt_info() -> dict:
    return {
        "title": "【LoL】エリス完全解説",
        "duration": 2191,
        "automatic_captions": {
            "ja": [
                {"ext": "json3", "url": "https://example.com/subs.json3"},
                {"ext": "srt", "url": "https://example.com/subs.srt"},
            ]
        },
        "formats": [
            {
                "format_id": "sb0",
                "ext": "mhtml",
                "resolution": "320x180",
                "vcodec": "none",
                "acodec": "none",
                "fragments": [
                    {"url": "https://example.com/sb0_frag0.jpg"},
                    {"url": "https://example.com/sb0_frag1.jpg"},
                ],
                "columns": 5,
                "rows": 5,
            },
        ],
    }


@pytest.fixture
def sample_caption_json3() -> dict:
    return {
        "events": [
            {"tStartMs": 1500, "dDurationMs": 4000, "segs": [{"utf8": "こんにちは。"}]},
            {"tStartMs": 5500, "dDurationMs": 3000, "segs": [{"utf8": "エリスの"}, {"utf8": "解説です。"}]},
            {"tStartMs": 8500, "dDurationMs": 2000, "segs": [{"utf8": "\n"}]},
        ]
    }
