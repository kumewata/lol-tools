---
title: 基本指標トレンド
---

<!-- target_summoner は .env の DEFAULT_RIOT_ID から自動生成された
     lol_history.target_summoner テーブルから取得する -->

<Dropdown name=queue_filter defaultValue="ranked" title="キュー種別">
  <DropdownOption value="ranked" valueLabel="ランクのみ"/>
  <DropdownOption value="normal" valueLabel="ノーマルのみ"/>
  <DropdownOption value="all"    valueLabel="全部"/>
</Dropdown>

```sql metrics
SELECT
    s.generated_at,
    ROUND(AVG(CASE WHEN m.win THEN 1.0 ELSE 0.0 END), 4)               AS win_rate_pct,
    ROUND(AVG((m.kills + m.assists) / GREATEST(m.deaths, 1)), 2)       AS avg_kda,
    ROUND(AVG(m.cs_per_min), 2)                                        AS avg_cs_per_min,
    ROUND(AVG(m.kill_participation), 4)                                AS avg_kp_pct,
    ROUND(AVG(m.vision_score * 60.0 / m.game_duration_seconds), 2)     AS avg_vision_per_min,
    COUNT(*)                                                           AS games
FROM lol_history.snapshots s
JOIN lol_history.matches m
  ON m.snapshot_id = s.snapshot_id
 AND m.summoner    = s.summoner
WHERE s.summoner = (SELECT summoner FROM lol_history.target_summoner)
  AND (
      ('${inputs.queue_filter.value}' = 'ranked' AND m.is_ranked = TRUE)
   OR ('${inputs.queue_filter.value}' = 'normal' AND m.queue_category IN ('normal_draft','normal_blind'))
   OR ('${inputs.queue_filter.value}' = 'all')
  )
GROUP BY s.generated_at
ORDER BY s.generated_at
```

## 勝率

<LineChart
  data={metrics}
  x="generated_at"
  y="win_rate_pct"
  yFmt="pct1"
  yAxisTitle="勝率"
/>

## 平均 KDA

<LineChart
  data={metrics}
  x="generated_at"
  y="avg_kda"
  yAxisTitle="KDA"
/>

## CS/min

<LineChart
  data={metrics}
  x="generated_at"
  y="avg_cs_per_min"
  yAxisTitle="CS/min"
/>

## キル参加率

<LineChart
  data={metrics}
  x="generated_at"
  y="avg_kp_pct"
  yFmt="pct1"
  yAxisTitle="KP"
/>

## Vision / min

<LineChart
  data={metrics}
  x="generated_at"
  y="avg_vision_per_min"
  yAxisTitle="Vision/min"
/>

## データテーブル

<DataTable data={metrics} />
