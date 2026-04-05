---
title: "ADR-015: 長尺 VOD 向け focused sampling と dry-run 検証基盤"
status: accepted
date: 2026-04-05
tags: [lol_vod_analyzer, focused-sampling, long-vod, dry-run, sampling-report]
---

# ADR-015: 長尺 VOD 向け focused sampling と dry-run 検証基盤

## ステータス

Accepted

## コンテキスト

`lol_vod_analyzer` には既に固定間隔抽出と `--adaptive` が存在していたが、長尺の gameplay VOD に対しては次の問題が残っていた。

1. `max_screenshots` が固定上限のため、重要場面が多い試合でも全編へ薄くスクリーンショットが配られやすい
2. `--adaptive` は動画全体の scene activity scan を追加で行うため、長いローカル動画では初回コストが重い
3. 重要場面に実際に何枚のスクリーンショットが割り当たったかが観測しづらく、改善の当たり外れを低コストで検証できない

実測でも、通常の `VOD + match-data` は `2:00` や `3:14` のような序盤レーン戦の連続性を追いやすい一方、後半のドラゴン、タワー、終盤 push の取りこぼしが起こりやすかった。逆に focused な配分を行うと、`6:38` のデス、`8:58` / `20:22` のドラゴン、`23:00` 付近の集団戦のような重要局面は強くなるが、レーン開始直後の連続性は薄くなりやすかった。

このため、長尺 VOD では「動画全体を均等に見る」より「`match-data` から重要区間を先に作り、そこへ予算を寄せる」仕組みが必要だった。

## 決定

### focused sampling を新しい選定戦略として追加する

`fixed` / `adaptive` を維持したまま、`focused` を新しい screenshot sampling strategy として追加する。

- `match-data` から `death` / `kill` / `assist` / `objective` / `level spike` / `momentum` の focus window を生成する
- `max_screenshots` を `focus_budget` と `backfill_budget` に分割する
- focus window には最低枚数を保証し、残りは priority と window 長に基づいて配分する
- 全体文脈維持のため `global_backfill` を明示的に残す

### 最初の主成果物を sampling report と dry-run に置く

長尺 VOD の改善は HTML の品質だけ見ても原因切り分けが難しいため、まず screenshot allocation を JSON で観測可能にする。

- `--dry-run-sampling`
- `--dump-sampling-report`
- `--sampling-strategy focused`

を追加し、スクリーンショット抽出と LLM 分析を実行せずに配分結果だけを検証できるようにする。

### focused の圧縮ルールを入れる

長尺検証で分かった偏りに対して、focused window には追加の圧縮ルールを入れる。

- 近接する `objective` window は追加マージする
- 長すぎる `momentum` window には最大長を設ける
- これにより、近いイベント群への過配分と、広すぎる window への低密度配分を抑える

### LLM 応答の部分破損は無効項目だけ捨てて継続する

focused 検証では、LLM が `timestamp_ms: "不明"` のような壊れた key moment を返すことがあった。これで全体分析を落とすのではなく、無効な key moment だけスキップして HTML 生成を継続する。

## 理由

- `focused` は `match-data` の強みをそのまま screenshot 配分に使えるため、長尺で重要局面を落としにくい
- `adaptive` は動画全体走査を伴うため、長尺ローカル動画では初回コスト削減の主手段になりにくい
- dry-run と sampling report があれば、LLM 品質ではなく allocation 自体を安価に検証できる
- 近接 `objective` のマージと `momentum` の圧縮で、旧 focused より前半文脈を戻しつつ、後半の重要局面も維持できた
- parser を堅くしておくことで、長時間ジョブの最終段階で小さな JSON 破損により全体が失敗するリスクを減らせる

## 影響

### 良い影響

- 長尺 VOD に対して、`match-data` 主導の重点抽出が可能になった
- screenshot 配分を dry-run で可視化でき、改善サイクルが速くなった
- 近接 objective と長い momentum の偏りを抑え、旧 focused より前半の文脈を回復できた
- LLM 応答の一部破損で全体レポート生成が止まりにくくなった

### 悪い影響 / 制約

- `focused` は通常 sampling の完全な代替ではなく、序盤レーンの連続性はなお弱くなりうる
- `match-data` の質や粒度に依存するため、不完全な試合データでは偏りも起きる
- focus rule は現在 1 系統であり、レビュー目的別の最適化はまだ入っていない

### フォローアップ

- issue [#22](https://github.com/kumewata/lol-tools/issues/22): `--focus-profile lane|balanced|objective|roam` のような用途別重点配分を追加する
- issue [#21](https://github.com/kumewata/lol-tools/issues/21): proxy 動画作成、`--speed 2.0`、dry-run、本実行、比較までの再現可能フローを docs / skill に落とす
