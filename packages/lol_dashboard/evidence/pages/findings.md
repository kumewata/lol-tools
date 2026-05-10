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

```sql findings_per_snap
SELECT
    s.generated_at,
    f.severity,
    COUNT(*) AS findings_count
FROM lol_history.findings f
JOIN lol_history.snapshots s
  ON f.snapshot_id = s.snapshot_id
 AND f.summoner    = s.summoner
WHERE s.summoner = (SELECT summoner FROM lol_history.target_summoner)
GROUP BY s.generated_at, f.severity
ORDER BY s.generated_at
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

## 所見タイムライン（severity 別件数）

各スナップショットで検出された所見の数を severity 別に積み上げて時系列表示する。
critical（赤）が増えていないか、warning（橙）が解消されているかを観察できる。

<BarChart
  data={findings_per_snap}
  x="generated_at"
  y="findings_count"
  series="severity"
  type="stacked"
  seriesColors={{"critical": "#ef4444", "warning": "#f59e0b", "info": "#3b82f6"}}
  yAxisTitle="件数"
  xAxisTitle="スナップショット"
/>

## 所見一覧（時系列）

スナップショットごとの個別所見。`category` / `severity` / `message` を確認できる。

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
