# CLAUDE.md

## Repository Overview

このファイルは AI エージェント向けの作業ガイド。
人向けのセットアップ手順、CLI の使い方、実行例は `README.md` を参照する。

## Shared Skills

- 共有スキル本体は `skills/` 配下に置く
- `.claude/skills` は Claude Code 互換のための同期コピー
- `.codex/skills` は Codex 互換のための同期コピー
- Claude Code / Codex のどちら向けの更新でも、編集先は `skills/` を正とする
- Windows では symlink より実ディレクトリの方が認識が安定しやすいため、互換入口は実ディレクトリで持つ

## Skill Maintenance

- スキル本体は各ディレクトリの `SKILL.md` を正本にする
- Codex 向け UI メタデータは `agents/openai.yaml` に置く
- 実際の CLI やファイル配置が変わったら、対応するスキル例も一緒に更新する
- repo 固有のデフォルト値がある場合は、スキル手順に省略時の挙動を明記する
- スキルを追加・更新したら、まず `skills/` を編集し、その内容を `.claude/skills/` と `.codex/skills/` に同期する

## Agent Working Rules

- プロジェクトの利用方法や CLI 仕様を参照するときは、まず `README.md` と実装を確認する
- ドキュメント更新時は、`README.md` を人向け、`CLAUDE.md` / `AGENT.md` をエージェント向けに分離する
- コマンド例や環境変数の説明を変更した場合は、対応するスキルの `SKILL.md` も必要に応じて更新する
- repo 固有の前提は `README.md` と実装を正とし、エージェント向けファイルには要点だけを書く

## Project Structure

uv workspace による monorepo 構成。

```
lol-tools/
├── pyproject.toml              # workspace root + lol-tools CLI
├── src/lol_tools/cli.py        # 統一エントリポイント
├── .env                        # 全 API キー（RIOT_API_KEY, GOOGLE_API_KEY）
├── packages/
│   ├── lol_review/             # 試合データ分析
│   │   ├── pyproject.toml
│   │   ├── src/lol_review/
│   │   ├── templates/
│   │   └── tests/
│   └── lol_vod_analyzer/       # 動画分析
│       ├── pyproject.toml
│       ├── src/lol_vod_analyzer/
│       ├── templates/
│       └── tests/
```

## Technology Stack

- **Python 3.12+** / **uv** package manager (workspace)
- **Riot API** (lol_review)
- **Google Gemini API** (lol_vod_analyzer)
- **yt-dlp** (YouTube字幕・ストーリーボード・動画ダウンロード)
- **OpenCV** / **Pillow** (スクリーンショット抽出・画像処理)
- **ffmpeg** (音声抽出・画面録画)
- **Pydantic** / **Jinja2** / **Typer** / **Click** / **Rich**
- **pytest** (テスト)

## Data Flow

```
Riot API → lol_review → latest_findings.json
                              ↓ --match-data
動画 → lol_vod_analyzer → vod_analysis_*.html
```

## 開発方針

- 解説動画からの言語化されたナレッジ蓄積が最優先
- 自分の試合データ (Riot API) と動画の組み合わせで高精度分析
- 画像のみの分析は精度が低いため、match-data 連携を前提とする
