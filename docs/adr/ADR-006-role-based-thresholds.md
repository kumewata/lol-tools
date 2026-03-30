---
title: "ADR-006: ロール別閾値による改善点検出"
status: accepted
date: 2026-03-29
tags: [lol_review, 分析ロジック, アドバイザー]
---

# ADR-006: ロール別閾値による改善点検出

## ステータス

Accepted

## コンテキスト

試合データから改善点を検出する `advisor.py` では、CS（クリープスコア）、Kill Participation、Vision Score 等の指標を閾値と比較して `Finding` を生成する。

当初は全ロール共通の閾値を使用していたが、LoL ではロールによって期待値が大きく異なる:

- Support は CS をほとんど取らないが、Kill Participation は高い
- Jungle は CS/min が Solo Lane より低いが、Kill Participation は高い
- ADC/Mid/Top は CS/min が高いが、Kill Participation はロールによる

## 決定

**ロール（TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY）ごとに異なる閾値を定義し、ロール別に改善点を検出する。**

主な閾値設計:

| 指標 | SUP | JG | TOP/MID/ADC |
|------|-----|-----|-------------|
| CS/min | チェック対象外 | 5.0 | 6.0〜7.0 |
| Kill Participation | 50%+ | 40%+ | — |
| Vision Score/min | 1.2 | 0.8 | 0.5 |

## 理由

- **分析精度**: 共通閾値では Support に対して「CS が低い」という無意味な Finding が生成されていた。ロール別閾値により、各ロールにとって実際に意味のある改善点のみを検出
- **段階的な severity**: 閾値を超えた程度に応じて `info` / `warning` / `critical` の重要度を設定。例えば CS/min が 5.0 未満は warning、4.0 未満は critical
- **拡張性**: 閾値は `advisor.py` 内の関数パラメータとして管理。将来的にランク帯別の閾値や設定ファイル化も可能

## 影響

- Riot API の `teamPosition` フィールドへの依存。ポジションが空の場合は汎用閾値にフォールバック
- 閾値の妥当性はプレイヤーのランク帯に依存する。現在はゴールド〜プラチナ帯を想定した値
- `/lol-advice` スキルからの参照時にも同じ閾値体系が使われる
