from __future__ import annotations

import json
import stat
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from lol_coach import chatgpt_auth as auth
from lol_coach.errors import LoginFailed, PlanScopeNotGranted, ReauthRequired
from lol_coach.store import Credentials, CredentialStore

SECRET_TOKENS = ("AT-secret", "RT-secret")


def _creds(**overrides) -> Credentials:
    base = dict(
        subject="user-1",
        client_id="oaiapp_123",
        ext_agent_host_id="urn:uuid:host",
        id_token="IDT",
        access_token="AT-secret",
        refresh_token="RT-secret",
        expires_at=time.time() + 3600,
        scopes=[auth.PLAN_SCOPE],
    )
    base.update(overrides)
    return Credentials(**base)


@pytest.fixture
def store(tmp_path: Path) -> CredentialStore:
    return CredentialStore(tmp_path / "cfg" / "chatgpt.json")


@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(key) -> dict:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="k1", alg="RS256", use="sig")
    return {"keys": [jwk]}


def _id_token(key, *, aud="oaiapp_123", nonce="n1", iss=auth.ISSUER) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": "user-1", "aud": aud, "iss": iss, "nonce": nonce, "iat": now, "exp": now + 600},
        key,
        algorithm="RS256",
        headers={"kid": "k1"},
    )


def test_authorize_url_has_required_params() -> None:
    url = auth.build_authorize_url(
        client_id=auth.DYNAMIC_CLIENT_ID,
        redirect_uri="http://127.0.0.1:5555/auth/callback",
        state="s",
        nonce="n",
        code_challenge="c",
        host_id="urn:uuid:h",
        register=True,
    )
    parsed = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == auth.AUTHORIZE_URL
    assert q["scope"].split() == [
        "openid", "profile", "email", "offline_access", "resource.invoke", "chatgpt.tokens.use.direct",
    ]
    assert q["resource"] == "https://api.openai.com/v1"
    assert q["code_challenge_method"] == "S256"
    assert q["response_type"] == "code"
    assert q["redirect_uri"].startswith("http://127.0.0.1:")
    assert q["redirect_uri"].endswith("/auth/callback")
    assert q["agent_name_hint"] == "lol-tools"
    assert q["ext_agent_host_id"] == "urn:uuid:h"


def test_authorize_url_omits_agent_name_on_reauth() -> None:
    url = auth.build_authorize_url(
        client_id="oaiapp_123", redirect_uri="http://127.0.0.1:1/callback", state="s",
        nonce="n", code_challenge="c", host_id="h", register=False,
    )
    assert "agent_name_hint" not in parse_qs(urlparse(url).query)


def test_pkce_challenge_is_s256_without_padding() -> None:
    import base64
    import hashlib

    verifier, challenge = auth.pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected
    assert "=" not in challenge


def test_store_writes_0600_atomically(store: CredentialStore) -> None:
    store.save(_creds())
    mode = stat.S_IMODE(store.path.stat().st_mode)
    assert mode == 0o600
    assert store.load().access_token == "AT-secret"
    assert not list(store.path.parent.glob(".chatgpt.*.tmp"))


def test_store_host_id_is_stable_and_survives_clear(store: CredentialStore) -> None:
    host = store.host_id()
    assert host.startswith("urn:uuid:")
    store.save(_creds(ext_agent_host_id=host))
    store.clear_tokens()
    assert store.load() is None
    assert store.host_id() == host
    assert store.issued_client_id() == "oaiapp_123"


def test_exchange_and_refresh_form_params(store: CredentialStore) -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == auth.TOKEN_URL
        seen.append({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, json={
            "access_token": "AT2", "refresh_token": "RT2", "expires_in": 3600,
            "scope": "openid chatgpt.tokens.use.direct",
        })

    http = httpx.Client(transport=httpx.MockTransport(handler))
    auth.exchange_code(http, client_id="oaiapp_123", code="C", verifier="V", redirect_uri="http://127.0.0.1:1/callback")
    new = auth.refresh(http, _creds())

    assert seen[0] == {
        "grant_type": "authorization_code", "client_id": "oaiapp_123", "code": "C",
        "code_verifier": "V", "redirect_uri": "http://127.0.0.1:1/callback", "resource": auth.RESOURCE,
    }
    assert seen[1]["grant_type"] == "refresh_token"
    assert seen[1]["client_id"] == "oaiapp_123"
    assert seen[1]["client_id"] != auth.DYNAMIC_CLIENT_ID
    assert seen[1]["resource"] == auth.RESOURCE
    assert new.refresh_token == "RT2"
    assert new.id_token == "IDT"  # kept when refresh response omits it


def test_refresh_invalid_grant_clears_tokens(store: CredentialStore) -> None:
    store.save(_creds(expires_at=time.time() - 10))
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": "invalid_grant"})
    ))
    with pytest.raises(ReauthRequired):
        auth.get_valid_access_token(http, store)
    assert store.load() is None
    assert store.issued_client_id() == "oaiapp_123"


def test_valid_token_is_returned_without_refresh(store: CredentialStore) -> None:
    store.save(_creds())
    http = httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("no HTTP expected")))
    assert auth.get_valid_access_token(http, store) == "AT-secret"


def test_refresh_uses_lock(store: CredentialStore, monkeypatch) -> None:
    store.save(_creds(expires_at=time.time() - 10))
    entered: list[bool] = []
    original = store.lock

    def tracking_lock():
        entered.append(True)
        return original()

    monkeypatch.setattr(store, "lock", tracking_lock)
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        "access_token": "AT2", "refresh_token": "RT2", "expires_in": 3600, "scope": auth.PLAN_SCOPE,
    })))
    assert auth.get_valid_access_token(http, store) == "AT2"
    assert entered == [True]
    assert store.load().refresh_token == "RT2"


def test_missing_credentials_requires_login(store: CredentialStore) -> None:
    with pytest.raises(ReauthRequired):
        auth.get_valid_access_token(httpx.Client(), store)


def test_verify_id_token_accepts_valid(rsa_key) -> None:
    claims = auth.verify_id_token(_id_token(rsa_key), client_id="oaiapp_123", nonce="n1", jwks=_jwks(rsa_key))
    assert claims["sub"] == "user-1"


@pytest.mark.parametrize("kwargs", [{"nonce": "other"}, {"aud": "oaiapp_other"}, {"iss": "https://evil"}])
def test_verify_id_token_rejects_wrong_nonce_aud_iss(rsa_key, kwargs) -> None:
    token = _id_token(rsa_key, **kwargs)
    with pytest.raises(LoginFailed):
        auth.verify_id_token(token, client_id="oaiapp_123", nonce="n1", jwks=_jwks(rsa_key))


def _login_http(rsa_key, scope: str) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == auth.DISCOVERY_URL:
            return httpx.Response(200, json={"jwks_uri": "https://auth.openai.com/jwks"})
        if url == "https://auth.openai.com/jwks":
            return httpx.Response(200, json=_jwks(rsa_key))
        if url == auth.TOKEN_URL:
            return httpx.Response(200, json={
                "access_token": "AT-secret", "refresh_token": "RT-secret",
                "id_token": _id_token(rsa_key), "expires_in": 3600, "scope": scope,
            })
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _complete(http, store, callback):
    return auth.complete_login(
        http, store, callback=callback, expected_state="st", client_id=auth.DYNAMIC_CLIENT_ID,
        verifier="V", nonce="n1", redirect_uri="http://127.0.0.1:1/callback", host_id="urn:uuid:h",
    )


def test_complete_login_saves_issued_client(store: CredentialStore, rsa_key) -> None:
    http = _login_http(rsa_key, auth.SCOPES)
    creds = _complete(http, store, {"code": "C", "state": "st", "client_id": "oaiapp_123"})
    assert creds.client_id == "oaiapp_123"
    assert store.load().subject == "user-1"


@pytest.mark.parametrize("callback", [
    {"code": "C", "state": "wrong", "client_id": "oaiapp_123"},
    {"error": "access_denied", "state": "st"},
    {},
    {"code": "C", "state": "st"},  # registration without issued client id
])
def test_login_callback_rejects_state_mismatch(store: CredentialStore, rsa_key, callback) -> None:
    with pytest.raises(LoginFailed):
        _complete(_login_http(rsa_key, auth.SCOPES), store, callback)
    assert store.load() is None


def test_login_missing_plan_scope(store: CredentialStore, rsa_key) -> None:
    http = _login_http(rsa_key, "openid profile email offline_access")
    with pytest.raises(PlanScopeNotGranted):
        _complete(http, store, {"code": "C", "state": "st", "client_id": "oaiapp_123"})
    assert store.load() is None


def test_errors_do_not_leak_tokens(store: CredentialStore) -> None:
    creds = _creds()
    assert not any(t in repr(creds) for t in SECRET_TOKENS)
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(500, json={"error": "server_error", "echo": "RT-secret"})
    ))
    with pytest.raises(LoginFailed) as exc:
        auth.refresh(http, creds)
    assert not any(t in str(exc.value) for t in SECRET_TOKENS)


def test_exchange_invalid_grant_reports_server_description() -> None:
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
        400, json={"error": "invalid_grant", "error_description": "code_verifier mismatch"}
    )))
    with pytest.raises(LoginFailed) as exc:
        auth.exchange_code(http, client_id="oaiapp_1", code="C", verifier="V", redirect_uri="http://127.0.0.1:1/callback")
    assert "認可コードの交換" in str(exc.value)
    assert "invalid_grant: code_verifier mismatch" in str(exc.value)
    assert "Plus / Pro" in str(exc.value)


def test_verify_id_token_requires_exp(rsa_key) -> None:
    token = jwt.encode(
        {"sub": "u", "aud": "oaiapp_123", "iss": auth.ISSUER, "nonce": "n1", "iat": int(time.time())},
        rsa_key, algorithm="RS256", headers={"kid": "k1"},
    )
    with pytest.raises(LoginFailed):
        auth.verify_id_token(token, client_id="oaiapp_123", nonce="n1", jwks=_jwks(rsa_key))


def test_verify_id_token_rejects_garbage(rsa_key) -> None:
    with pytest.raises(LoginFailed):
        auth.verify_id_token("", client_id="oaiapp_123", nonce="n1", jwks=_jwks(rsa_key))


def test_non_ascii_state_is_rejected_cleanly(store: CredentialStore, rsa_key) -> None:
    with pytest.raises(LoginFailed):
        _complete(_login_http(rsa_key, auth.SCOPES), store, {"code": "C", "state": "é", "client_id": "oaiapp_123"})


def test_scope_falls_back_when_token_response_omits_it(store: CredentialStore, rsa_key) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == auth.DISCOVERY_URL:
            return httpx.Response(200, json={"jwks_uri": "https://auth.openai.com/jwks"})
        if url == "https://auth.openai.com/jwks":
            return httpx.Response(200, json=_jwks(rsa_key))
        return httpx.Response(200, json={
            "access_token": "AT", "refresh_token": "RT", "id_token": _id_token(rsa_key), "expires_in": 3600,
        })

    creds = _complete(httpx.Client(transport=httpx.MockTransport(handler)), store,
                      {"code": "C", "state": "st", "client_id": "oaiapp_123", "scope": auth.SCOPES})
    assert auth.PLAN_SCOPE in creds.scopes


def test_wait_for_callback_ignores_unrelated_requests() -> None:
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def hit() -> None:
        with httpx.Client() as c:
            assert c.get(f"{base}/favicon.ico").status_code == 404
            assert c.get(f"{base}/auth/callback?state=other&code=evil").status_code == 404
            assert c.get(f"{base}/callback?state=st&code=wrongpath").status_code == 404
            assert c.get(f"{base}/auth/callback?state=st&code=good").status_code == 200

    t = threading.Thread(target=hit)
    t.start()
    try:
        result = auth._wait_for_callback(server, 10, "st")
    finally:
        t.join()
        server.server_close()
    assert result == {"state": "st", "code": "good"}
