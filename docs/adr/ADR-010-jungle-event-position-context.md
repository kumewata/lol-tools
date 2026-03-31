---
title: "ADR-010: ジャングルイベントと位置情報の match-data 拡張"
status: accepted
date: 2026-03-31
tags: [lol_review, lol_vod_analyzer, timeline, match-data]
---

# ADR-010: ジャングルイベントと位置情報の match-data 拡張

## ステータス

Accepted

## コンテキスト

`ADR-005` で `lol_review` の `latest_findings.json` を `lol_vod_analyzer` に渡す方針を採用したことで、gameplay 分析の精度は大きく改善した。一方で、match-data に含めていた確定情報はキル、デス、アシスト、アイテム購入、スキルレベルアップ、対面レベル推移が中心で、ジャングルルートの復元に必要な情報は不足していた。

その結果、Gameplay モードのレポートでは以下の問題が残っていた。

- 画面やミニマップから一般化したジャングルルートを推測しやすい
- 試合固有の中立モンスター取得タイミングと動線がプロンプトに反映されない
- `lol_review` の JSON には `ELITE_MONSTER_KILL` とその `position` が存在していても、`lol_vod_analyzer` に伝搬していない
- participant frame の `position` と `jungleMinionsKilled` を保持していないため、通常キャンプを含む移動の根拠が弱い

今回は、ゲームプレイ分析で「画面から読み取れること」と「Riot API 由来の確定時系列」をより明確に分離し、ジャングルルートに関するハルシネーションを減らす必要があった。

## 決定

**`lol_review` の timeline 解析で位置情報と jungle CS 推移を保持し、`lol_vod_analyzer` の gameplay prompt に中立モンスター撃破イベントと位置スナップショットを確定データとして注入する。**

具体的には、以下を採用する。

- `PlayerStats` に `position_timeline` を追加する
- `PlayerStats` に `jungle_cs_timeline` を追加する
- 既存の `objective_events` を `--match-data` 経由で `match_context` に渡す
- gameplay 分析の `_build_chunk_timeline` で、以下を時系列イベントとして統合する
  - キル / デス / アシスト
  - アイテム購入
  - レベルアップ / スキルレベルアップ
  - `ELITE_MONSTER_KILL` / `BUILDING_KILL`
  - フレーム位置スナップショット

データフロー:

```text
Riot timeline
  → lol_review.parse_timeline
  → findings.json
    - objective_events
    - position_timeline
    - jungle_cs_timeline
  → lol_vod_analyzer --match-data
  → gameplay prompt の確定時系列
  → vod_analysis_*.html
```

表現ルール:

- 中立モンスター撃破は `monsterType` と `monsterSubType` を連結して表記する
- 座標は `座標=(x, y)` の形式で統一する
- 位置スナップショットには同時刻の `jungleCS` があれば併記する

## 理由

- **既存データを活かせる**: `objective_events` には既に `ELITE_MONSTER_KILL` と `position` が含まれていたため、新しい外部依存なしに精度を上げられる
- **確定情報と推測情報を分離できる**: LLM に中立モンスター撃破と位置情報を明示することで、画像からの過剰推測を抑えやすい
- **通常キャンプの補助線になる**: Riot timeline には通常キャンプの撃破イベントが十分に揃わないが、`position_timeline` と `jungle_cs_timeline` を組み合わせれば進行方向の根拠を補強できる
- **ADR-005 の方針を拡張する**: match-data 連携の価値を、チャンピオン誤認防止だけでなく時系列行動の復元にも広げられる
- **変更範囲を局所化できる**: HTML レポート構造や CLI 仕様を変えず、`lol_review` の timeline 抽出と `lol_vod_analyzer` の prompt 生成に変更を閉じ込められる

## 影響

- `findings.json` の `player_stats` に `position_timeline` と `jungle_cs_timeline` が追加される
- `lol_vod_analyzer` は `objective_events` を含む richer な `match_context` を扱う
- gameplay レポートでは、ジャングルルートやオブジェクト周辺の記述が Riot API の時系列に引っ張られるようになる
- 通常キャンプの完全な撃破順までは保証されず、依然として minute/frame 粒度の制約は残る
- 将来的にジャングルルート可視化 UI を追加する場合も、今回の時系列構造を再利用できる

