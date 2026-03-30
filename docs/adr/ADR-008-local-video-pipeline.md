---
title: "ADR-008: ローカル動画処理パイプライン"
status: accepted
date: 2026-03-29
tags: [lol_vod_analyzer, 動画処理, ffmpeg, OpenCV]
---

# ADR-008: ローカル動画処理パイプライン

## ステータス

Accepted

## コンテキスト

YouTube 動画の字幕分析（Commentary モード）に加え、ローカルに保存したリプレイ動画や画面録画を直接分析する機能が必要だった。LoL のリプレイファイル（`.rofl`）は暗号化されたパケットデータであり、直接動画として処理できないため、画面録画した動画ファイル（`.mov`, `.mp4` 等）を入力とする。

ただし、Gameplay モードの分析精度は入力動画の出所に依存する。自分の試合録画は Riot API から取得した試合データと紐付けやすく、`--match-data` によってイベントやビルド文脈を補完できる。一方で、他の人が YouTube などにアップロードしたリプレイ動画は試合データとの紐付けが難しく、映像からの推定に依存するため分析精度が下がる。

## 決定

**ffmpeg + OpenCV + Gemini API の3段階パイプラインでローカル動画を処理する。**

このうち、**自分の試合録画を対象にした Gameplay 分析を標準機能**とし、**他人のリプレイ動画に対する Gameplay 分析は実験的機能**として位置付ける。

```
動画ファイル
  ├── ffmpeg → 音声抽出（m4a）→ Gemini 文字起こし → Commentary 分析
  └── OpenCV → スクリーンショット抽出（N秒間隔）→ Gameplay 分析
```

`local_video.py` に以下を実装:

- `get_video_metadata()` — ffprobe でメタデータ取得
- `extract_audio()` — ffmpeg で m4a 音声抽出
- `transcribe_audio()` — Gemini API で音声文字起こし
- `extract_screenshots()` — OpenCV で定期的にフレーム抽出

モード自動判定: 字幕セグメントが 10 未満の場合は Gameplay モードに自動切替。

## 理由

- **ffmpeg**: 音声抽出のデファクトスタンダード。m4a（AAC）形式で Gemini API に直接入力可能
- **OpenCV**: フレーム抽出に特化した軽量な選択。Pillow での保存と組み合わせ、JPEG 品質を制御可能
- **Gemini 文字起こし**: Whisper 等の別サービスを追加せず、既に利用している Gemini API で音声文字起こしも処理。依存を最小化
- **モード自動判定**: 解説音声がない動画（リプレイ録画）を手動でモード指定する手間を削減。`--interval` オプションでスクリーンショット間隔もカスタマイズ可能

## 影響

- システムに `ffmpeg` と `ffprobe` が必要（Homebrew 等でインストール）
- OpenCV（`opencv-python`）は依存が重い（numpy 含む）。バイナリサイズに影響
- `--download` オプションで YouTube → ローカル → 分析のワンストップパイプラインも実現
- 一時ファイル（音声、スクリーンショット）は `tempfile` で管理し、分析後に自動削除
- Gameplay モードの期待精度は入力ソースに差があるため、README や CLI では標準フローと実験的フローを分けて案内する必要がある
