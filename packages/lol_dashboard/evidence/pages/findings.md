---
title: 所見タイムライン
---

<!-- target_summoner は .env の DEFAULT_RIOT_ID から自動生成された
     lol_history.target_summoner テーブルから取得する -->

```sql findings_timeline
SELECT
    s.generated_at,
    f.category,
    f.severity,
    f.message,
    f.detail
FROM lol_history.findings f
JOIN lol_history.snapshots s
  ON f.snapshot_id = s.snapshot_id
 AND f.summoner    = s.summoner
WHERE s.summoner = (SELECT summoner FROM lol_history.target_summoner)
ORDER BY s.generated_at, f.severity
```

```sql findings_freq
SELECT
    f.category,
    f.severity,
    COUNT(*) AS occurrences
FROM lol_history.findings f
JOIN lol_history.snapshots s
  ON f.snapshot_id = s.snapshot_id
 AND f.summoner    = s.summoner
WHERE s.summoner = (SELECT summoner FROM lol_history.target_summoner)
GROUP BY f.category, f.severity
ORDER BY occurrences DESC
```

## 所見タイムライン（severity 別カラー）

各スナップショットでどの所見が出ていたかを散布図で可視化する。
y 軸はカテゴリ、点の色は severity（critical=赤 / warning=橙 / info=青）。

<ScatterPlot
  data={findings_timeline}
  x="generated_at"
  y="category"
  series="severity"
  seriesColors={{"critical": "#ef4444", "warning": "#f59e0b", "info": "#3b82f6"}}
  tooltipTitle="message"
  yAxisTitle="カテゴリ"
  xAxisTitle="スナップショット"
/>

## 所見一覧

<DataTable
  data={findings_timeline}
  rows=50
/>

## カテゴリ別出現頻度

<BarChart
  data={findings_freq}
  x="category"
  y="occurrences"
  series="severity"
  seriesColors={{"critical": "#ef4444", "warning": "#f59e0b", "info": "#3b82f6"}}
  swapXY=true
/>
