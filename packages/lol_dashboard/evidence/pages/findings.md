---
title: 所見タイムライン
---

<!-- target_summoner: 'apililili#3197' -->

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
WHERE s.summoner = 'apililili#3197'
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
WHERE s.summoner = 'apililili#3197'
GROUP BY f.category, f.severity
ORDER BY occurrences DESC
```

## 所見タイムライン

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
