---
title: "ADR-016: Sign in with ChatGPT による助言生成と将来の公開提供方針"
status: accepted
date: 2026-10-03
tags: [LLM, 認証, Sign in with ChatGPT, lol_coach, 公開提供]
---

# ADR-016: Sign in with ChatGPT による助言生成と将来の公開提供方針

## ステータス

Accepted

## コンテキスト

試合データの助言生成は `skills/lol-advice` に依存しており、Claude Code / Codex を使わない人は利用できなかった。
2026-09 の OpenAI DevDay で、Sign in with ChatGPT（preview）が発表された。
OSS / ローカルアプリは `client_id=dynamic_agent_client` で動的登録でき、ユーザーの ChatGPT Plus / Pro 枠で Responses API を呼べる。

最終目標は、LoL 分析機能を公開し、LLM コストを利用者自身のサブスクで賄う形で提供することである。

## 決定

1. 新パッケージ `lol_coach` に、認証（`chatgpt_auth` / `store`）、LLM 呼び出し（`llm`）、入力圧縮（`context`）、助言生成（`advise`）を置く。CLI 層（`src/lol_tools/coach.py`）とは分離する
2. HTTP は httpx を直接使い、openai SDK は使わない。`store=false` / `stream=true` が必須で、一部パラメータが禁止され、エラーコードも独自のため
3. データ収集は決定的処理として Python で行い、LLM は 1 回だけ呼ぶ。tool calling やエージェントループは使わない
4. `latest_findings.json` は LLM に渡す前に圧縮する（実データで約 9%）。位置・レベルアップのタイムラインを落とし、アイテムは完成品とブーツ、ゴールド差は 5 分刻みに絞る
5. 複数試合にまたがる集計（時間帯別・チャンピオン別・キュー別・味方別の勝率や平均値）は Python で事前計算して `aggregates` として渡し、モデルには引用だけさせる。時刻も `分:秒` に変換して渡す。軽量モデル（gpt-5.6-luna）が集計を誤ったため（2026-10-03 に3モデルで比較）
6. 出力フォーマットの正本を `lol_coach/prompts/advice.md` に置く。`lol-advice` skill も `advise --dry-run` 経由で同じ正本と圧縮入力を使う
7. トークンは `~/.config/lol-tools/chatgpt.json`（0600、atomic write）に保存し、refresh はファイルロックで直列化する

## 将来の公開提供に向けた方針

| 形態 | OpenAI 側 | Riot 側 | 本設計からの差分 |
|---|---|---|---|
| OSS CLI 配布 | `dynamic_agent_client` でそのまま可 | 利用者ごとの API キーが必要（規約は要確認） | パッケージ配布の整備のみ |
| ホスト型サービス | 標準 client_id が必要（waitlist） | Production Key が必要 | `chatgpt_auth` の client_id と `CredentialStore` をサーバー側の実装に差し替える |

どちらの形態でも `context` / `llm` / `advise` はそのまま使えるよう、ローカルパスや `.env` に依存させない。

## 結果

- エージェントなしで `auth chatgpt login` → `advise` の 2 コマンドで助言を得られる
- skill と CLI で出力フォーマットの二重管理がなくなる
- 利用できるのは ChatGPT Plus / Pro のアカウントに限られる。Free アカウントでは同意後のコード交換が `invalid_grant` で失敗することを実機で確認した（2026-10-03）。公開時に Free の利用者向けの経路を別に用意するかは未決定
- Sign in with ChatGPT は preview のため、仕様変更時は `chatgpt_auth` / `llm` の定数を更新する

## 採用しなかった案

- vod_analyzer の LLM 切り替え: 主要機能ではないため対象外
- 生の findings JSON をそのまま渡す: 約 210K 文字あり、ユーザーのプラン枠を圧迫する
- `.env` へのトークン保存: refresh でローテーションするうえ、権限管理が必要なため

## 参照

- https://developers.openai.com/siwc/token-sharing-open-source
- https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery
- https://developers.openai.com/siwc/request-client-id
