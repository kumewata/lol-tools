---
title: "ADR-002: Riot API クライアント設計"
status: accepted
date: 2026-03-29
tags: [lol_review, API, 非同期処理]
---

# ADR-002: Riot API クライアント設計（async httpx）

## ステータス

Accepted

## コンテキスト

Riot API から試合データを取得するクライアントを設計する必要があった。取得するデータは以下の通り:

1. サモナー名 → PUUID の解決
2. PUUID → 試合 ID リスト
3. 試合 ID → 試合詳細データ
4. 試合 ID → タイムラインデータ

複数試合のデータを順次取得するため、I/O 待ちが多い処理となる。

## 決定

**`httpx.AsyncClient` を使った非同期クライアント (`RiotClient`) を実装する。**

主な設計:

- 全 HTTP リクエストを `_request()` メソッドに集約し、API キーヘッダーの付与とエラーハンドリングを統一
- `parse_match_summary()` / `parse_timeline()` でレスポンス JSON を Pydantic モデルに変換
- Data Dragon API からアイテム名・分類を取得し、ビルドタイミングの分析に利用

## 理由

- **非同期 I/O**: 試合データの逐次取得で発生する I/O 待ちを効率化。`httpx` は `requests` と同等の API で非同期をネイティブサポート
- **`_request()` 集約**: API キーの付与、レート制限、エラーハンドリングを一箇所に集約。テスト時は `_request()` をモックするだけで全 API 呼び出しを制御可能
- **Pydantic パーサー分離**: API レスポンスの JSON 構造と内部モデルの変換ロジックを `parse_*` メソッドに分離。Riot API のレスポンス形式が変わっても影響範囲を限定

## 影響

- CLI（Click）から非同期関数を呼び出すために `asyncio.run()` が必要
- テストでは `_request()` のモックにより、実 API 呼び出しなしで全フローを検証可能
- Riot API のレート制限（20 req / 1s）への対応は現時点では未実装。大量取得時にはスリープ等の追加が必要
