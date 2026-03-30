# lol-tools

League of Legends 上達支援ツール群。試合データの分析と動画分析を組み合わせて、具体的な改善アドバイスを生成する。

## セットアップ

### 前提条件

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) パッケージマネージャ
- ffmpeg（画面録画・音声抽出に使用）

```bash
# uv のインストール
curl -LsSf https://astral.sh/uv/install.sh | sh

# ffmpeg のインストール（macOS）
brew install ffmpeg
```

### API Key の設定

```bash
# Riot API Key（試合データ取得用）
# https://developer.riotgames.com/ から取得
echo "RIOT_API_KEY=your_key_here" > lol_review/.env

# Google API Key（Gemini AI 動画分析用）
# https://aistudio.google.com/apikey から取得
echo "GOOGLE_API_KEY=your_key_here" > lol_vod_analyzer/.env
```

### 依存関係のインストール

```bash
cd lol_review && uv sync && cd ..
cd lol_vod_analyzer && uv sync && cd ..
```

## 使い方

### 試合データ分析 (lol_review)

```bash
cd lol_review

# 直近20試合のレポートを生成
uv run lol-review report "SummonerName#JP1"

# 直近1試合のみ
uv run lol-review report "SummonerName#JP1" --count 1

# ブラウザを開かない
uv run lol-review report "SummonerName#JP1" --no-open
```

### 動画分析 (lol_vod_analyzer)

```bash
cd lol_vod_analyzer

# YouTube 解説動画の分析（字幕ベース）
uv run lol-vod 'https://youtube.com/watch?v=...' --mode commentary

# YouTube 動画をダウンロードして分析（字幕がない動画向け）
uv run lol-vod 'https://youtube.com/watch?v=...' --download --mode gameplay

# ローカル動画の分析
uv run lol-vod ~/Desktop/replay.mov --mode gameplay --interval 5

# 試合データと連携して精度を上げる
uv run lol-vod ~/Desktop/replay.mov --mode gameplay --interval 5 \
  --match-data ../lol_review/output/latest_findings.json
```

### 自分のリプレイを分析するワークフロー

```bash
# 1. 試合データを取得
cd lol_review
uv run lol-review report "SummonerName#JP1" --count 1 --no-open

# 2. LoLクライアントでリプレイを再生し、ffmpegで画面録画
ffmpeg -f avfoundation -i "1:none" -t 900 -r 10 -vf scale=1280:720 ~/Desktop/replay.mov
# ※ "1" は画面番号。ffmpeg -f avfoundation -list_devices true -i "" で確認

# 3. 試合データ付きで動画分析
cd ../lol_vod_analyzer
uv run lol-vod ~/Desktop/replay.mov --mode gameplay --interval 5 \
  --match-data ../lol_review/output/latest_findings.json
```

### 動画の直接分析（検証用）

```bash
cd lol_vod_analyzer

# Gemini に動画をまるごとアップロードして分析
uv run python scripts/analyze_video_direct.py ~/Desktop/replay.mov

# カスタムプロンプト
uv run python scripts/analyze_video_direct.py ~/Desktop/replay.mov \
  --prompt "この動画のElise SUPの立ち回りを評価して"
```

## テスト

```bash
cd lol_review && uv run pytest
cd lol_vod_analyzer && uv run pytest
```

## CLIオプション一覧

### lol-vod

| オプション | 説明 |
|-----------|------|
| `--mode` | `commentary`（解説動画）or `gameplay`（プレイ動画） |
| `--download` | YouTube動画をダウンロードしてローカル分析 |
| `--interval N` | スクリーンショット間隔（秒、デフォルト10） |
| `--match-data PATH` | lol_reviewのfindings.jsonで試合データ連携 |
| `--lang CODE` | 字幕言語（デフォルト`ja`） |
| `--no-open` | レポートをブラウザで開かない |
