---
name: lol-vod-analyze
description: LoL の解説動画やプレイ動画を分析し、学習レポートを生成する。YouTube の URL を渡されたとき、LoL の動画分析・VOD レビュー・コーチング動画の要約を頼まれたとき、「この動画から学びたい」「プロの動画を分析して」といった依頼があったときに使う。
---

# /lol-vod-analyze - LoL 動画分析レポート生成

YouTube 上の LoL 解説動画・コーチング動画・プレイ動画を AI で分析し、構造化されたHTMLレポートを生成する。

## 前提

- ツールは `packages/lol_vod_analyzer/` にある
- ルートの `.env` に `GOOGLE_API_KEY` が設定済みであること
- YouTube 動画の字幕（自動生成含む）とストーリーボード画像を取得して Gemini で分析する

## 手順

1. ユーザーから動画 URL を受け取る（YouTube URL）
2. 分析モードを確認する:
   - **commentary** — 解説・コーチング動画向け（字幕テキスト重視）。デフォルト
   - **gameplay** — プレイ動画向け（画像重視）
3. 以下のコマンドを実行:
   ```bash
   uv run lol-tools vod analyze '<YouTube URL>' --mode <mode> --no-open
   ```
4. 生成されたHTMLレポートのパスが出力されるので、その内容を読み込む
5. レポートの内容をユーザーに要約して伝える

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
- タイトル、再生時間、分析モード

### 学べるポイント（Topics のまとめ）
- 各トピックの要点を箇条書きで簡潔に
- 特に重要なタイムスタンプは YouTube リンク付きで提示

### 今すぐ実践できること（Actionable Tips）
- Tips をそのまま伝える

### 注目シーン
- Key Moments から特に重要な 5 つ程度をピックアップ
- 各シーンに YouTube タイムスタンプリンク付き

最後にHTMLレポートのパスを伝え、ブラウザで全体を確認できることを案内する。

## lol-advice との連携

ユーザーが自分の試合データと照らし合わせたい場合は、`/lol-advice` で最新の試合分析を出し、動画の教えと自分のプレイの差分を議論できる。例えば:

- 動画「レベル3でガンクを狙う」→ 自分のデータで序盤のキル/デスタイミングを確認
- 動画「CSを意識」→ 自分の CS/min と比較

## トラブルシューティング

- **字幕が取得できない場合** — 動画に自動字幕がない可能性がある。別の動画を試すか、手動字幕付きの動画を選ぶ
- **GOOGLE_API_KEY エラー** — ルートの `.env` に API キーが設定されているか確認
- **yt-dlp エラー** — `uv pip install --upgrade yt-dlp` で更新を試す
