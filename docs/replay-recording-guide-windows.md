# Windows で自分のリプレイ動画を録画する手順

`lol-tools replay analyze` で自分の試合を分析するには、LoL クライアントでリプレイを再生し、その画面を `.mp4` などの動画として保存しておく必要がある。

このドキュメントは、Windows でリプレイ録画を用意する手順だけに絞ったガイド。OS をまたいだ全体像を見たい場合は [自分のリプレイ動画を用意する手順](./replay-recording-guide.md) を参照。

## 前提

- LoL クライアントで対象試合のリプレイを再生できる
- できれば対象試合は自分の直近数試合に含まれている
- `ffmpeg` を使う場合は `ffprobe` も使える

`ffprobe` の確認:

```powershell
ffprobe -version
```

入っていなければ、たとえば次でインストールできる。通常は `ffmpeg` パッケージに `ffprobe` も含まれる。

```powershell
winget install Gyan.FFmpeg
```

## 全体の流れ

1. LoL クライアントで対象試合のリプレイを開く
2. Windows の画面録画機能か録画ソフトで試合全体を録画する
3. 保存した `.mp4` を `lol-tools replay analyze` に渡す

## 一番簡単なやり方

Windows では、まず Xbox Game Bar か OBS のどちらかを使うのが簡単。

### Xbox Game Bar

追加インストールなしで始めたいとき向け。

1. LoL クライアントで対象試合のリプレイを開く
2. 可能ならウィンドウ表示かボーダーレスで、録画したい画面が収まる状態にする
3. `Win + G` で Xbox Game Bar を開く
4. キャプチャウィジェットの録画ボタンを押す、または `Win + Alt + R` で録画を開始する
5. リプレイを最初から最後まで再生する
6. もう一度 `Win + Alt + R` を押して録画を止める
7. 保存された動画を確認する

保存先の例:

```text
C:\Users\<you>\Videos\Captures
```

その後、次のように分析する。

```powershell
uv run lol-tools replay analyze "C:\Users\<you>\Videos\Captures\replay.mp4"
```

### OBS Studio

録画範囲を安定させたい、保存先や画質を細かく決めたいとき向け。

1. OBS を起動する
2. 「ソース」で「ゲームキャプチャ」または「ウィンドウキャプチャ」を追加する
3. LoL クライアントのリプレイ画面が正しく映ることを確認する
4. 「設定」→「出力」で録画先を確認する
5. 「録画開始」を押してからリプレイを再生する
6. 試合終了後に「録画終了」を押す
7. 保存された `.mp4` を確認する

OBS でも、分析時は同じように動画パスを渡せばよい。

```powershell
uv run lol-tools replay analyze "C:\Users\<you>\Videos\OBS\replay.mp4"
```

## ffmpeg で録画するやり方

毎回同じ条件で録画したいなら `ffmpeg` を使う。

### デスクトップ全体を録画する

```powershell
ffmpeg -f gdigrab -framerate 10 -i desktop -t 900 -vf scale=1280:720 "$env:USERPROFILE\Desktop\replay.mp4"
```

意味:

- `-f gdigrab`: Windows の画面キャプチャ入力を使う
- `-framerate 10`: 10fps で保存する
- `-i desktop`: デスクトップ全体を録画する
- `-t 900`: 最大 900 秒まで録画する
- `-vf scale=1280:720`: 解像度を 1280x720 に揃える

保存後は次を実行する。

```powershell
uv run lol-tools replay analyze "$env:USERPROFILE\Desktop\replay.mp4"
```

少し前の試合を選びたい場合:

```powershell
uv run lol-tools replay analyze "$env:USERPROFILE\Desktop\replay.mp4" --review-count 5 --match-index 2
```

## 録画のコツ

- `.rofl` はそのまま渡せないので、必ず再生画面を録画する
- 試合の最初から最後まで録画する
- HUD を隠さず、通常の観戦 UI を映す
- できれば 720p 以上で保存する
- リプレイを倍速で再生して録画した場合は `--speed` で補正する

## よくある詰まりどころ

### Xbox Game Bar で録画できない

フルスクリーン表示や権限設定の影響で録画が始まらないことがある。その場合はボーダーレスウィンドウに切り替えるか、OBS を使う方が安定しやすい。

### どの試合と紐付いたか分からない

まずは最新試合で試し、ズレていそうなら `--review-count` と `--match-index` を付けて調整する。

```powershell
uv run lol-tools replay analyze "C:\Users\<you>\Videos\Captures\replay.mp4" --review-count 5 --match-index 1
```

### `ffmpeg` が見つからない

```powershell
winget install Gyan.FFmpeg
uv run lol-tools doctor
```
