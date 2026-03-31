---
title: Architecture Decision Records
tags: [ADR, アーキテクチャ, インデックス]
---

# Architecture Decision Records (ADR)

このディレクトリには、lol-tools リポジトリにおける主要なアーキテクチャ上の意思決定を記録した ADR を格納する。

## インデックス

| ADR | タイトル | 対象 | ステータス |
|-----|---------|------|-----------|
| [ADR-001](ADR-001-monorepo-structure.md) | モノレポ構成 | 全体 | Accepted |
| [ADR-002](ADR-002-riot-api-client.md) | Riot API クライアント設計（async httpx） | lol_review | Accepted |
| [ADR-003](ADR-003-gemini-video-analysis.md) | Gemini API による動画分析 | lol_vod_analyzer | Accepted |
| [ADR-004](ADR-004-youtube-integration.md) | yt-dlp による YouTube 連携 | lol_vod_analyzer | Accepted |
| [ADR-005](ADR-005-match-data-integration.md) | 試合データ連携による動画分析精度向上 | 全体 | Accepted |
| [ADR-006](ADR-006-role-based-thresholds.md) | ロール別閾値による改善点検出 | lol_review | Accepted |
| [ADR-007](ADR-007-html-report-generation.md) | HTML レポート生成（Jinja2） | 全体 | Accepted |
| [ADR-008](ADR-008-local-video-pipeline.md) | ローカル動画処理パイプライン | lol_vod_analyzer | Accepted |
| [ADR-009](ADR-009-first-run-onboarding.md) | 初回ユーザー導線の統一 | 全体 | Accepted |
| [ADR-010](ADR-010-jungle-event-position-context.md) | ジャングルイベントと位置情報の match-data 拡張 | 全体 | Accepted |
| [ADR-011](ADR-011-single-match-data-for-vod-analysis.md) | 動画分析の match-data を単一試合 JSON に限定する | 全体 | Accepted |
