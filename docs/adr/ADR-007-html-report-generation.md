---
title: "ADR-007: HTML レポート生成"
status: accepted
date: 2026-03-29
tags: [lol_review, lol_vod_analyzer, レポート, Jinja2]
---

# ADR-007: HTML レポート生成（Jinja2）

## ステータス

Accepted

## コンテキスト

分析結果をユーザーが閲覧するためのレポート形式を決定する必要があった。選択肢として:

1. ターミナル出力（Rich 等）
2. JSON ファイル
3. HTML レポート
4. Web アプリケーション（Flask/FastAPI 等）

## 決定

**Jinja2 テンプレートを使い、スタンドアロンの HTML ファイルとしてレポートを生成する。** 両プロジェクトで同じアプローチを採用。

- **lol_review**: `report.py` で試合統計・チャンピオン分析・改善点を HTML テーブルとチャートで表示。同時に `latest_findings.json` を出力
- **lol_vod_analyzer**: `report.py` でトピック・キーモーメント・スクリーンショットタイムラインを HTML で表示。スクリーンショットは base64 データ URI として埋め込み

出力先は `output/` ディレクトリで、タイムスタンプ付きファイル名。

## 理由

- **ゼロ依存の閲覧**: HTML ファイルはブラウザだけで閲覧可能。サーバー不要、インストール不要
- **リッチな表現**: テーブル、色分け、画像埋め込み、チャートなど、ターミナル出力では難しい表現が可能
- **ポータビリティ**: 画像を base64 で埋め込むことで、単一 HTML ファイルで完結。共有やアーカイブが容易
- **JSON 併用**: `lol_review` は HTML に加えて JSON を出力。これにより `lol_vod_analyzer` との連携（ADR-005）や `/lol-advice` スキルからの機械的な参照が可能

## 影響

- Jinja2 テンプレートの HTML/CSS が `report.py` 内に文字列として埋め込まれている。テンプレートが大きくなった場合は外部ファイル化を検討
- base64 画像埋め込みにより、スクリーンショットが多い場合にファイルサイズが大きくなる
- `--no-open` オプションで自動ブラウザ起動を抑制可能（CI/スクリプト用途）
- `_sanitize_for_json()` で Infinity/NaN 値を処理し、JSON 出力の安全性を確保
