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
3. 分析用の入力と出力フォーマットを取得する:
   ```bash
   uv run lol-tools advise --no-fetch --dry-run
   ```
   - 出力の前半（`---- input ----` より前）が出力フォーマットと注意事項の正本（`packages/lol_coach/src/lol_coach/prompts/advice.md`）
   - 後半は `latest_findings.json`・練習プランの進捗（`practice status --json` 相当）・対面サマリ（`matchup summary --json` 相当）・前回スナップショットとの比較を圧縮した JSON
   - 圧縮で落とした項目（位置タイムラインなど）が必要な場合だけ `packages/lol_review/output/latest_findings.json` を直接読む
4. 正本の「出力フォーマット」と「注意事項」に従ってアドバイスを出力する。出力構成や観点を変えるときは SKILL.md ではなく正本を編集する

エージェントを使わず CLI 単体で同じ助言を生成する場合は、`uv run lol-tools auth chatgpt login` の後に `uv run lol-tools advise` を使う（ユーザーの ChatGPT プラン枠を消費する）。

## 今日の練習プラン

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
- 助言の内容に関する注意事項は正本（`packages/lol_coach/src/lol_coach/prompts/advice.md`）に従う
- 練習プランの Markdown を書く際は、ユーザーが手動で `**進捗**: done` / `keep` と書き換えた行を上書きしない（既存プランがあれば差分更新ではなく日付単位で新規作成）
- `packages/lol_practice/plans/*.md` は gitignored。コミットしないこと
