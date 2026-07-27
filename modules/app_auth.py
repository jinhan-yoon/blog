"""구글 계정 로그인 게이트 — 지정된 이메일 계정만 앱 접근 허용"""
from __future__ import annotations

import os
import base64
import hashlib
import hmac
import json
import time
import secrets
from pathlib import Path
import requests
from dotenv import load_dotenv

from google_auth_oauthlib.flow import Flow

load_dotenv()

# openid+email 스코프만 요청 (Blogger 연동과 무관한 별도 로그인 전용 클라이언트)
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]
LOGIN_CLIENT_SECRET_PATH = Path("login_client_secret.json")
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# ── 로그인 세션 쿠키 (서버 재시작/재연결에도 로그인 유지) ──────────────────────
SESSION_COOKIE_NAME = "blog_auth_token"
SESSION_TTL_SECONDS = 30 * 24 * 3600  # 30일
_SESSION_SECRET_PATH = Path(".session_secret")


def _get_session_secret() -> bytes:
    """쿠키 서명용 비밀키. .env의 APP_SESSION_SECRET을 쓰거나, 없으면 로컬 파일에 1회 생성해 재사용."""
    env_secret = os.getenv("APP_SESSION_SECRET", "")
    if env_secret:
        return env_secret.encode()

    if _SESSION_SECRET_PATH.exists():
        return _SESSION_SECRET_PATH.read_text().strip().encode()

    new_secret = secrets.token_urlsafe(32)
    _SESSION_SECRET_PATH.write_text(new_secret)
    return new_secret.encode()


def make_session_token(email: str) -> str:
    """로그인 성공 시 쿠키에 저장할 서명된 토큰 생성 (email + 만료시각 + HMAC 서명)."""
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{email}:{expires_at}"
    sig = hmac.new(_get_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_session_token(token: str | None) -> str | None:
    """쿠키 토큰을 검증해 유효하면 이메일을, 아니면 None을 반환."""
    if not token:
        return None
    try:
        email, expires_at_s, sig = token.rsplit(":", 2)
        expires_at = int(expires_at_s)
    except (ValueError, TypeError):
        return None

    payload = f"{email}:{expires_at_s}"
    expected_sig = hmac.new(_get_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    if time.time() > expires_at:
        return None

    allowed = os.getenv("ALLOWED_GOOGLE_EMAIL", "").strip().lower()
    if email.strip().lower() != allowed:
        return None

    return email

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

# 인증 코드(1회용)가 짧은 시간 안에 중복 제출되는 경우(모바일 브라우저의
# 링크 프리페치, 중복 연결 등)를 대비한 결과 캐시. 같은 code가 다시 오면
# 구글 토큰 엔드포인트를 다시 호출하지 않고 캐시된 이메일을 그대로 반환해
# invalid_grant를 피한다. TTL이 짧아 예전의 "서버 재시작 때문에 로그인
# 요청이 만료" 문제(별도 원인)와는 무관하다.
_code_result_cache: dict[str, tuple[str, float]] = {}
_CODE_CACHE_TTL = 120  # seconds


def is_configured() -> bool:
    """로그인 게이트 사용 가능 여부 (클라이언트 파일 + 허용 이메일 설정 여부)"""
    return LOGIN_CLIENT_SECRET_PATH.exists() and bool(os.getenv("ALLOWED_GOOGLE_EMAIL", ""))


def get_login_url(redirect_uri: str) -> str:
    """
    구글 로그인 동의 화면 URL 생성 (PKCE S256).

    code_verifier는 OAuth state 파라미터에 그대로 실어 보낸다 (서버 메모리에
    따로 보관하지 않음). 브라우저가 구글로 갔다 돌아오는 사이 Streamlit
    서버가 재시작되거나 세션이 여러 번 재실행돼도, 콜백에 돌아온 state 값을
    그대로 code_verifier로 재사용하면 되므로 "로그인 요청 만료" 문제가 없다.
    이 앱은 최종적으로 ALLOWED_GOOGLE_EMAIL 하나만 허용하므로 state 노출로
    인한 보안 손실은 미미하다.
    """
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )

    flow = Flow.from_client_secrets_file(str(LOGIN_CLIENT_SECRET_PATH), SCOPES, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="online",
        prompt="select_account",
        state=code_verifier,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return auth_url


def _load_client_id_secret() -> tuple[str, str]:
    data = json.loads(LOGIN_CLIENT_SECRET_PATH.read_text())
    section = data.get("web") or data.get("installed") or {}
    return section.get("client_id", ""), section.get("client_secret", "")


def complete_login(code: str, redirect_uri: str, state: str = "") -> str:
    """
    인증 코드를 교환해 로그인한 계정의 이메일을 확인.
    ALLOWED_GOOGLE_EMAIL과 일치하지 않으면 PermissionError 발생.
    """
    cached = _code_result_cache.get(code)
    if cached and time.time() - cached[1] < _CODE_CACHE_TTL:
        return cached[0]

    code_verifier = state
    if not code_verifier:
        raise RuntimeError(
            "로그인 요청이 유효하지 않습니다. 로그인 링크를 다시 눌러 재시도해주세요."
        )

    # google_auth_oauthlib의 Flow.fetch_token()은 실패 시 구글이 실제로 보낸
    # 원본 오류(예: error_description)를 감추고 "Bad Request" 같은 뭉뚱그린
    # 메시지만 노출해서, requests로 토큰 엔드포인트를 직접 호출해 구글의
    # 원본 응답을 그대로 확인할 수 있게 한다.
    client_id, client_secret = _load_client_id_secret()
    token_resp = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        },
        timeout=15,
    )
    if not token_resp.ok:
        raise RuntimeError(f"토큰 교환 실패 [{token_resp.status_code}] {token_resp.text[:500]}")

    access_token = token_resp.json().get("access_token", "")
    if not access_token:
        raise RuntimeError(f"토큰 교환 응답에 access_token이 없습니다: {token_resp.text[:500]}")

    resp = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    email = resp.json().get("email", "")

    allowed = os.getenv("ALLOWED_GOOGLE_EMAIL", "").strip().lower()
    if not email or email.strip().lower() != allowed:
        raise PermissionError(f"허용되지 않은 계정입니다: {email or '(이메일 확인 실패)'}")

    now = time.time()
    _code_result_cache[code] = (email, now)
    for k, (_, cached_at) in list(_code_result_cache.items()):
        if now - cached_at > _CODE_CACHE_TTL:
            del _code_result_cache[k]

    return email
