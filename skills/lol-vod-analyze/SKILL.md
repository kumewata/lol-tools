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
- ローカル動画ファイルも入力できる
- `--match-data` を使うと `lol-review` の試合データと結合できる

## 手順

1. 入力ソースを確認する
   - YouTube URL
   - ローカル動画ファイルパス
2. 分析モードを判断する
   - **commentary** — 解説・コーチング動画向け（字幕テキスト重視）
   - **gameplay** — プレイ動画向け（画像重視）
   - モード指定がない場合、CLI 側で自動判定またはデフォルトに任せてよい
3. 必要なら試合データ連携の有無を確認する
   - 明示的な `findings.json` があればそれを使う
   - 直前に `lol-tools review` を実行している場合は `packages/lol_review/output/latest_findings.json` を候補にしてよい
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
   試合データを結合する場合:
   ```bash
   uv run lol-tools vod analyze /path/to/video.mp4 --mode gameplay --match-data packages/lol_review/output/latest_findings.json --no-open
   ```
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

## トラブルシューティング

- **字幕が取得できない場合** — YouTube 字幕が無い可能性がある。`--download --mode gameplay` かローカル動画分析に切り替える
- **GOOGLE_API_KEY エラー** — まずルートの `.env` に API キーが設定されているか確認
- **match-data エラー** — JSON パスが存在するか、`packages/lol_review/output/latest_findings.json` を使えるか確認
- **yt-dlp エラー** — `uv pip install --upgrade yt-dlp` で更新を試す
