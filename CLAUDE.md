# CLAUDE.md

## Repository Overview

League of Legends 上達支援ツール群。試合データの分析と動画分析を組み合わせて、具体的な改善アドバイスを生成する。

## Shared Skills

- 共有スキル本体は `skills/` 配下に置く
- `.claude/skills` は `skills/` への互換リンク
- `.codex/skills` も `skills/` への互換リンク
- Claude Code / Codex のどちら向けの更新でも、編集先は `skills/` を正とする

## Project Structure

uv workspace による monorepo 構成。

```
lol-tools/
├── pyproject.toml              # workspace root + lol-tools CLI
├── src/lol_tools/cli.py        # 統一エントリポイント
├── .env                        # 全 API キー（RIOT_API_KEY, GOOGLE_API_KEY）
├── packages/
│   ├── lol_review/             # 試合データ分析
│   │   ├── pyproject.toml
│   │   ├── src/lol_review/
│   │   ├── templates/
│   │   └── tests/
│   └── lol_vod_analyzer/       # 動画分析
│       ├── pyproject.toml
│       ├── src/lol_vod_analyzer/
│       ├── templates/
│       └── tests/
```

## Setup

```bash
uv sync                         # 全パッケージの依存関係を一括インストール
```

## Usage

### 統一 CLI

```bash
# 試合データ分析
uv run lol-tools review "SummonerName#JP1" --no-open

# 動画分析
uv run lol-tools vod analyze 'https://youtube.com/...' --mode commentary
```

### 個別コマンド（後方互換）

```bash
# 試合データ分析
uv run lol-review report "SummonerName#JP1" --no-open

# YouTube 解説動画
uv run lol-vod 'https://youtube.com/...' --mode commentary
# ローカル動画 + 試合データ連携
uv run lol-vod ~/Desktop/replay.mov --mode gameplay --interval 5 \
  --match-data packages/lol_review/output/latest_findings.json
# YouTube 動画ダウンロード → ローカル分析
uv run lol-vod 'https://youtube.com/...' --download --mode gameplay
```

## Technology Stack

- **Python 3.12+** / **uv** package manager (workspace)
- **Riot API** (lol_review)
- **Google Gemini API** (lol_vod_analyzer)
- **yt-dlp** (YouTube字幕・ストーリーボード・動画ダウンロード)
- **OpenCV** / **Pillow** (スクリーンショット抽出・画像処理)
- **ffmpeg** (音声抽出・画面録画)
- **Pydantic** / **Jinja2** / **Typer** / **Click** / **Rich**
- **pytest** (テスト)

## Environment Requirements

ルートの `.env` に全 API キーを設定:

```
RIOT_API_KEY=...
GOOGLE_API_KEY=...
DEFAULT_COUNT=20
```

## Testing

```bash
uv run pytest packages/lol_review/tests
uv run pytest packages/lol_vod_analyzer/tests
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
