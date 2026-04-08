---
name: lol-vod-analyze
description: LoL の解説動画やプレイ動画を分析し、学習レポートを生成する。YouTube の URL を渡されたとき、LoL の動画分析・VOD レビュー・コーチング動画の要約を頼まれたとき、「この動画から学びたい」「プロの動画を分析して」といった依頼があったときに使う。
---

# /lol-vod-analyze - LoL 動画分析レポート生成

LoL の解説動画・コーチング動画・プレイ動画を AI で分析し、構造化されたHTMLレポートを生成する。

## 前提

- ツールは `packages/lol_vod_analyzer/` にある
- 通常はルートの `.env` に `GOOGLE_API_KEY` が設定済みであること
- YouTube 動画は字幕（自動生成含む）とストーリーボード画像、またはダウンロードした動画から分析する
- ローカル動画ファイルも入力できる（gameplay モードのみ）
- `--match-data` を使うと `lol-review` の試合データと結合できる
- `--adaptive` で動きの多い場面のスクリーンショット密度を自動調整できる
- `--sampling-strategy focused` を使うと、match-data を元に重要局面へ screenshot 予算を寄せられる
- `--dry-run-sampling` と `--dump-sampling-report` で screenshot 配分だけ先に検証できる
- `--speed` でリプレイの再生速度を指定し、タイムスタンプを正規化できる（例: 2倍速なら `--speed 2.0`）
- `--game-start` で動画上の試合開始時刻（秒）を指定し、match-data のタイムスタンプとのずれを補正できる
- 長尺 VOD の標準フローは `docs/long-vod-workflow.md` にまとまっている

## 手順

1. 入力ソースを確認する
   - YouTube URL
   - ローカル動画ファイルパス
   - 長尺ローカル動画なら、まず proxy を作るかどうか判断する
2. 分析モードを判断する
   - **commentary** — 解説・コーチング動画向け（YouTube 字幕テキスト重視）
   - **gameplay** — プレイ動画向け（画像重視）
   - ローカル動画は `gameplay` のみ対応
3. 必要なら試合データ連携の有無を確認する
   - `vod analyze --match-data` に渡す JSON は単一試合である必要がある
   - 直前の `latest_findings.json` をそのまま使うのではなく、必要なら `lol-tools export-match-data --match-index <N>` を挟む
   - dry-run や sampling 比較が不要なら `lol-tools replay analyze` が最短導線
4. ソースに応じて以下のいずれかを実行する
   YouTube:
   ```bash
   uv run lol-tools vod analyze '<YouTube URL>' --mode <mode> --no-open
   ```
   YouTube をダウンロードして gameplay 分析:
   ```bash
   uv run lol-tools vod analyze '<YouTube URL>' --download --mode gameplay --no-open
   ```
   ローカル動画:
   ```bash
   uv run lol-tools vod analyze /path/to/video.mp4 --mode gameplay --interval 5 --no-open
   ```
   単一試合の match-data を結合する場合:
   ```bash
   uv run lol-tools vod analyze /path/to/video.mp4 --mode gameplay --match-data packages/lol_review/output/match_data_index2.json --no-open
   ```
   倍速リプレイ + 試合開始オフセット付きの場合:
   ```bash
   uv run lol-tools vod analyze /path/to/replay.mov --mode gameplay --match-data match.json --speed 2.0 --game-start 90 --no-open
   ```
   長尺 VOD で focused の dry-run を見る場合:
   ```bash
   uv run lol-tools vod analyze /path/to/replay.proxy.mp4 --mode gameplay --match-data match.json --sampling-strategy focused --focus-profile balanced --focus-window-seconds 45 --focus-budget-ratio 0.75 --global-backfill 4 --max-screenshots 24 --dry-run-sampling --dump-sampling-report packages/lol_vod_analyzer/output/focused_sampling_report.json --no-open
   ```
   fixed と focused を比較したい場合は `docs/long-vod-workflow.md` の手順に沿って、dry-run と本実行をそれぞれ 1 回ずつ回す
5. 生成されたHTMLレポートのパスを読み取り、内容を要約する

## 出力の読み方

レポートは `packages/lol_vod_analyzer/output/vod_analysis_YYYYMMDD_HHMMSS.html` に保存される。

HTMLの中に以下のセクションがある:

- **Summary** — 動画全体の要約
- **Key Moments** — タイムスタンプ付きの重要場面一覧（YouTube リンク付き）
- **Topics** — トピック別の整理（ルーン、コンボ、立ち回り等）
- **Actionable Tips** — すぐに実践できるアドバイス

## ユーザーへの伝え方

レポート生成後、以下の構成で要約を伝える:

### 動画概要
- タイトルまたはファイル名、再生時間、分析モード
- `match-data` を併用した場合は対象チャンピオン/ロールも添える

### 学べるポイント（Topics のまとめ）
- 各トピックの要点を箇条書きで簡潔に
- 特に重要なタイムスタンプは YouTube リンク付きで提示

### 今すぐ実践できること（Actionable Tips）
- Tips をそのまま伝える

### 注目シーン
- Key Moments から特に重要な 3-5 件をピックアップ
- YouTube の場合はタイムスタンプリンクを付ける
- ローカル動画の場合は時刻だけを示す

最後にHTMLレポートのパスを伝え、必要なら `--match-data` 付きで再分析できることも案内する。

## lol-advice との連携

ユーザーが自分の試合データと照らし合わせたい場合は、`/lol-advice` で最新の試合分析を出し、動画の教えと自分のプレイの差分を議論できる。例えば:

- 動画「レベル3でガンクを狙う」→ 自分のデータで序盤のキル/デスタイミングを確認
- 動画「CSを意識」→ 自分の CS/min と比較

## オプション判断ガイド

| 状況 | 追加オプション |
|------|---------------|
| リプレイを2倍速で録画した | `--speed 2.0` |
| 動画の先頭がロード画面や待機時間で試合開始と一致しない | `--game-start <秒>` |
| 重要なシーンのスクリーンショットが足りない/多すぎる | `--adaptive` |
| 長尺 VOD で重要局面を優先したい | `--sampling-strategy focused` |
| focused の寄り方を変えたい | `--focus-profile balanced|lane|objective|roam` |
| focused window を広げたい / 狭めたい | `--focus-window-seconds <秒>` |
| focus への配分を増減したい | `--focus-budget-ratio <0.0-1.0>` |
| 全体文脈用の backfill を増減したい | `--global-backfill <件数>` |
| 本実行前に screenshot 配分だけ見たい | `--dry-run-sampling --dump-sampling-report <path>` |
| YouTube 動画の字幕がなく画像分析したい | `--download --mode gameplay` |
| `--speed` と `--game-start` は併用可能。`--speed` は動画全体のタイムスケール補正、`--game-start` は開始位置のオフセット補正 | |

## トラブルシューティング

- **字幕が取得できない場合** — YouTube 字幕が無い可能性がある。`--download --mode gameplay` かローカル動画分析に切り替える
- **GOOGLE_API_KEY エラー** — まずルートの `.env` に API キーが設定されているか確認
- **ローカル commentary を使いたい場合** — 現状は非対応。YouTube URL を直接渡して字幕分析を使う
- **match-data エラー** — JSON パスが存在するか確認し、複数試合入りの `latest_findings.json` をそのまま渡していないか確認する。必要なら `lol-tools export-match-data --match-index <N>` を使う
- **長尺 VOD のコストが重い** — proxy 動画を作り、先に `--dry-run-sampling` で allocation だけ確認する
- **yt-dlp エラー** — `uv pip install --upgrade yt-dlp` で更新を試す
