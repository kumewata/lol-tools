# 長尺 VOD の前処理からレポート作成までの標準フロー

長い LoL 動画をそのまま `vod analyze` や `replay analyze` に渡すと、実行時間とコストが重くなりやすい。実運用では、必要に応じて解析用 proxy 動画を作り、`match-data` と dry-run を組み合わせてから本実行するのが扱いやすい。

このドキュメントは、長尺 VOD を再現性のある手順で分析し、通常 sampling と focused sampling を比較するための標準フローをまとめたもの。

## このフローを使う場面

- 20 分超の gameplay VOD を分析したい
- 自分で録画した replay を `--speed 2.0` 付きで分析したい
- `match-data` を使って focused sampling を試したい
- screenshot 配分だけ先に dry-run で確認したい
- 通常 sampling と focused sampling の HTML レポートを比較したい

## 前提

- `ffmpeg` と `ffprobe` が使える
- gameplay 分析では `GOOGLE_API_KEY` が設定済み
- `match-data` を使う場合は Riot API が使える
- `vod analyze --match-data` に渡す JSON は単一試合である

導入確認:

```bash
uv run lol-tools doctor
ffprobe -version
```

## 全体の流れ

1. 元動画の長さ、解像度、fps を確認する
2. 必要なら軽量な proxy 動画を作る
3. `review` または `export-match-data` で単一試合の `match-data` を用意する
4. `--speed` と `--game-start` を決める
5. `--dry-run-sampling` と `--dump-sampling-report` で screenshot 配分を確認する
6. 通常 sampling と focused sampling を本実行する
7. 生成された HTML と sampling report を比較する

## 1. 元動画を確認する

まず動画の基礎情報を確認する。長尺かどうか、fps が高すぎないか、proxy を作るべきかをここで判断する。

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,duration \
  -of default=noprint_wrappers=1:nokey=0 path/to/full-replay.mp4
```

見たい点:

- `duration` が長いか
- `width` / `height` が大きすぎないか
- `r_frame_rate` が高すぎないか

長い 1080p / 60fps 動画は、そのまま検証を回すより proxy を作った方が扱いやすい。

## 2. 必要なら proxy 動画を作る

dry-run や focused 比較の反復では、まず軽量な proxy で検証するのが実用的。元動画は残したまま、解析専用の mp4 を別に作る。

```bash
ffmpeg -i path/to/full-replay.mp4 \
  -vf "fps=4,scale=1280:-2" \
  -c:v libx264 -preset veryfast -crf 30 \
  -an \
  path/to/full-replay.proxy.mp4
```

目安:

- `fps=4` から試し、必要なら 5-8fps に上げる
- 解像度は 720p 前後を基準にする
- 音声が不要なら `-an` で外す

proxy 化後に再確認:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,duration \
  -of default=noprint_wrappers=1:nokey=0 path/to/full-replay.proxy.mp4
```

## 3. `match-data` を単一試合で用意する

`vod analyze --match-data` は複数試合入りの `latest_findings.json` を直接受け付けない。必ず単一試合 JSON にしてから使う。

### 最短で進める場合

`replay analyze` は内部で review と単一試合化を行うので、dry-run や sampling 比較が不要ならこれが最短。

```bash
uv run lol-tools replay analyze path/to/replay.mp4
uv run lol-tools replay analyze path/to/replay.mp4 --review-count 5 --match-index 2
```

### 長尺比較フローで使う場合

`vod analyze` を直に使うため、先に `review` と `export-match-data` を通しておく。

```bash
uv run lol-tools review --count 5 --no-open
```

```bash
uv run lol-tools export-match-data \
  --input packages/lol_review/output/latest_findings.json \
  --match-index 2 \
  --output packages/lol_review/output/match_data_index2.json
```

## 4. `--speed` と `--game-start` を決める

- LoL クライアントの replay を 2 倍速で再生して録画したなら `--speed 2.0`
- 動画の先頭にロード画面や待機時間が入るなら `--game-start <秒>`
- 両方あるなら併用する

例:

```bash
uv run lol-tools vod analyze path/to/replay.proxy.mp4 \
  --mode gameplay \
  --match-data packages/lol_review/output/match_data_index2.json \
  --speed 2.0 \
  --game-start 90 \
  --no-open
```

## 5. dry-run で screenshot 配分を確認する

いきなり本実行せず、まず dry-run で allocation を見る。長尺 VOD ではここを挟むと調整が速い。

### 通常 sampling を確認する

```bash
uv run lol-tools vod analyze path/to/replay.proxy.mp4 \
  --mode gameplay \
  --match-data packages/lol_review/output/match_data_index2.json \
  --interval 5 \
  --max-screenshots 24 \
  --speed 2.0 \
  --game-start 90 \
  --dry-run-sampling \
  --dump-sampling-report packages/lol_vod_analyzer/output/fixed_sampling_report.json \
  --no-open
```

### focused sampling を確認する

```bash
uv run lol-tools vod analyze path/to/replay.proxy.mp4 \
  --mode gameplay \
  --match-data packages/lol_review/output/match_data_index2.json \
  --sampling-strategy focused \
  --focus-profile balanced \
  --focus-window-seconds 45 \
  --focus-budget-ratio 0.75 \
  --global-backfill 4 \
  --max-screenshots 24 \
  --speed 2.0 \
  --game-start 90 \
  --dry-run-sampling \
  --dump-sampling-report packages/lol_vod_analyzer/output/focused_sampling_report.json \
  --no-open
```

### report の見方

- `final_timestamps_sec`: 最終的に採用された screenshot 時刻
- `focus_budget` / `backfill_budget`: focused 時の配分比率
- `windows`: どのイベント周辺が focus window になったか
- `backfill.selected_timestamps_sec`: 全体文脈用に残した時刻

ここで「序盤が薄すぎる」「objective に寄りすぎる」などを確認してから本実行に進む。

## 6. 通常 sampling と focused sampling を本実行する

### 通常 sampling

```bash
uv run lol-tools vod analyze path/to/replay.proxy.mp4 \
  --mode gameplay \
  --match-data packages/lol_review/output/match_data_index2.json \
  --interval 5 \
  --max-screenshots 24 \
  --speed 2.0 \
  --game-start 90 \
  --no-open
```

### focused sampling

```bash
uv run lol-tools vod analyze path/to/replay.proxy.mp4 \
  --mode gameplay \
  --match-data packages/lol_review/output/match_data_index2.json \
  --sampling-strategy focused \
  --focus-profile balanced \
  --focus-window-seconds 45 \
  --focus-budget-ratio 0.75 \
  --global-backfill 4 \
  --max-screenshots 24 \
  --speed 2.0 \
  --game-start 90 \
  --no-open
```

focused を始めるときの基準:

- まず `balanced`
- 序盤レーンを厚くしたいなら `lane`
- objective 前後を厚くしたいなら `objective`
- roam / skirmish 寄りにしたいなら `roam`

## 7. 比較するときの見方

通常 sampling と focused sampling は、どちらが常に上というより、何を見たいかで強みが違う。

- 通常 sampling:
  動画全体を均等に見やすく、レーン序盤の連続性を追いやすい
- focused sampling:
  kill / death / objective / momentum 周辺を拾いやすく、長尺で重要局面を落としにくい

比較観点:

- dry-run の配分が意図どおりか
- HTML の key moments が欲しい時間帯を拾えているか
- 序盤レーンの流れを残したいか、後半の重要局面を優先したいか

## よくある使い分け

### まず 1 本だけ手早く見たい

```bash
uv run lol-tools replay analyze path/to/replay.mp4 --speed 2.0
```

### 長尺 replay を再現性高く詰めたい

1. `review`
2. `export-match-data`
3. proxy 作成
4. fixed / focused dry-run
5. 本実行 2 本

### focused の寄り方を調整したい

- focus を強める: `--focus-budget-ratio` を上げる
- 全体文脈を戻す: `--global-backfill` を増やす
- window の広さを変える: `--focus-window-seconds` を調整する
- 目的別に振る: `--focus-profile` を切り替える

## 関連ドキュメント

- 録画手順: [docs/replay-recording-guide.md](./replay-recording-guide.md)
- Windows 録画手順: [docs/replay-recording-guide-windows.md](./replay-recording-guide-windows.md)
- focused sampling の設計判断: [docs/adr/ADR-015-focused-sampling-for-long-vod-analysis.md](./adr/ADR-015-focused-sampling-for-long-vod-analysis.md)
