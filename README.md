# lol-tools

[![CI](https://github.com/kumewata/lol-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/kumewata/lol-tools/actions/workflows/ci.yml)

League of Legends の試合データ分析と動画分析を、1つの CLI から扱うツール集。

## このリポジトリでできること

- Riot API から直近の試合データを取得して改善点をレポート化する
- 動画を分析して学習メモを作る
  - YouTube の解説動画から知識を抽出する
  - 自分のプレイ動画やリプレイ録画を振り返る
  - 他人のリプレイ動画も分析できるが、これは実験的な扱い
- 試合データを動画分析に追加して、文脈つきで振り返る

## 機能の整理

このリポジトリの機能は、次のように整理すると分かりやすい。

1. 試合データ分析
   Riot API から試合統計を取得して、プレイ傾向や改善点を分析する。
2. 動画分析
   入力ソースに応じて 2 つの使い方がある。
   - 解説動画分析: YouTube の解説動画を見て、知識や判断基準を抽出する
   - プレイ動画分析: 自分の録画やリプレイ動画を見て、プレイ内容を振り返る

`プレイ動画分析` の標準的な対象は、自分の試合データと紐付けられる自分の録画やリプレイ動画。`試合データ付きリプレイ分析` によって試合内イベントやビルド文脈を加味できるため、分析精度が高い。

一方で、他の人が YouTube などにアップロードしたリプレイ動画は、通常は自分たちの試合データと紐付けられない。そのため文脈情報が不足し、分析精度は下がる。これは `プレイ動画分析` の中でも **実験的な機能** として扱う。

`試合データ付きリプレイ分析` は独立した第3機能ではなく、`プレイ動画分析` に `試合データ分析` の出力を追加した拡張ワークフロー。

## 3分クイックスタート

### 前提条件

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- ffmpeg（`ffprobe` を含む）

```bash
# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# ffmpeg / ffprobe (macOS)
brew install ffmpeg
```

Windows の例:

```powershell
# uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# ffmpeg / ffprobe
winget install Gyan.FFmpeg
```

別手段として `choco install ffmpeg` でもよい。

### セットアップ

```bash
git clone <repo>
cd lol-tools
uv sync
uv run lol-tools init
uv run lol-tools doctor
```

`uv run lol-tools init` は `.env` がなければ自動で作成する。手動で作る場合だけ `.env.example` を `.env` にコピーしてもよい。

#### Windows で `uv` 管理 Python が詰まる場合

Windows では `uv` が管理する Python が App Control / WDAC / Defender などでブロックされることがある。その場合は、`uv` に Python をダウンロードさせる代わりに、通常インストール済みの Python 3.12 を明示して使う方が安定しやすい。

実際に通った確認コマンドと実行コマンドの例:

```powershell
# Python Launcher から使える Python 一覧を確認
& "$env:LocalAppData\Programs\Python\Launcher\py.exe" -0p

# 3.12 本体と unicodedata が利用できることを確認
& "$env:LocalAppData\Programs\Python\Launcher\py.exe" -3.12 -c "import sys,unicodedata; print(sys.executable); print(sys.version); print(unicodedata.unidata_version)"

# 例: C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe が見つかった場合
uv sync -p "$env:LocalAppData\Programs\Python\Python312\python.exe" --refresh

# キャッシュ権限エラーも同時に疑うなら no-cache を付ける
uv sync -p "$env:LocalAppData\Programs\Python\Python312\python.exe" --refresh --no-cache

uv run lol-tools init
uv run lol-tools doctor
```

`uv run lol-tools review` 実行時に `ImportError: DLL load failed ... アプリケーション制御ポリシーによってこのファイルがブロックされました` のようなエラーが出る場合も、同様に通常インストール版 Python 3.12 に切り替えると回避できることが多い。

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

#### 解説動画分析

```bash
# YouTube 解説動画を分析
uv run lol-tools vod analyze 'https://youtube.com/watch?v=...' --mode commentary
```

`commentary` は YouTube 字幕を前提とする。ローカル動画の `commentary` モードは現在サポートしていない。

#### プレイ動画分析

標準ワークフローは、自分の試合を録画した動画を対象にする使い方。

```bash
# ローカルの録画を分析
uv run lol-tools vod analyze path/to/replay.mp4 --mode gameplay --interval 5

# 字幕がない YouTube 動画をダウンロードして分析
uv run lol-tools vod analyze 'https://youtube.com/watch?v=...' --download --mode gameplay
```

注意:

- 自分の試合録画は `--match-data` で試合データと組み合わせやすく、分析精度が高い
- 他人のリプレイ動画は試合データと紐付けられないことが多く、推定ベースの分析になる
- そのため、他人のリプレイ動画分析は実験的な機能として扱う

出力:

- HTML レポート: `packages/lol_vod_analyzer/output/`

### 試合データ付きリプレイ分析

`プレイ動画分析` に `試合データ分析` の結果を足して、試合内イベントの文脈を付ける使い方。
自分の試合録画を対象にした、もっとも精度の高いプレイ分析フロー。

録画方法が分からない場合は [自分のリプレイ動画を用意する手順](docs/replay-recording-guide.md) を参照。Windows で録画したい場合は [Windows 向けリプレイ録画ガイド](docs/replay-recording-guide-windows.md) も使える。
長尺 VOD の前処理から dry-run、本実行、通常 / focused 比較までを通しで見たい場合は [長尺 VOD の標準フロー](docs/long-vod-workflow.md) を参照。

```bash
# 標準フロー: replay analyze が試合データ取得と動画分析をつなぐ
uv run lol-tools replay analyze path/to/replay.mp4

# 少し前の試合を選ぶ
uv run lol-tools replay analyze path/to/replay.mp4 --review-count 5 --match-index 2
```

### Windows で実際に通ったコマンド例

Windows で `review` → `export-match-data` → `vod analyze` を通す場合は、次のように症状ごとの切り分けがしやすい。

レビュー実行例:

```powershell
uv run --no-cache lol-tools review --count 5 --no-open
```

複数試合のレビュー結果から動画分析向けの単一試合 JSON を作る例:

```powershell
$env:PYTHONUTF8='1'
uv run --no-cache lol-tools export-match-data --input "C:\Users\<you>\Desktop\lol-tools\packages\lol_review\output\latest_findings.json" --match-index 2 --output "C:\Users\<you>\Desktop\lol-tools\packages\lol_review\output\match_data_index2.json"
```

VOD 分析の実行例:

```powershell
$env:PYTHONUTF8='1'
uv run --no-cache lol-tools vod analyze "C:\Users\<you>\Downloads\lol_replay_5min.mov" --mode gameplay --interval 5 --match-data "C:\Users\<you>\Desktop\lol-tools\packages\lol_review\output\match_data_index2.json" --no-open
```

生成された HTML レポートを開く例:

```powershell
start "" "C:\Users\<you>\Desktop\lol-tools\packages\lol_vod_analyzer\output\vod_analysis_YYYYMMDD_HHMMSS.html"
```

## プレイ動画分析の標準ワークフロー

このワークフローは、自分の試合を Riot API の試合データと紐付けて分析できる前提のため、プレイ動画分析の中では標準機能として扱う。

詳細な録画手順は [docs/replay-recording-guide.md](docs/replay-recording-guide.md) を参照。Windows だけを見たい場合は [docs/replay-recording-guide-windows.md](docs/replay-recording-guide-windows.md) を参照。
長尺 replay の proxy 作成、`--speed` / `--game-start`、`--dry-run-sampling`、`--sampling-strategy focused`、sampling report 比較まで含めた再現フローは [docs/long-vod-workflow.md](docs/long-vod-workflow.md) にまとめている。

```bash
# 1. 試合データを取得
uv run lol-tools review --count 1 --no-open

# 2. LoL クライアントでリプレイを再生し、画面録画する
#    macOS の例
ffmpeg -f avfoundation -i "1:none" -t 900 -r 10 -vf scale=1280:720 ~/Desktop/replay.mov

# 3. replay analyze で試合データ付き分析
uv run lol-tools replay analyze ~/Desktop/replay.mov
```

Windows では Xbox Game Bar や OBS で `.mp4` を録画して、同じ `replay analyze` に渡せばよい。`ffmpeg` を使う場合は `gdigrab` など Windows 向け入力を使う。

## 長尺 VOD を扱うときの基本方針

- 長い gameplay 動画は、必要に応じて `ffmpeg` で軽量 proxy 動画を作ってから検証すると速い
- `vod analyze --match-data` には複数試合入りの `latest_findings.json` を直接渡さず、`export-match-data` で単一試合 JSON を作る
- 2 倍速 replay は `--speed 2.0`、動画先頭に待機時間があるときは `--game-start <秒>` を使う
- 本実行の前に `--dry-run-sampling` と `--dump-sampling-report` で screenshot 配分を確認すると、長尺 VOD の調整がしやすい
- `--sampling-strategy focused` と `--focus-profile` / `--focus-window-seconds` / `--focus-budget-ratio` / `--global-backfill` を使うと、重要局面への寄せ方を調整できる

代表例:

```bash
uv run lol-tools vod analyze path/to/replay.proxy.mp4 \
  --mode gameplay \
  --match-data packages/lol_review/output/match_data_index2.json \
  --sampling-strategy focused \
  --focus-profile balanced \
  --dry-run-sampling \
  --dump-sampling-report packages/lol_vod_analyzer/output/focused_sampling_report.json \
  --speed 2.0 \
  --game-start 90 \
  --no-open
```

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
- Windows なら `winget install Gyan.FFmpeg` または `choco install ffmpeg`
- `ffprobe` も通常は同梱される。`uv run lol-tools doctor` で両方確認する
- セットアップ後に `uv run lol-tools doctor` で再確認する

### Windows で `uv sync` や `uv run` が Python の DLL 読み込みで失敗する

- `uv` 管理 Python ではなく、通常インストール版 Python 3.12 を `uv sync -p "<python.exe>" --refresh` で明示する
- `py.exe -0p` と `py.exe -3.12 -c "import unicodedata"` で使う Python を確認する
- キャッシュや権限の切り分けには `--no-cache` を付ける
- Windows で文字化けや文字コード周りが怪しいときは、必要に応じて `$env:PYTHONUTF8='1'` を付けてコマンドを再実行する

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
- 自分のリプレイ動画分析: `replay analyze <動画パス>`
- 動画分析: `vod analyze`
- 解説動画分析: `vod analyze <YouTube URL> --mode commentary`
- プレイ動画分析: `vod analyze <動画パス> --mode gameplay`
- 試合データ付きリプレイ分析: `vod analyze <動画パス> --mode gameplay --match-data <json>` 。
  自分の試合録画を対象にした標準フロー
- 他人のリプレイ動画分析: `vod analyze <YouTube URL or 動画パス> --mode gameplay` 。
  試合データと紐付けにくいため実験的機能

`commentary` は YouTube 向け、ローカル動画は `gameplay` 向けという境界で使い分ける。

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
