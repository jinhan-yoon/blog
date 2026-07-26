"""구글 계정 로그인 게이트 — 지정된 이메일 계정만 앱 접근 허용"""
from __future__ import annotations

import os
import time
import base64
import hashlib
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

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

# 브라우저가 구글로 리디렉션됐다가 돌아오면 Streamlit 세션이 새로 시작될 수 있어
# (st.session_state로는 못 들고 다님), PKCE code_verifier를 state 값 기준으로
# 서버 메모리에 잠깐 보관해 콜백에서 다시 꺼내 쓴다. 이 앱은 단일 프로세스로만 돌아가므로 충분함.
_pending_verifiers: dict[str, str] = {}

# 팝업 로그인 창에서 인증이 끝나면 원래 탭(별도 세션)도 자동으로 통과시켜야 하는데,
# Streamlit의 session_state는 탭(세션)마다 독립적이라 팝업의 인증 결과를 원래 탭이 알 수 없다.
# 이 앱은 허용 이메일이 1개뿐인 개인용 도구라는 전제 하에, 로그인 성공 시 서버 전체에
# 임시로 통행증을 발급하는 방식으로 단순화한다 (만료 시간 있음 — 무기한 아님).
GLOBAL_AUTH_TTL_SECONDS = 24 * 60 * 60  # 24시간
_global_auth: dict = {"email": None, "expires_at": 0.0}


def check_global_auth() -> str | None:
    """서버 전체 임시 인증이 유효하면 이메일 반환, 아니면 None"""
    if _global_auth["email"] and time.time() < _global_auth["expires_at"]:
        return _global_auth["email"]
    return None


def set_global_auth(email: str) -> None:
    _global_auth["email"] = email
    _global_auth["expires_at"] = time.time() + GLOBAL_AUTH_TTL_SECONDS


def clear_global_auth() -> None:
    _global_auth["email"] = None
    _global_auth["expires_at"] = 0.0


def is_configured() -> bool:
    """로그인 게이트 사용 가능 여부 (클라이언트 파일 + 허용 이메일 설정 여부)"""
    return LOGIN_CLIENT_SECRET_PATH.exists() and bool(os.getenv("ALLOWED_GOOGLE_EMAIL", ""))


def get_login_url(redirect_uri: str) -> str:
    """구글 로그인 동의 화면 URL 생성 (PKCE S256)"""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    state = secrets.token_urlsafe(16)
    _pending_verifiers[state] = code_verifier

    flow = Flow.from_client_secrets_file(str(LOGIN_CLIENT_SECRET_PATH), SCOPES, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="online",
        prompt="select_account",
        state=state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return auth_url


def complete_login(code: str, redirect_uri: str, state: str = "") -> str:
    """
    인증 코드를 교환해 로그인한 계정의 이메일을 확인.
    ALLOWED_GOOGLE_EMAIL과 일치하지 않으면 PermissionError 발생.
    """
    code_verifier = _pending_verifiers.pop(state, "")
    if not code_verifier:
        raise RuntimeError(
            "로그인 요청이 만료되었거나 서버가 재시작됐습니다. 로그인 링크를 다시 눌러 재시도해주세요."
        )

    flow = Flow.from_client_secrets_file(str(LOGIN_CLIENT_SECRET_PATH), SCOPES, redirect_uri=redirect_uri)
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
