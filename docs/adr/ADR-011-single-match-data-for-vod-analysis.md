---
title: "ADR-011: 動画分析の match-data を単一試合 JSON に限定する"
status: accepted
date: 2026-03-31
tags: [lol_vod_analyzer, lol_review, CLI, match-data]
---

# ADR-011: 動画分析の match-data を単一試合 JSON に限定する

## ステータス

Accepted

## コンテキスト

`ADR-005` で `lol_review` の出力を `lol_vod_analyzer` に渡す方針を採用し、`ADR-010` でジャングルイベントと位置情報まで match-data に拡張した。しかし、その入力として使っていた `lol_review` の `latest_findings.json` は、本来は複数試合をまとめたレビュー成果物である。

この設計のまま `vod analyze --match-data` に `latest_findings.json` を直接渡すと、以下の問題が起きた。

- 動画に対応する試合を 1 件に特定していなくても、先頭試合が暗黙に選ばれる
- 動画と別試合のロールやイベントが流れ込み、分析結果が大きくぶれる
- `vod analyze` の責務が「単一動画の分析」なのに、入力フォーマットだけ複数試合レビューに依存している
- `replay analyze` では内部的に `match-index` で 1 試合へ絞っていた一方、`vod analyze` 直呼びでは同じ前提が守られない

実際に、複数試合を含む JSON を `vod analyze --match-data` に渡した際、動画はジャングル視点なのに `UTILITY` 試合が使われ、要約が BOT レーン前提へ崩れる事象が起きた。

## 決定

**`vod analyze --match-data` は単一試合だけを含む JSON を前提とし、複数試合入り JSON は受け付けない。単一試合 JSON は `lol-tools export-match-data` または `replay analyze --match-index` で生成する。**

具体的には、以下を採用する。

- `lol_vod_analyzer` の `match-data` 読み込みは `matches` が 1 件であることを必須にする
- `player_stats` も 1 試合分だけであることを必須にする
- 条件を満たさない場合、警告ではなくエラーで停止する
- root CLI に `lol-tools export-match-data --match-index <N>` を追加し、`lol_review` の findings から単一試合 JSON を明示的に出力できるようにする
- `examples` などの案内文は、`latest_findings.json` 直指定ではなく、export 後の `match_data_*.json` を使う形へ更新する

データフロー:

```text
Riot API
  → lol_review
  → latest_findings.json (複数試合レビュー成果物)
  → lol-tools export-match-data --match-index N
  → match_data_*.json (単一試合)
  → lol_vod_analyzer --match-data
  → vod_analysis_*.html
```

`replay analyze` は従来どおり、内部で 1 試合に絞った JSON を作って `vod analyze` に渡す。

## 理由

- **入力境界を明確にするため**: `vod analyze` が扱うのは単一動画であり、対応する match-data も単一試合であるべき
- **誤用を防ぐため**: 複数試合レビュー JSON をそのまま受けると、暗黙の `index 0` 選択で別試合の文脈が混ざる
- **CLI の責務を分離できるため**: `lol_review` はレビュー成果物生成、`export-match-data` は単一試合抽出、`vod analyze` は単一動画分析に責務を分けられる
- **既存の replay analyze と整合するため**: `replay analyze` はすでに `match-index` で 1 試合へ絞る構造を持っており、その前提を CLI 全体で統一できる
- **将来拡張しやすいため**: 1 試合専用フォーマットを前提にすれば、後で match ID 自動選択や動画との紐付け判定を追加しやすい

## 影響

- `vod analyze --match-data packages/lol_review/output/latest_findings.json` のような使い方はエラーになる
- 動画分析前に `export-match-data` を挟むか、`replay analyze --match-index` を使うのが正式な導線になる
- `lol_review` の `latest_findings.json` は「レビュー成果物」であり、動画分析の直接入力ではないことが明確になる
- CLI 利用者は 1 ステップ増えるが、その代わり動画と試合データの取り違えを防ぎやすくなる
- 将来的に `lol_review` 側でより専用の単一試合 export 形式へ発展させる余地ができる

