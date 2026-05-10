---
title: チャンピオン統計
---

<!-- target_summoner: 'apililili#3197' -->

<Dropdown name=queue_filter defaultValue="ranked" title="キュー種別">
  <DropdownOption value="ranked" valueLabel="ランクのみ"/>
  <DropdownOption value="normal" valueLabel="ノーマルのみ"/>
  <DropdownOption value="all"    valueLabel="全部"/>
</Dropdown>

```sql champ_wr
SELECT
    s.generated_at,
    m.champion,
    COUNT(*) AS games,
    ROUND(AVG(CASE WHEN m.win THEN 1.0 ELSE 0.0 END) * 100, 1) AS win_rate_pct
FROM lol_history.matches m
JOIN lol_history.snapshots s
  ON m.snapshot_id = s.snapshot_id
 AND m.summoner    = s.summoner
WHERE s.summoner = 'apililili#3197'
  AND (
      ('${inputs.queue_filter.value}' = 'ranked' AND m.is_ranked = TRUE)
   OR ('${inputs.queue_filter.value}' = 'normal' AND m.queue_category IN ('normal_draft','normal_blind'))
   OR ('${inputs.queue_filter.value}' = 'all')
  )
GROUP BY s.generated_at, m.champion
HAVING COUNT(*) >= 2
ORDER BY s.generated_at, win_rate_pct DESC
```

```sql pick_freq
SELECT
    m.champion,
    COUNT(*) AS games
FROM lol_history.matches m
WHERE m.summoner = 'apililili#3197'
  AND (
      ('${inputs.queue_filter.value}' = 'ranked' AND m.is_ranked = TRUE)
   OR ('${inputs.queue_filter.value}' = 'normal' AND m.queue_category IN ('normal_draft','normal_blind'))
   OR ('${inputs.queue_filter.value}' = 'all')
  )
GROUP BY m.champion
ORDER BY games DESC
LIMIT 15
```

```sql patch_wr
SELECT
    m.patch,
    m.champion,
    COUNT(*) AS games,
    ROUND(AVG(CASE WHEN m.win THEN 1.0 ELSE 0.0 END) * 100, 1) AS win_rate_pct
FROM lol_history.matches m
WHERE m.summoner = 'apililili#3197'
  AND m.patch IS NOT NULL
  AND m.is_ranked = TRUE
GROUP BY m.patch, m.champion
HAVING COUNT(*) >= 2
ORDER BY m.patch DESC, win_rate_pct DESC
```

## WR 推移（直近スナップショット × チャンピオン）

<LineChart
  data={champ_wr}
  x="generated_at"
  y="win_rate_pct"
  series="champion"
  yAxisTitle="勝率 (%)"
/>

## ピック頻度

<BarChart
  data={pick_freq}
  x="champion"
  y="games"
  swapXY=true
/>

## パッチ別 WR（ランク戦・2試合以上）

<DataTable data={patch_wr} />
