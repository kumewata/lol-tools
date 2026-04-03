---
name: replay-recording
description: LoL の自分のリプレイ動画をどう用意するか案内する。画面録画のやり方が分からないとき、`.rofl` をそのまま使えるか確認したいとき、Windows や macOS での録画手順を出したいとき、`lol-tools replay analyze` の前段を説明したいときに使う。
---

# /replay-recording - 自分のリプレイ動画の準備

自分の試合を `lol-tools replay analyze` で分析する前に、LoL クライアントのリプレイを動画ファイルとして保存するための案内を行う。

## 使う場面

- 「自分のリプレイ動画をどう用意すればいいか」と聞かれたとき
- `.rofl` をそのまま分析できるか確認されたとき
- 画面録画のやり方を案内したいとき
- `replay analyze` の前段の手順をまとめたいとき

## 基本方針

1. まず `.rofl` はそのまま使えず、LoL クライアントで再生した画面を録画する必要があると伝える
2. OS に合わせて、Windows なら Xbox Game Bar / OBS、macOS なら標準録画を案内する
3. 録画条件を固定したいなら `ffmpeg` を案内する

## 標準の案内

最初に次を短く伝える。

- `.rofl` は動画ファイルではない
- LoL クライアントでリプレイを再生し、その画面を `.mov` や `.mp4` として録画する
- 自分で録画した動画の方が、他人の YouTube リプレイより分析精度が高い

## 案内手順

### 1. まず簡単な方法を案内する

Windows なら Xbox Game Bar か OBS、macOS なら標準録画を優先する。

#### Windows の簡易案内

1. LoL クライアントで対象試合のリプレイを開く
2. `Win + G` で Xbox Game Bar を開く、または OBS で録画準備をする
3. リプレイを再生して録画する
4. 保存された `.mp4` を確認する

#### macOS の簡易案内

1. LoL クライアントで対象試合のリプレイを開く
2. `Shift + Command + 5` を押す
3. 画面全体または対象範囲の録画を選ぶ
4. リプレイを再生して録画する
5. 保存された `.mov` を確認する

### 2. ffmpeg が必要ならこちらを案内する

`ffmpeg` が未導入なら、OS に応じて次を案内する:

```bash
# macOS
brew install ffmpeg

# Windows (PowerShell)
winget install Gyan.FFmpeg
```

macOS の画面番号確認:

```bash
ffmpeg -f avfoundation -list_devices true -i ""
```

macOS の録画例:

```bash
ffmpeg -f avfoundation -i "1:none" -t 900 -r 10 -vf scale=1280:720 ~/Desktop/replay.mov
```

Windows の録画例:

```powershell
ffmpeg -f gdigrab -framerate 10 -i desktop -t 900 -vf scale=1280:720 "$env:USERPROFILE\Desktop\replay.mp4"
```

## 参照先

詳細手順が必要なら [docs/replay-recording-guide.md](../../docs/replay-recording-guide.md) を開く。Windows 向けだけでよければ [docs/replay-recording-guide-windows.md](../../docs/replay-recording-guide-windows.md) を開く。

## 注意点

- `.rofl` を直接渡さない
- 試合の最初から最後まで録画する（ロード画面が入っても `--game-start` で補正可能）
- 低画質すぎる動画は避ける
- 対象試合が直近数試合から外れているなら `--review-count` を増やす
- リプレイを倍速で再生して録画した場合は `--speed` オプションでタイムスタンプを補正する
