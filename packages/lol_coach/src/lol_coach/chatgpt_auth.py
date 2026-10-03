"""Sign in with ChatGPT for open-source / local apps (OAuth 2.0 + PKCE).

Spec: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
"""

from __future__ import annotations

import base64
import hashlib
import os
import sys
import secrets
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import jwt

from lol_coach.errors import LoginFailed, PlanScopeNotGranted, ReauthRequired
from lol_coach.store import Credentials, CredentialStore

ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = f"{ISSUER}/api/accounts/authorize"
TOKEN_URL = f"{ISSUER}/api/accounts/oauth/token"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = f"openid profile email offline_access resource.invoke {PLAN_SCOPE}"
DYNAMIC_CLIENT_ID = "dynamic_agent_client"
AGENT_NAME = "lol-tools"
# ChatGPT only accepts http://127.0.0.1:<any port>/auth/callback for local apps
# (same as the TanStack AI and pi reference implementations).
CALLBACK_PATH = "/auth/callback"
REFRESH_MARGIN_SECONDS = 60


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    id_token: str
    expires_in: int
    scopes: list[str]

    def __repr__(self) -> str:
        return f"TokenSet(expires_in={self.expires_in!r}, scopes={self.scopes!r})"


def pkce_pair() -> tuple[str, str]:
    """Return (verifier, S256 challenge), base64url without padding."""
    verifier = secrets.token_urlsafe(32)  # 43 chars, same as the reference SDKs
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_challenge: str,
    host_id: str,
    register: bool,
) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
        "ext_agent_host_id": host_id,
    }
    if register:
        params["agent_name_hint"] = AGENT_NAME
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _token_request(http: httpx.Client, data: dict[str, str]) -> dict:
    is_refresh = data.get("grant_type") == "refresh_token"
    try:
        resp = http.post(TOKEN_URL, data=data, headers={"Accept": "application/json"})
    except httpx.HTTPError as e:
        raise LoginFailed(f"トークンエンドポイントに接続できませんでした（{type(e).__name__}）。") from None
    if resp.status_code != 200:
        _debug(f"token endpoint HTTP {resp.status_code} body={resp.text[:500]!r}")
        error, description = _oauth_error(resp)
        detail = f"HTTP {resp.status_code}, {error or 'unknown'}" + (f": {description}" if description else "")
        if is_refresh and error == "invalid_grant":
            raise ReauthRequired("ChatGPT のサインインが無効になりました。`lol-tools auth chatgpt login` で再ログインしてください。")
        step = "トークン更新" if is_refresh else "認可コードの交換"
        message = f"{step}に失敗しました（{detail}）。"
        if not is_refresh and error == "invalid_grant":
            # Observed with a Free account: consent succeeds, the exchange is rejected.
            message += (
                "\nChatGPT プランの利用は Plus / Pro が対象です。Free などの対象外プランではこのエラーになります。"
                "対象プランの場合は、時間をおいて再度ログインしてください。"
            )
        raise LoginFailed(message)
    try:
        body = resp.json()
    except ValueError:
        raise LoginFailed("トークンエンドポイントの応答を解釈できませんでした。") from None
    if not isinstance(body, dict) or "access_token" not in body:
        raise LoginFailed("トークンエンドポイントの応答に access_token がありません。")
    return body


def _debug(message: str) -> None:
    """Diagnostics for `LOL_TOOLS_DEBUG_AUTH=1`. Never pass tokens, codes or verifiers here."""
    if os.environ.get("LOL_TOOLS_DEBUG_AUTH"):
        print(f"[auth debug] {message}", file=sys.stderr)


def _oauth_error(resp: httpx.Response) -> tuple[str | None, str | None]:
    """Return (error, error_description). Descriptions are short server messages, not tokens."""
    try:
        body = resp.json()
    except ValueError:
        return None, None
    if not isinstance(body, dict):
        return None, None
    error = body.get("error")
    if isinstance(error, dict):  # some OpenAI endpoints nest the error object
        return error.get("code") or error.get("type"), _short(error.get("message"))
    return error, _short(body.get("error_description"))


def _short(value: object, limit: int = 200) -> str | None:
    if not value:
        return None
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _to_token_set(
    body: dict, *, previous_id_token: str = "", previous_refresh_token: str = "",
    fallback_scopes: list[str] | None = None,
) -> TokenSet:
    scope = body.get("scope")
    scopes = sorted(str(scope).split()) if scope else sorted(fallback_scopes or [])
    return TokenSet(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token") or previous_refresh_token,
        id_token=body.get("id_token") or previous_id_token,
        expires_in=int(body.get("expires_in", 3600)),
        scopes=scopes,
    )


def exchange_code(
    http: httpx.Client, *, client_id: str, code: str, verifier: str, redirect_uri: str,
    fallback_scopes: list[str] | None = None,
) -> TokenSet:
    body = _token_request(
        http,
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "resource": RESOURCE,
        },
    )
    tokens = _to_token_set(body, fallback_scopes=fallback_scopes)
    if not tokens.refresh_token:
        raise LoginFailed("refresh token が発行されませんでした。")
    return tokens


def refresh(http: httpx.Client, creds: Credentials) -> Credentials:
    """Refresh with the issued client id (never the dynamic one)."""
    body = _token_request(
        http,
        {
            "grant_type": "refresh_token",
            "client_id": creds.client_id,
            "refresh_token": creds.refresh_token,
            "resource": RESOURCE,
        },
    )
    tokens = _to_token_set(
        body, previous_id_token=creds.id_token, previous_refresh_token=creds.refresh_token,
        fallback_scopes=creds.scopes,
    )
    return Credentials(
        subject=creds.subject,
        client_id=creds.client_id,
        ext_agent_host_id=creds.ext_agent_host_id,
        id_token=tokens.id_token,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_at=time.time() + tokens.expires_in,
        scopes=tokens.scopes or creds.scopes,
    )


def discover(http: httpx.Client) -> dict:
    try:
        resp = http.get(DISCOVERY_URL)
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        raise LoginFailed(f"OpenID 設定を取得できませんでした（{type(e).__name__}）。") from None
    if not isinstance(body, dict):
        raise LoginFailed("OpenID 設定の形式が不正です。")
    return body


def fetch_jwks(http: httpx.Client) -> dict:
    jwks_uri = discover(http).get("jwks_uri")
    if not jwks_uri:
        raise LoginFailed("OpenID 設定に jwks_uri がありません。")
    try:
        resp = http.get(jwks_uri)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as e:
        raise LoginFailed(f"署名鍵を取得できませんでした（{type(e).__name__}）。") from None


def revoke(http: httpx.Client, creds: Credentials) -> bool:
    """Return True only when the server confirmed revocation."""
    try:
        endpoint = discover(http).get("revocation_endpoint")
    except LoginFailed:
        return False
    try:
        if not endpoint:
            return False
        resp = http.post(
            endpoint,
            data={
                "token": creds.refresh_token,
                "token_type_hint": "refresh_token",
                "client_id": creds.client_id,
            },
        )
    except httpx.HTTPError:
        return False
    return resp.status_code == 200


ID_TOKEN_ALGORITHMS = ["RS256"]


def verify_id_token(id_token: str, *, client_id: str, nonce: str, jwks: dict) -> dict:
    try:
        header = jwt.get_unverified_header(id_token)
        keys = jwt.PyJWKSet.from_dict(jwks)
        key = next((k for k in keys.keys if k.key_id == header.get("kid")), None)
        if key is None:
            raise LoginFailed("ID トークンの署名鍵が見つかりません。")
        claims = jwt.decode(
            id_token,
            key=key.key,
            algorithms=ID_TOKEN_ALGORITHMS,  # never trust the header's alg
            audience=client_id,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except LoginFailed:
        raise
    except (jwt.PyJWTError, TypeError, ValueError) as e:
        raise LoginFailed(f"ID トークンの検証に失敗しました: {type(e).__name__}") from None
    if claims.get("nonce") != nonce:
        raise LoginFailed("ID トークンの nonce が一致しません。")
    return claims


def _same(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _wait_for_callback(server: HTTPServer, timeout: float, expected_state: str) -> dict[str, str]:
    """Wait for the callback carrying our state; ignore unrelated requests."""
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        timeout = 5  # a browser pre-connect must not block the loop

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            if parsed.path != CALLBACK_PATH or not _same(params.get("state", ""), expected_state):
                self.send_response(404)
                self.end_headers()
                return
            result.update(params)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<p>lol-tools: サインインが完了しました。このタブは閉じて構いません。</p>".encode()
            )

        def log_message(self, *args: object) -> None:  # keep codes out of stderr
            return

    server.RequestHandlerClass = Handler
    server.timeout = 1
    deadline = time.monotonic() + timeout
    while not result and time.monotonic() < deadline:
        server.handle_request()
    return result


def complete_login(
    http: httpx.Client,
    store: CredentialStore,
    *,
    callback: dict[str, str],
    expected_state: str,
    client_id: str,
    verifier: str,
    nonce: str,
    redirect_uri: str,
    host_id: str,
) -> Credentials:
    if not callback:
        raise LoginFailed("サインインがタイムアウトしました。")
    if callback.get("error"):
        raise LoginFailed(f"サインインが拒否されました（{callback['error']}）。")
    if not _same(callback.get("state", ""), expected_state):
        raise LoginFailed("state が一致しません。もう一度ログインしてください。")
    if "code" not in callback:
        names = ", ".join(sorted(callback)) or "なし"
        raise LoginFailed(f"認可コードが返されませんでした（コールバックのパラメータ: {names}）。")

    # New registrations return the issued client id (oaiapp_...) on the callback.
    issued_client_id = callback.get("client_id") or client_id
    if issued_client_id == DYNAMIC_CLIENT_ID:
        names = ", ".join(sorted(callback))
        raise LoginFailed(f"発行済み client_id が返されませんでした（コールバックのパラメータ: {names}）。")

    _debug(
        f"callback params={sorted(callback)} client_id={issued_client_id[:7]}… "
        f"redirect_uri={redirect_uri} code_len={len(callback['code'])} verifier_len={len(verifier)}"
    )
    tokens = exchange_code(
        http,
        client_id=issued_client_id,
        code=callback["code"],
        verifier=verifier,
        redirect_uri=redirect_uri,
        fallback_scopes=(callback.get("scope") or SCOPES).split(),
    )
    if PLAN_SCOPE not in tokens.scopes:
        raise PlanScopeNotGranted(
            "ChatGPT プランの利用が許可されませんでした。同意画面でプラン利用を許可して再ログインしてください。"
        )
    jwks = fetch_jwks(http)
    claims = verify_id_token(tokens.id_token, client_id=issued_client_id, nonce=nonce, jwks=jwks)

    creds = Credentials(
        subject=str(claims["sub"]),
        client_id=issued_client_id,
        ext_agent_host_id=host_id,
        id_token=tokens.id_token,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_at=time.time() + tokens.expires_in,
        scopes=tokens.scopes,
    )
    store.save(creds)
    return creds


def login(
    http: httpx.Client,
    store: CredentialStore,
    *,
    open_browser: Callable[[str], object] = webbrowser.open,
    on_url: Callable[[str], object] | None = None,
    timeout: float = 300,
) -> Credentials:
    host_id = store.host_id()
    client_id = store.issued_client_id() or DYNAMIC_CLIENT_ID
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        redirect_uri = f"http://127.0.0.1:{server.server_address[1]}{CALLBACK_PATH}"
        url = build_authorize_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            code_challenge=challenge,
            host_id=host_id,
            register=client_id == DYNAMIC_CLIENT_ID,
        )
        if on_url:
            on_url(url)
        open_browser(url)
        callback = _wait_for_callback(server, timeout, state)
    finally:
        server.server_close()

    return complete_login(
        http,
        store,
        callback=callback,
        expected_state=state,
        client_id=client_id,
        verifier=verifier,
        nonce=nonce,
        redirect_uri=redirect_uri,
        host_id=host_id,
    )


def get_valid_access_token(
    http: httpx.Client, store: CredentialStore, *, now: Callable[[], float] = time.time
) -> str:
    creds = store.load()
    if creds is None:
        raise ReauthRequired("ChatGPT にログインしていません。`lol-tools auth chatgpt login` を実行してください。")
    if now() < creds.expires_at - REFRESH_MARGIN_SECONDS:
        return creds.access_token
    with store.lock():
        # Another process may have refreshed while we waited for the lock.
        creds = store.load()
        if creds is None:
            raise ReauthRequired("ChatGPT にログインしていません。`lol-tools auth chatgpt login` を実行してください。")
        if now() < creds.expires_at - REFRESH_MARGIN_SECONDS:
            return creds.access_token
        try:
            creds = refresh(http, creds)
        except ReauthRequired:
            store.clear_tokens()
            raise
        store.save(creds)
        return creds.access_token
