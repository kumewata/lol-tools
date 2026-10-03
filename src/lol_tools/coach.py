"""`lol-tools auth chatgpt` and helpers for `lol-tools advise`."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.markup import escape

from lol_coach import advise as coach_advise
from lol_coach import chatgpt_auth
from lol_coach.errors import CoachError
from lol_coach.llm import ChatGPTPlanProvider, list_models
from lol_coach.store import CredentialStore

console = Console()
MODEL_ENV = "LOL_TOOLS_CHATGPT_MODEL"
# The model list has no price field; luna is the one described as "fast and efficient",
# so it is the default to keep the user's plan usage low.
DEFAULT_MODEL = "gpt-5.6-luna"

auth_app = typer.Typer(help="外部サービスへのログイン")
chatgpt_app = typer.Typer(help="Sign in with ChatGPT（ChatGPT プランで LLM を利用）")
auth_app.add_typer(chatgpt_app, name="chatgpt")


def _http() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(30.0))


def _store() -> CredentialStore:
    return CredentialStore()


def _fail(error: CoachError) -> typer.Exit:
    console.print(f"[red]Error:[/] {escape(str(error))}")
    return typer.Exit(1)


@chatgpt_app.command("login")
def login() -> None:
    """ブラウザで ChatGPT にログインし、プラン利用を許可します。"""
    def show_url(url: str) -> None:
        console.print("ブラウザで ChatGPT のログイン画面を開きます。開かない場合は次の URL を開いてください:")
        console.print(url, soft_wrap=True)

    try:
        with _http() as http:
            creds = chatgpt_auth.login(http, _store(), on_url=show_url)
    except CoachError as e:
        raise _fail(e) from None
    console.print(f"[green]ログインしました[/]（client: {creds.client_id}）")


@chatgpt_app.command("status")
def status() -> None:
    """保存済みのログイン状態を表示します。"""
    creds = _store().load()
    if creds is None:
        console.print("未ログインです。`uv run lol-tools auth chatgpt login` を実行してください。")
        raise typer.Exit(1)
    expires = datetime.fromtimestamp(creds.expires_at).strftime("%Y-%m-%d %H:%M:%S")
    console.print(f"ログイン済み（client: {creds.client_id}）")
    console.print(f"access token 有効期限: {expires}（期限切れ時は自動更新）")
    plan_ok = chatgpt_auth.PLAN_SCOPE in creds.scopes
    console.print(f"プラン利用: {'許可済み' if plan_ok else '[red]未許可[/]'}")


@chatgpt_app.command("models")
def models() -> None:
    """プラン利用で選べるモデルを表示します。"""
    try:
        with _http() as http:
            token = chatgpt_auth.get_valid_access_token(http, _store())
            for slug in list_models(http, token):
                console.print(slug)
    except CoachError as e:
        raise _fail(e) from None


@chatgpt_app.command("logout")
def logout() -> None:
    """トークンを失効させ、ローカルから削除します。"""
    store = _store()
    creds = store.load()
    if creds is None:
        console.print("未ログインです。")
        return
    with _http() as http:
        revoked = chatgpt_auth.revoke(http, creds)
    store.clear_tokens()
    if revoked:
        console.print("ログアウトしました。")
    else:
        console.print(
            "[yellow]ローカルのトークンは削除しましたが、サーバー側の失効は確認できませんでした。[/]"
            " 必要なら https://chatgpt.com/settings/security で連携を解除してください。"
        )


def _load_practice_status(summoner: str | None) -> dict[str, Any] | None:
    try:
        from lol_practice.cli import build_status_payload
    except ModuleNotFoundError:
        return None
    try:
        return build_status_payload(summoner=summoner)
    except Exception as e:  # DuckDB missing/locked etc. must not block advice
        console.print(f"[yellow]Warning:[/] 練習プランの進捗を取得できませんでした: {e}")
        return None


def _load_matchup(findings: dict[str, Any]) -> dict[str, Any] | None:
    from lol_tools.matchup import build_matchup_summary

    try:
        return build_matchup_summary(findings)
    except Exception as e:
        console.print(f"[yellow]Warning:[/] 対面サマリを作れませんでした: {e}")
        return None


def build_advice_input(findings_path: Path, summoner: str | None) -> str:
    findings = json.loads(findings_path.read_text(encoding="utf-8"))
    previous_path = coach_advise.find_previous_snapshot(findings_path.parent)
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path else None
    return coach_advise.build_input(
        findings,
        practice_status=_load_practice_status(summoner),
        matchup=_load_matchup(findings),
        previous=previous,
    )


def resolve_default_model(available: list[str]) -> str:
    if DEFAULT_MODEL in available:
        return DEFAULT_MODEL
    if not available:
        raise typer.BadParameter("利用可能なモデルがありません。")
    console.print(
        f"[yellow]Warning:[/] 既定モデル {DEFAULT_MODEL} が使えないため {available[0]} を使います。"
        f" `--model` か {MODEL_ENV} で指定できます。"
    )
    return available[0]


def run_llm_advice(input_text: str, *, output_dir: Path, model: str | None) -> Path:
    store = _store()
    with _http() as http:
        def token() -> str:
            return chatgpt_auth.get_valid_access_token(http, store)

        resolved = model or os.environ.get(MODEL_ENV)
        if not resolved:
            resolved = resolve_default_model(list_models(http, token()))
        console.print(f"[dim]model: {resolved}[/]")
        provider = ChatGPTPlanProvider(http, token, resolved)

        def write(delta: str) -> None:
            sys.stdout.write(delta)
            sys.stdout.flush()

        path = coach_advise.generate_advice(
            provider,
            instructions=coach_advise.load_instructions(),
            input_text=input_text,
            output_dir=output_dir,
            on_delta=write,
        )
    sys.stdout.write("\n")
    return path
