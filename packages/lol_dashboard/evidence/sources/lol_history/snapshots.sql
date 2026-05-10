SELECT
    snapshot_id,
    summoner,
    puuid,
    strptime(generated_at, '%Y%m%d_%H%M%S') AS generated_at,
    total_games,
    wins,
    losses,
    win_rate,
    avg_kda,
    avg_cs_per_min
FROM snapshots
