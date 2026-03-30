---
title: "ADR-005: 試合データ連携による動画分析精度向上"
status: accepted
date: 2026-03-29
tags: [lol_vod_analyzer, lol_review, データ連携]
---

# ADR-005: 試合データ連携による動画分析精度向上

## ステータス

Accepted

## コンテキスト

Gameplay モードでスクリーンショットのみから LLM で分析を行うと、以下の問題が発生した:

- 360p の画像ではチャンピオン名の誤判定率が 50% 以上
- ロール（Top/Jungle/Mid/ADC/Support）の誤認
- アイテム名のハルシネーション（存在しないアイテムを生成）
- キル/アシスト等のイベントの見落とし

画像認識の精度限界を補うために、Riot API から取得した試合データを分析に注入する方針を検討した。

## 決定

**`lol_review` が出力する `latest_findings.json` を `--match-data` オプションで `lol_vod_analyzer` に渡し、ゲームタイムラインのコンテキストをプロンプトに注入する。**

データフロー:

```
Riot API → lol_review → latest_findings.json
                              ↓ --match-data
動画 → lol_vod_analyzer → vod_analysis_*.html
```

注入される情報:

- 参加チャンピオンとロール（10人分）
- アイテム購入タイムライン
- スキルレベルアップ順序
- 対戦相手のレベル推移

## 理由

- **画像分析の限界**: 低解像度スクリーンショットからのチャンピオン・アイテム認識は信頼性が低い。構造化された試合データを与えることで LLM は「何が映っているか」ではなく「なぜそうしたか」の分析に集中できる
- **精度向上の実績**: match-data 注入により、ロール誤認とアイテムハルシネーションがほぼ解消された
- **疎結合**: `lol_review` と `lol_vod_analyzer` は JSON ファイルを介した疎結合。直接の import 依存はない

## 影響

- 動画分析の前に `lol_review report` を実行して JSON を生成する手順が必要
- 画像のみの分析（`--match-data` なし）は参考程度の精度。ドキュメントで match-data 連携を前提とする旨を明記
- 将来的には match ID の自動連携（1コマンドで試合データ取得 → 録画 → 分析）を目指す
