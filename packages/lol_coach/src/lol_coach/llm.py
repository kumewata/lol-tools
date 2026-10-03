"""Responses API client for ChatGPT plan usage.

Spec: https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
"""

from __future__ import annotations

import json
import time
from typing import Callable, Iterator, Protocol

import httpx

from lol_coach.errors import (
    CoachError,
    InferenceFailed,
    NotEligible,
    ReauthRequired,
    TemporarilyUnavailable,
    UnsupportedRequest,
    UsageLimitExceeded,
)

API_BASE = "https://api.openai.com/v1"
RESPONSES_URL = f"{API_BASE}/responses"
MODELS_URL = f"{API_BASE}/models"
RETRY_DELAYS = (1.0, 2.0, 4.0)
STREAM_TIMEOUT = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
USAGE_SETTINGS_URL = "https://chatgpt.com/settings/usage"

_CODE_TO_ERROR: dict[str, tuple[type[CoachError], str]] = {
    "subscription_sharing_usage_limit_exceeded": (
        UsageLimitExceeded,
        f"ChatGPT プランの利用上限に達しました。{USAGE_SETTINGS_URL} で上限を確認してください。",
    ),
    "subscription_sharing_invalid_user": (
        ReauthRequired, "ChatGPT の認証が無効です。`lol-tools auth chatgpt login` で再ログインしてください。",
    ),
    "subscription_sharing_user_not_eligible": (
        NotEligible, "この ChatGPT アカウントではプランを外部アプリで利用できません。",
    ),
    "subscription_sharing_unsupported_capability": (
        UnsupportedRequest, "このモデルまたは入力はプラン利用でサポートされていません。--model を見直してください。",
    ),
    "subscription_sharing_route_not_supported": (
        UnsupportedRequest, "このエンドポイントはプラン利用でサポートされていません。",
    ),
    "subscription_sharing_usage_unavailable": (
        TemporarilyUnavailable, "ChatGPT の利用状況を確認できませんでした。時間をおいて再実行してください。",
    ),
    "subscription_sharing_user_unavailable": (
        TemporarilyUnavailable, "ChatGPT のアカウント情報を取得できませんでした。時間をおいて再実行してください。",
    ),
}

_STATUS_TO_ERROR: dict[int, tuple[type[CoachError], str]] = {
    401: _CODE_TO_ERROR["subscription_sharing_invalid_user"],
    429: _CODE_TO_ERROR["subscription_sharing_usage_limit_exceeded"],
    503: _CODE_TO_ERROR["subscription_sharing_usage_unavailable"],
}


def _error_code(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error", payload)
    if isinstance(error, dict):
        return error.get("code") or error.get("type")
    return None


def to_error(*, status: int | None, payload: object) -> CoachError:
    code = _error_code(payload)
    if code in _CODE_TO_ERROR:
        cls, message = _CODE_TO_ERROR[code]
        return cls(message)
    if status in _STATUS_TO_ERROR:
        cls, message = _STATUS_TO_ERROR[status]
        return cls(message)
    if status == 403:
        return NotEligible(f"リクエストが拒否されました（{code or 'forbidden'}）。")
    if status == 400:
        return UnsupportedRequest(f"リクエストが不正です（{code or 'bad_request'}）。")
    where = f"HTTP {status}" if status is not None else "stream"
    return InferenceFailed(f"推論に失敗しました（{where}, {code or 'unknown'}）。")


class LLMProvider(Protocol):
    model: str

    def stream(self, *, instructions: str, input_text: str) -> Iterator[str]: ...


def _iter_sse(lines: Iterator[str]) -> Iterator[dict]:
    """Yield JSON events. An unterminated trailing event is discarded (SSE spec)."""
    data: list[str] = []
    for line in lines:
        if line == "":
            if data:
                raw = "\n".join(data)
                data = []
                if raw == "[DONE]":
                    continue
                try:
                    event = json.loads(raw)
                except ValueError:
                    raise InferenceFailed("ストリームの応答を解釈できませんでした。") from None
                if isinstance(event, dict):
                    yield event
            continue
        if line.startswith("data:"):
            data.append(line[5:].lstrip())


def list_models(http: httpx.Client, token: str) -> list[str]:
    try:
        resp = http.get(MODELS_URL, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as e:
        raise TemporarilyUnavailable(f"モデル一覧を取得できませんでした（{type(e).__name__}）。") from None
    if resp.status_code != 200:
        raise to_error(status=resp.status_code, payload=_safe_json(resp))
    body = _safe_json(resp)
    # Plan usage returns {"models": [...]} (observed 2026-10-03); keep "data" for the public API shape.
    models = (body.get("models") or body.get("data") or []) if isinstance(body, dict) else []
    listed = [
        m for m in models
        if isinstance(m, dict) and (m.get("slug") or m.get("id")) and m.get("visibility", "list") == "list"
    ]
    listed.sort(key=lambda m: m.get("priority", float("inf")))
    return [str(m.get("slug") or m.get("id")) for m in listed]


def _safe_json(resp: httpx.Response) -> object:
    try:
        return resp.json()
    except ValueError:
        return None


class ChatGPTPlanProvider:
    def __init__(
        self,
        http: httpx.Client,
        token_supplier: Callable[[], str],
        model: str,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.http = http
        self.token_supplier = token_supplier
        self.model = model
        self._sleep = sleep

    def _body(self, instructions: str, input_text: str) -> dict:
        return {
            "model": self.model,
            "instructions": instructions,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": input_text}]}],
            "store": False,
            "stream": True,
        }

    def stream(self, *, instructions: str, input_text: str) -> Iterator[str]:
        body = self._body(instructions, input_text)
        for attempt in range(len(RETRY_DELAYS) + 1):
            emitted = False
            try:
                for delta in self._stream_once(body):
                    emitted = True
                    yield delta
                return
            except TemporarilyUnavailable:
                # Retrying after partial output would duplicate text on screen.
                if emitted or attempt == len(RETRY_DELAYS):
                    raise
                self._sleep(RETRY_DELAYS[attempt])

    def _stream_once(self, body: dict) -> Iterator[str]:
        headers = {
            "Authorization": f"Bearer {self.token_supplier()}",
            "Accept": "text/event-stream",
        }
        try:
            with self.http.stream(
                "POST", RESPONSES_URL, json=body, headers=headers, timeout=STREAM_TIMEOUT
            ) as resp:
                if resp.status_code != 200:
                    resp.read()
                    raise to_error(status=resp.status_code, payload=_safe_json(resp))
                for event in _iter_sse(resp.iter_lines()):
                    kind = event.get("type")
                    if kind == "response.output_text.delta":
                        yield event.get("delta") or ""
                    elif kind == "response.completed":
                        return
                    elif kind in ("response.failed", "response.incomplete", "error"):
                        payload = event.get("response", event)
                        raise to_error(status=None, payload=payload)
        except httpx.HTTPError as e:
            raise TemporarilyUnavailable(f"OpenAI への接続が切れました（{type(e).__name__}）。") from None
        raise InferenceFailed("応答が完了する前にストリームが終了しました。")
