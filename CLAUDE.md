# CLAUDE.md

## Repository Overview

League of Legends 上達支援ツール群。試合データの分析と動画分析を組み合わせて、具体的な改善アドバイスを生成する。

## Projects

### lol_review — 試合データ分析
Riot API から試合データを取得し、統計分析・改善点検出・HTMLレポートを生成する。

```bash
cd lol_review && uv sync
uv run lol-review report "SummonerName#JP1" --no-open
```

### lol_vod_analyzer — 動画分析
YouTube 解説動画やローカル動画を AI で分析し、構造化されたHTMLレポートを生成する。

```bash
cd lol_vod_analyzer && uv sync
# YouTube 解説動画
uv run lol-vod 'https://youtube.com/...' --mode commentary
# ローカル動画 + 試合データ連携
uv run lol-vod ~/Desktop/replay.mov --mode gameplay --interval 5 \
  --match-data ../lol_review/output/latest_findings.json
# YouTube 動画ダウンロード → ローカル分析
uv run lol-vod 'https://youtube.com/...' --download --mode gameplay
```

## Technology Stack

- **Python 3.12+** / **uv** package manager
- **Riot API** (lol_review)
- **Google Gemini API** (lol_vod_analyzer)
- **yt-dlp** (YouTube字幕・ストーリーボード・動画ダウンロード)
- **OpenCV** / **Pillow** (スクリーンショット抽出・画像処理)
- **ffmpeg** (音声抽出・画面録画)
- **Pydantic** / **Jinja2** / **Typer** / **Rich**
- **pytest** (テスト)

## Environment Requirements

各プロジェクトの `.env` に API Key を設定:
- `lol_review/.env`: `RIOT_API_KEY=...`
- `lol_vod_analyzer/.env`: `GOOGLE_API_KEY=...`

## Testing

```bash
cd lol_review && uv run pytest
cd lol_vod_analyzer && uv run pytest
```

## Data Flow

```
Riot API → lol_review → latest_findings.json
                              ↓ --match-data
動画 → lol_vod_analyzer → vod_analysis_*.html
```

## 開発方針

- 解説動画からの言語化されたナレッジ蓄積が最優先
- 自分の試合データ (Riot API) と動画の組み合わせで高精度分析
- 画像のみの分析は精度が低いため、match-data 連携を前提とする
