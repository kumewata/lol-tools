---
title: "ADR-004: yt-dlp による YouTube 連携"
status: accepted
date: 2026-03-29
tags: [lol_vod_analyzer, YouTube, yt-dlp]
---

# ADR-004: yt-dlp による YouTube 連携

## ステータス

Accepted

## コンテキスト

YouTube 上の LoL 解説動画から字幕・メタデータ・ストーリーボード画像を取得し、さらに動画そのものをダウンロードしてローカル分析する機能が必要だった。

## 決定

**`yt-dlp` ライブラリを使い、YouTube 動画の字幕取得・メタデータ取得・動画ダウンロード・ストーリーボード抽出を行う。**

`fetcher.py` に以下の機能を実装:

- `fetch_video_metadata()` — 動画タイトル・チャンネル・長さ等
- `fetch_transcript()` — 日本語自動字幕の取得と `TranscriptSegment` への変換
- `download_video()` — 360p MP4 のダウンロード
- `download_storyboard_sprites()` — ストーリーボードタイル画像の取得・分割

## 理由

- **安定性**: `yt-dlp` は YouTube の仕様変更に追随するコミュニティ主導のライブラリで、字幕・ストーリーボード・動画ダウンロードを統一的に扱える
- **字幕フォーマット**: YouTube の `json3` 形式の字幕を `parse_caption_events()` でパースし、タイムスタンプ付きセグメントに変換
- **SABR 問題への対応**: YouTube の新しい SABR プロトコルにより通常のダウンロードが失敗する問題があった。`android` クライアントを指定（`extractor_args: {'youtube': {'client': ['android']}}`）することで 360p の取得に成功。ただし PO Token 不要の代わり 360p 制限がある

## 影響

- YouTube の字幕取得は 429（レート制限）エラーが発生することがあり、リトライ処理が必要
- `--download` オプションで YouTube → ローカル → 分析のパイプラインが可能だが、360p 制限のため画像分析の精度は低い
- `ffmpeg` がシステムにインストールされている前提（音声抽出・動画処理に必要）
