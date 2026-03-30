# lol-tools

League of Legends の試合データ分析と動画分析を、1つの CLI から扱うツール集。

## このリポジトリでできること

- Riot API から直近の試合データを取得して改善点をレポート化する
- YouTube の解説動画やローカルのリプレイ動画を分析して学習メモを作る
- 試合データと動画分析を組み合わせて、自分のプレイ改善に使う

## 3分クイックスタート

### 前提条件

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- ffmpeg

```bash
# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# ffmpeg (macOS)
brew install ffmpeg
```

### セットアップ

```bash
git clone <repo>
cd lol-tools
uv sync
cp .env.example .env
uv run lol-tools init
uv run lol-tools doctor
```

`.env` には必要に応じて以下を設定する。

```dotenv
RIOT_API_KEY=your_riot_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
DEFAULT_RIOT_ID=SummonerName#JP1
DEFAULT_COUNT=20
```

## まず使うコマンド

### 試合データ分析

```bash
# Riot ID を直接指定
uv run lol-tools review "SummonerName#JP1"

# .env の DEFAULT_RIOT_ID を使う
uv run lol-tools review

# 直近1試合だけ
uv run lol-tools review --count 1 --no-open
```

出力:

- HTML レポート: `packages/lol_review/output/`
- 最新の JSON: `packages/lol_review/output/latest_findings.json`

### 動画分析

```bash
# YouTube 解説動画を分析
uv run lol-tools vod analyze 'https://youtube.com/watch?v=...' --mode commentary

# 字幕がない YouTube 動画をダウンロードして分析
uv run lol-tools vod analyze 'https://youtube.com/watch?v=...' --download --mode gameplay

# ローカルの録画を分析
uv run lol-tools vod analyze ~/Desktop/replay.mov --mode gameplay --interval 5
```

出力:

- HTML レポート: `packages/lol_vod_analyzer/output/`

### 試合データつきでリプレイ分析

```bash
# 1. 先に直近1試合の試合データを取得
uv run lol-tools review --count 1 --no-open

# 2. 試合データを添えて動画分析
uv run lol-tools vod analyze ~/Desktop/replay.mov \
  --mode gameplay \
  --interval 5 \
  --match-data packages/lol_review/output/latest_findings.json
```

## リプレイ分析の標準ワークフロー

```bash
# 1. 試合データを取得
uv run lol-tools review --count 1 --no-open

# 2. LoL クライアントでリプレイを再生し、ffmpeg で録画
ffmpeg -f avfoundation -i "1:none" -t 900 -r 10 -vf scale=1280:720 ~/Desktop/replay.mov

# 3. 動画分析
uv run lol-tools vod analyze ~/Desktop/replay.mov \
  --mode gameplay \
  --interval 5 \
  --match-data packages/lol_review/output/latest_findings.json
```

`"1"` は画面番号。環境に応じて `ffmpeg -f avfoundation -list_devices true -i ""` で確認する。

## 補助コマンド

```bash
# .env の作成・更新を支援
uv run lol-tools init

# 設定漏れや依存不足を診断
uv run lol-tools doctor

# 代表的な実行例だけ確認
uv run lol-tools examples
```

## トラブルシュート

### `RIOT_API_KEY` がないと言われる

- `.env` に `RIOT_API_KEY=...` を設定する
- 取得元: <https://developer.riotgames.com/>

### `GOOGLE_API_KEY` がないと言われる

- `.env` に `GOOGLE_API_KEY=...` を設定する
- 取得元: <https://aistudio.google.com/apikey>

### `ffmpeg` が見つからない

- macOS なら `brew install ffmpeg`
- セットアップ後に `uv run lol-tools doctor` で再確認する

### どのコマンドから始めればよいか分からない

```bash
uv run lol-tools examples
```

## テスト

```bash
uv run pytest
```

## 開発者向けメモ

### CLI の入口

- 統一入口: `uv run lol-tools`
- 試合データ分析: `review`
- 動画分析: `vod analyze`

### リポジトリ構成

```text
src/lol_tools/                 # 統一 CLI
packages/lol_review/           # 試合データ分析パッケージ
packages/lol_vod_analyzer/     # 動画分析パッケージ
docs/adr/                      # 設計判断の記録
skills/                        # AI skill の実体
```

### AI Skill Layout

- 共有スキル本体は `skills/` に配置
- `.claude/skills` は Claude Code 互換の入口
- `.codex/skills` は Codex 互換の入口
- スキル更新時は `skills/` 配下を編集する
