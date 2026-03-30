"""Direct video analysis via Gemini multimodal API.

Upload a video file directly to Gemini and get analysis.
Use this to verify lol-vod-analyzer output against raw LLM analysis.

Usage:
    uv run python scripts/analyze_video_direct.py <video_path> [--prompt <prompt>]
    uv run python scripts/analyze_video_direct.py ~/Desktop/lol_replay_5min.mov
    uv run python scripts/analyze_video_direct.py ~/Desktop/lol_replay_5min.mov --prompt "この動画のEliseの立ち回りを評価して"
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

MODEL_NAME = "gemini-2.5-flash"

DEFAULT_PROMPT = """あなたはLeague of Legendsの分析エキスパートです。
この動画はLoLのゲームプレイ動画です。

以下の観点で動画を分析してください:

1. **試合概要** — チャンピオン構成、ロール、勝敗の推定
2. **序盤（0-5分）** — レーン戦、レベル先行、ファーストブラッド
3. **中盤（5-15分）** — オブジェクト、ローム、集団戦
4. **終盤（15分以降）** — バロン、インヒビター、ゲームクローズ
5. **注目プレイ** — 上手いプレイ、改善できるプレイ
6. **実践アドバイス** — すぐに使える改善点を3つ

日本語で回答してください。"""


def _elapsed(start: float) -> str:
    s = int(time.time() - start)
    return f"{s // 60}:{s % 60:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Direct video analysis via Gemini")
    parser.add_argument("video", type=Path, help="Video file path")
    parser.add_argument("--prompt", type=str, default=None, help="Custom analysis prompt")
    parser.add_argument("--output", type=Path, default=None, help="Save output to file")
    args = parser.parse_args()

    if not args.video.exists():
        print(f"Error: {args.video} not found", file=sys.stderr)
        sys.exit(1)

    # scripts/ -> lol_vod_analyzer/ -> packages/ -> lol-tools/
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    load_dotenv(env_path)
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    prompt = args.prompt or DEFAULT_PROMPT
    total_start = time.time()

    # Step 1: Upload
    size_mb = args.video.stat().st_size / 1024 / 1024
    print(f"[1/3] Uploading {args.video.name} ({size_mb:.1f} MB)...", flush=True)
    upload_start = time.time()
    uploaded = client.files.upload(file=args.video)
    print(f"[1/3] Upload complete ({_elapsed(upload_start)}): {uploaded.name}", flush=True)

    # Step 2: Wait for processing
    print(f"[2/3] Processing...", end="", flush=True)
    process_start = time.time()
    poll_count = 0
    while uploaded.state.name == "PROCESSING":
        time.sleep(5)
        poll_count += 1
        uploaded = client.files.get(name=uploaded.name)
        print(f"\r[2/3] Processing... {_elapsed(process_start)} (poll #{poll_count})", end="", flush=True)

    if uploaded.state.name != "ACTIVE":
        print(f"\nError: Upload failed with state {uploaded.state.name}", file=sys.stderr)
        sys.exit(1)
    print(f"\r[2/3] Processing complete ({_elapsed(process_start)})", flush=True)

    # Step 3: Analyze
    print(f"[3/3] Analyzing with {MODEL_NAME}...", flush=True)
    analyze_start = time.time()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[uploaded, prompt],
    )
    print(f"[3/3] Analysis complete ({_elapsed(analyze_start)})", flush=True)

    # Summary
    total = _elapsed(total_start)
    print(f"\nTotal time: {total}", flush=True)
    print("=" * 60)
    print(response.text)
    print("=" * 60)

    if args.output:
        args.output.write_text(response.text, encoding="utf-8")
        print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
