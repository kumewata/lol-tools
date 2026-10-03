from __future__ import annotations

import json

import httpx
import pytest

from lol_coach import llm
from lol_coach.errors import (
    InferenceFailed,
    NotEligible,
    ReauthRequired,
    TemporarilyUnavailable,
    UnsupportedRequest,
    UsageLimitExceeded,
)


def _sse(*events: dict) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def _provider(handler, sleeps: list[float] | None = None) -> llm.ChatGPTPlanProvider:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return llm.ChatGPTPlanProvider(
        http, lambda: "AT-secret", "gpt-test", sleep=(sleeps.append if sleeps is not None else lambda s: None)
    )


def _run(provider) -> str:
    return "".join(provider.stream(instructions="sys", input_text="data"))


def test_stream_yields_deltas_until_completed() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, content=_sse(
            {"type": "response.created"},
            {"type": "response.output_text.delta", "delta": "こん"},
            {"type": "response.output_text.delta", "delta": "にちは"},
            {"type": "response.completed"},
            {"type": "response.output_text.delta", "delta": "ignored"},
        ))

    assert _run(_provider(handler)) == "こんにちは"
    body = seen["body"]
    assert body["store"] is False and body["stream"] is True
    assert body["model"] == "gpt-test"
    assert body["instructions"] == "sys"
    assert body["input"][0]["content"][0] == {"type": "input_text", "text": "data"}
    assert "max_output_tokens" not in body
    assert seen["auth"] == "Bearer AT-secret"


def test_stream_without_completed_raises() -> None:
    handler = lambda r: httpx.Response(200, content=_sse({"type": "response.output_text.delta", "delta": "a"}))
    with pytest.raises(InferenceFailed):
        _run(_provider(handler))


def test_response_failed_event_maps_code() -> None:
    handler = lambda r: httpx.Response(200, content=_sse({
        "type": "response.failed",
        "response": {"error": {"code": "subscription_sharing_usage_limit_exceeded"}},
    }))
    with pytest.raises(UsageLimitExceeded):
        _run(_provider(handler))


@pytest.mark.parametrize(("status", "code", "expected"), [
    (429, "subscription_sharing_usage_limit_exceeded", UsageLimitExceeded),
    (401, "subscription_sharing_invalid_user", ReauthRequired),
    (403, "subscription_sharing_user_not_eligible", NotEligible),
    (400, "subscription_sharing_unsupported_capability", UnsupportedRequest),
    (429, None, UsageLimitExceeded),
    (401, None, ReauthRequired),
    (403, "chatpass_v2_scope_not_authorized", NotEligible),
])
def test_error_mapping(status, code, expected) -> None:
    payload = {"error": {"code": code}} if code else {}
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json=payload)

    with pytest.raises(expected) as exc:
        _run(_provider(handler))
    assert calls == [1]  # non-retryable
    assert "AT-secret" not in str(exc.value)


def test_503_retries_then_fails() -> None:
    sleeps: list[float] = []
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, json={"error": {"code": "subscription_sharing_usage_unavailable"}})

    with pytest.raises(TemporarilyUnavailable):
        _run(_provider(handler, sleeps))
    assert sleeps == [1.0, 2.0, 4.0]
    assert len(calls) == 4


def test_503_then_success() -> None:
    responses = iter([
        httpx.Response(503, json={}),
        httpx.Response(200, content=_sse(
            {"type": "response.output_text.delta", "delta": "ok"}, {"type": "response.completed"},
        )),
    ])
    assert _run(_provider(lambda r: next(responses), [])) == "ok"


def test_list_models_filters_visibility() -> None:
    handler = lambda r: httpx.Response(200, json={"data": [
        {"id": "a", "slug": "gpt-a", "visibility": "list"},
        {"id": "b", "slug": "gpt-b", "visibility": "hidden"},
    ]})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert llm.list_models(http, "t") == ["gpt-a"]


def test_malformed_sse_raises_inference_failed() -> None:
    handler = lambda r: httpx.Response(200, content=b"data: {not json\n\n")
    with pytest.raises(InferenceFailed):
        _run(_provider(handler))


def test_null_delta_and_unterminated_tail() -> None:
    content = _sse(
        {"type": "response.output_text.delta", "delta": None},
        {"type": "response.output_text.delta", "delta": "ok"},
        {"type": "response.completed"},
    ) + b"data: {trunc"
    assert _run(_provider(lambda r: httpx.Response(200, content=content))) == "ok"


def test_transport_error_is_retried_before_output() -> None:
    attempts: list[int] = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, content=_sse(
            {"type": "response.output_text.delta", "delta": "ok"}, {"type": "response.completed"},
        ))

    assert _run(_provider(handler, [])) == "ok"
    assert len(attempts) == 2


def test_incomplete_response_raises() -> None:
    handler = lambda r: httpx.Response(200, content=_sse(
        {"type": "response.output_text.delta", "delta": "a"},
        {"type": "response.incomplete", "response": {"error": None}},
    ))
    with pytest.raises(InferenceFailed) as exc:
        _run(_provider(handler))
    assert "HTTP None" not in str(exc.value)


def test_list_models_reads_plan_shape_sorted_by_priority() -> None:
    handler = lambda r: httpx.Response(200, json={"models": [
        {"slug": "gpt-late", "visibility": "list", "priority": 9},
        {"slug": "gpt-hidden", "visibility": "hide", "priority": 1},
        {"slug": "gpt-first", "visibility": "list", "priority": 2},
    ]})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert llm.list_models(http, "t") == ["gpt-first", "gpt-late"]
