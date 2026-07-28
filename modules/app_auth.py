"""구글 계정 로그인 게이트 — 지정된 이메일 계정만 앱 접근 허용"""
from __future__ import annotations

import os
import json
import hashlib
import hmac
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

# ── 로그인 세션 쿠키 (서버 재시작/재연결에도 로그인 유지) ──────────────────────
SESSION_COOKIE_NAME = "blog_auth_token"
SESSION_TTL_SECONDS = 30 * 24 * 3600  # 30일
OAUTH_STATE_TTL_SECONDS = 10 * 60  # 10분
_SESSION_SECRET_PATH = Path(".session_secret")
_OAUTH_STATE_PATH = Path(".oauth_states.json")


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

# ── 비밀번호 로그인 (단일 관리자용 — 구글 OAuth보다 단순하고 외부 의존성 없음) ──

def is_password_configured() -> bool:
    """비밀번호 로그인 게이트 사용 가능 여부 (.env에 APP_PASSWORD 설정 여부)"""
    return bool(os.getenv("APP_PASSWORD", ""))


def check_password(password: str) -> bool:
    """입력한 비밀번호가 APP_PASSWORD와 일치하는지 확인 (타이밍 공격 방지)."""
    correct = os.getenv("APP_PASSWORD", "")
    return bool(correct) and hmac.compare_digest(password, correct)


def make_password_session_token() -> str:
    """비밀번호 로그인 성공 시 쿠키에 저장할 서명된 토큰 생성 (만료시각 + HMAC 서명)."""
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"pwauth:{expires_at}"
    sig = hmac.new(_get_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_password_session_token(token: str | None) -> bool:
    """쿠키 토큰을 검증해 유효한 비밀번호 로그인 세션이면 True."""
    if not token:
        return False
    try:
        marker, expires_at_s, sig = token.rsplit(":", 2)
        expires_at = int(expires_at_s)
    except (ValueError, TypeError):
        return False
    if marker != "pwauth":
        return False

    payload = f"{marker}:{expires_at_s}"
    expected_sig = hmac.new(_get_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False
    if time.time() > expires_at:
        return False

    return True


os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def is_configured() -> bool:
    """구글 로그인 게이트 사용 가능 여부 (클라이언트 파일 + 허용 이메일 설정 여부)"""
    return LOGIN_CLIENT_SECRET_PATH.exists() and bool(os.getenv("ALLOWED_GOOGLE_EMAIL", ""))


def _load_oauth_states() -> dict[str, dict[str, object]]:
    if not _OAUTH_STATE_PATH.exists():
        return {}
    try:
        data = json.loads(_OAUTH_STATE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_oauth_states(states: dict[str, dict[str, object]]) -> None:
    _OAUTH_STATE_PATH.write_text(json.dumps(states, separators=(",", ":")))


def _remember_code_verifier(state: str, code_verifier: str) -> None:
    now = int(time.time())
    states = {
        k: v for k, v in _load_oauth_states().items()
        if isinstance(v, dict) and int(v.get("expires_at", 0)) > now
    }
    states[state] = {
        "code_verifier": code_verifier,
        "expires_at": now + OAUTH_STATE_TTL_SECONDS,
    }
    _save_oauth_states(states)


def _pop_code_verifier(state: str) -> str | None:
    if not state:
        return None
    now = int(time.time())
    states = _load_oauth_states()
    item = states.pop(state, None)
    states = {
        k: v for k, v in states.items()
        if isinstance(v, dict) and int(v.get("expires_at", 0)) > now
    }
    _save_oauth_states(states)
    if not isinstance(item, dict) or int(item.get("expires_at", 0)) <= now:
        return None
    code_verifier = item.get("code_verifier", "")
    return code_verifier if isinstance(code_verifier, str) and code_verifier else None


def get_login_url(redirect_uri: str) -> str:
    """구글 로그인 동의 화면 URL 생성. PKCE verifier는 서버에 10분간 보관한다."""
    code_verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    _remember_code_verifier(state, code_verifier)

    flow = Flow.from_client_secrets_file(
        str(LOGIN_CLIENT_SECRET_PATH),
        SCOPES,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    auth_url, _ = flow.authorization_url(
        access_type="online",
        prompt="select_account",
        state=state,
    )
    return auth_url


def complete_login(code: str, redirect_uri: str, state: str = "") -> str:
    """
    인증 코드를 교환해 로그인한 계정의 이메일을 확인.
    ALLOWED_GOOGLE_EMAIL과 일치하지 않으면 PermissionError 발생.
    """
    code_verifier = _pop_code_verifier(state)
    if not code_verifier:
        raise RuntimeError(
            "로그인 요청이 유효하지 않습니다. 로그인 링크를 다시 눌러 재시도해주세요."
        )

    flow = Flow.from_client_secrets_file(
        str(LOGIN_CLIENT_SECRET_PATH),
        SCOPES,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    flow.fetch_token(code=code, code_verifier=code_verifier)

    resp = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {flow.credentials.token}"},
        timeout=10,
    )
    resp.raise_for_status()
    email = resp.json().get("email", "")

    allowed = os.getenv("ALLOWED_GOOGLE_EMAIL", "").strip().lower()
    if not email or email.strip().lower() != allowed:
        raise PermissionError(f"허용되지 않은 계정입니다: {email or '(이메일 확인 실패)'}")

    return email
