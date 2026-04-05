# 自分のリプレイ動画を用意する手順

`lol-tools replay analyze` で精度の高い分析をするには、LoL クライアントのリプレイを再生して、その画面を動画として保存しておく必要がある。

このドキュメントは、`自分の試合録画を用意する` ところだけに絞った手順書。長尺 replay の proxy 作成、dry-run、focused sampling 比較まで含めた全体フローは [docs/long-vod-workflow.md](./long-vod-workflow.md) を参照。

## 前提

- LoL クライアントで対象試合のリプレイを再生できる
- `ffprobe` が使える
- できれば対象試合は自分の直近数試合に含まれている

`ffprobe` の確認:

```bash
ffprobe -version
```

入っていなければ、たとえば次でインストールできる。通常は `ffmpeg` パッケージに `ffprobe` も含まれる。

```bash
# macOS
brew install ffmpeg

# Windows (PowerShell)
winget install Gyan.FFmpeg
```

## 全体の流れ

1. LoL クライアントで対象試合のリプレイを開く
2. 画面録画でその試合を動画ファイルとして保存する
3. 保存した動画を `lol-tools replay analyze` に渡す

## 一番簡単なやり方

OS 標準の画面録画を使うのが最も手早い。

### macOS

macOS の標準録画機能を使って、LoL のリプレイ再生画面を録画する。

1. LoL クライアントで対象試合のリプレイを開く
2. フルスクリーンでもウィンドウでもよいので、録画したい画面を表示する
3. `Shift + Command + 5` を押す
4. 「画面全体を収録」または「選択部分を収録」を選ぶ
5. リプレイを再生して録画を開始する
6. 試合が終わったら録画を停止する
7. 保存された `.mov` ファイルを確認する

その後、次のように分析する。

```bash
uv run lol-tools replay analyze path/to/replay.mov
```

### Windows

Windows では Xbox Game Bar か OBS で録画するのが簡単。

1. LoL クライアントで対象試合のリプレイを開く
2. `Win + G` で Xbox Game Bar を開く、または OBS で画面録画を始める
3. リプレイを再生して録画する
4. 保存された `.mp4` を確認する
5. 次のように分析する

```bash
uv run lol-tools replay analyze path/to/replay.mp4
```

## ffmpeg で録画するやり方

録画条件を固定したい場合は `ffmpeg` でも録画できる。

### macOS: 画面デバイス番号を確認する

```bash
ffmpeg -f avfoundation -list_devices true -i ""
```

出力に表示される画面デバイス番号を確認する。たとえば `1` が対象画面なら、次のように使う。

### macOS: 録画する

```bash
ffmpeg -f avfoundation -i "1:none" -t 900 -r 10 -vf scale=1280:720 ~/Desktop/replay.mov
```

意味:

- `1:none`: 画面デバイス 1 を録画し、音声は使わない
- `-t 900`: 最大 900 秒まで録画する
- `-r 10`: 10fps で保存する
- `-vf scale=1280:720`: 解像度を 1280x720 に揃える

録画後は次を実行する。

```bash
uv run lol-tools replay analyze path/to/replay.mov
```

少し前の試合を選びたい場合:

```bash
uv run lol-tools replay analyze path/to/replay.mov --review-count 5 --match-index 2
```

### Windows: ffmpeg で録画する例

Windows では `gdigrab` を使ってデスクトップ全体を録画できる。

```powershell
ffmpeg -f gdigrab -framerate 10 -i desktop -t 900 -vf scale=1280:720 "$env:USERPROFILE\Desktop\replay.mp4"
```

保存後は次を実行する。

```bash
uv run lol-tools replay analyze path/to/replay.mp4
```

## どの方法を使うべきか

- とりあえず試したいだけなら macOS 標準録画
- Windows なら Xbox Game Bar または OBS
- 毎回同じ条件で録画したいなら `ffmpeg`
- 他人の YouTube リプレイを使うより、自分で録画した動画を使う方が精度は高い

## 録画のコツ

- 試合の最初から最後まで録画する
- HUD を隠さず、通常の観戦画面で録画する
- 画質が低すぎるとチャンピオンや UI の認識が不安定になる
- できれば 720p 以上で保存する
- 対象試合が直近数試合から外れているなら `--review-count` を増やす
- 2 倍速で録画したなら、分析時に `--speed 2.0` を付ける
- 長尺 replay は、録画後に proxy 動画を作ってから検証すると扱いやすい

## よくある詰まりどころ

### `.rofl` ファイルを直接渡せない

LoL の `.rofl` は動画ファイルではないため、そのままでは分析できない。LoL クライアントで再生して、画面録画した `.mov` や `.mp4` を使う。

### どの試合と紐付いたか分からない

まずは最新試合で試し、ズレていそうなら `--review-count` と `--match-index` を付けて調整する。

```bash
uv run lol-tools replay analyze path/to/replay.mp4 --review-count 5 --match-index 1
```

### `ffmpeg` が見つからない

```bash
# macOS
brew install ffmpeg

# Windows
winget install Gyan.FFmpeg

uv run lol-tools doctor
```
