---
title: LoL 成長トレンド ダッシュボード
---

<!-- target_summoner: 'apililili#3197' -->

```sql latest_snapshot
SELECT
    snapshot_id,
    generated_at,
    total_games,
    wins,
    losses,
    ROUND(win_rate * 100, 1) AS win_rate_pct,
    ROUND(avg_kda, 2)        AS avg_kda,
    ROUND(avg_cs_per_min, 2) AS avg_cs_per_min
FROM lol_history.snapshots
WHERE summoner = 'apililili#3197'
ORDER BY snapshot_id DESC
LIMIT 1
```

```sql snapshot_count
SELECT COUNT(*) AS cnt FROM lol_history.snapshots WHERE summoner = 'apililili#3197'
```

## 最新スナップショット

<BigValue
  data={latest_snapshot}
  value="win_rate_pct"
  title="勝率 (%)"
/>

<BigValue
  data={latest_snapshot}
  value="avg_kda"
  title="平均 KDA"
/>

<BigValue
  data={latest_snapshot}
  value="avg_cs_per_min"
  title="CS/min"
/>

<BigValue
  data={latest_snapshot}
  value="total_games"
  title="試合数"
/>

> 最終更新: {latest_snapshot[0].generated_at} — スナップショット累計 {snapshot_count[0].cnt} 件

## ページ一覧

- [基本指標トレンド](/basic-metrics) — 勝率・KDA・CS/min・KP・Vision の時系列
- [所見タイムライン](/findings) — 検出された課題の出現・解消
- [チャンピオン統計](/champions) — チャンピオン別 WR 推移とパッチ別比較
