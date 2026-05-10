---
name: lol-advice
description: LoL の試合レポートデータを分析し、ゲームプレイの改善点をアドバイスする
---

# /lol-advice - LoL 試合改善アドバイス

LoL の試合レポートデータを分析し、ゲームプレイの改善点をアドバイスする。
さらに findings から「今日の練習プラン」を生成し、日付単位で進捗を追跡する。

## 手順

1. ユーザーに Riot ID を確認する
   - Riot ID が明示されていればその値を使う
   - Riot ID が省略されている場合は、リポジトリルートの `.env` に設定された `DEFAULT_RIOT_ID` を使ってよい
   - `DEFAULT_RIOT_ID` も無い場合だけユーザーに確認する
2. 最新データを取得するため、以下を実行する:
   ```bash
   uv run lol-tools review "{RiotID}" --no-open
   ```
   Riot ID を省略してよい場合は、以下でもよい:
   ```bash
   uv run lol-tools review --no-open
   ```
3. `packages/lol_review/output/latest_findings.json` を読み込む
4. **active プランの進捗を取得する**:
   ```bash
   uv run lol-tools practice status --json
   ```
   - 結果は `{"plans": [...]}` 形式の JSON
   - `plans` が空なら「初回」として扱う
   - 各 verdict は `category`, `source_severity`, `current_severity`, `status`
   - `status` の値: `done`（消失）/ `improving`（severity 低下）/ `continuing`（変化なし or 悪化）/ `manual_done`（ユーザー手動 done）/ `manual_keep`（ユーザー手動 keep）
5. JSON の内容と進捗判定を分析し、以下の構成でアドバイスを出力する

※ タイムスタンプ付きスナップショット (`findings_YYYYMMDD_HHMMSS.json`) も自動保存されるので、過去の分析結果と比較可能。

## 出力フォーマット

### 概要
- サモナー名、試合数、勝率、平均KDA を簡潔に要約

### ルールベース検出結果
- `findings` 配列の内容を severity 順（critical → warning → info）で表示
- 各項目に具体的な数値を含める

### 総合アドバイス
以下の観点から、試合データ（matches, player_stats, champion_stats）を読み解いて具体的な改善提案を行う:

1. **マッチアップ分析** — `lane_opponents` で対面チャンピオンを確認し、勝敗・KDA との相関を分析。ボットレーンの場合は ADC+SUP の2v2ペアとして評価する。苦手/得意な対面パターンを特定する。`ally_team` / `enemy_team` からチーム構成の傾向も考慮する
2. **レーニング（序盤）** — CS推移、序盤のデスタイミング。対面チャンピオンとの相性を踏まえた序盤の立ち回り提案
3. **チームファイト（中盤〜終盤）** — `kill_participation` でキル参加率を確認（ロール別目安: SUP 50%+, JG 40%+, MID/BOT 35%+, TOP 30%+）。デスのタイミングと集団戦の関連
4. **ダメージ構成分析** — `damage_physical` / `damage_magical` / `damage_true` の内訳を確認。チャンピオンの特性に合ったダメージ比率かどうか。ビルドの効率を評価する
5. **ビルドパス** — コアアイテムの完成タイミング、ビルド順の妥当性。対面に応じたビルド適応ができているか
6. **ビジョン** — ワード購入頻度、ビジョンスコア
7. **ゲーム時間帯と勝率** — `game_duration_analysis` で短期戦/長期戦の勝率傾向を分析。プレイスタイルの適性を判断する
8. **チャンピオンプール** — 勝率の高い/低いチャンピオン、得意チャンピオンの傾向

### 前回との比較（過去スナップショットがある場合）

`packages/lol_review/output/` 内の `findings_*.json` をタイムスタンプ順にリストし、最新と1つ前のスナップショットを比較する:

1. Glob で `packages/lol_review/output/findings_*.json` を取得
2. 最新 = `latest_findings.json`（今回生成）、前回 = タイムスタンプ順で2番目のファイル
3. 前回データがあれば以下を比較して表示:
   - 勝率の変化（例: 45% → 60% で改善）
   - 平均KDAの変化
   - 平均CS/minの変化
   - findingsの増減（前回あった問題が解消されたか、新たな問題が出たか）
4. 前回データがなければ「初回分析のため比較データなし」と表示

### 優先して取り組むべきこと（TOP 3）
- 最もインパクトのある改善点を3つに絞って提案

### 進捗追跡（active プランがある場合）

手順4で取得した `practice status --json` の結果を使う。

`plans` が空の場合はこのセクションを省略。

`plans[0].verdicts` を以下のフォーマットで表示する:

```
- ✅ {category}: {source_severity} → {current_severity or '消失'} ({status})
```

`status` の意味:
- `done` — 元 finding が消失した（達成）
- `improving` — severity が下がった（前進中）
- `continuing` — severity 変化なし or 悪化（継続課題）
- `manual_done` — ユーザーが手動で done と書いた（自動判定をスキップ）
- `manual_keep` — ユーザーが手動で keep と書いた（解消したくないポジティブな点）

### 今日の練習プラン

以下のコマンドで active プランを更新または新規作成する:

```bash
uv run lol-tools practice generate --json
```

- ファイルパス: `packages/lol_practice/plans/{YYYY-MM-DD}.md`
- 同じ日付の既存プランがあれば、ユーザーの手動編集を守るため上書きしない
- 生成結果は `{"created": true/false, "date": "...", "path": "..."}` 形式
- 最新 findings を severity 順（critical → warning → info）で category 単位にユニーク化する
- 自動生成された練習ポイントが粗い場合だけ、ユーザーへの回答内で追加アドバイスとして補足する

書き出した後は、CLI 確認のため以下を実行して結果を報告する:

```bash
uv run lol-tools practice show
uv run lol-tools practice status --json
```

## 注意事項
- データに基づいた具体的な数値を示すこと
- 「もっと CS を取れ」ではなく「平均 X.X CS/min → 目標 Y.Y、特に10分以降のサイドレーン CS を意識」のように具体的に
- チャンピオンごとの特性を考慮したアドバイスにすること
- 試合の時系列データ（kill/death タイムスタンプ、アイテム購入順）を活用して、パターンを見つけること
- ポジティブな点も挙げること（良い KDA の試合、高い Assist 率など）
- 練習プランの Markdown を書く際は、ユーザーが手動で `**進捗**: done` / `keep` と書き換えた行を上書きしない（既存プランがあれば差分更新ではなく日付単位で新規作成）
- `packages/lol_practice/plans/*.md` は gitignored。コミットしないこと
