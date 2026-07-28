"""구글 로그인(OAuth) 문제 디버그용 — 앱을 거치지 않고 터미널에서 직접 각 단계를 확인.

사용법:
    python debug_google_login.py

1) 이 스크립트가 인증 URL을 출력하면, 실제 브라우저(본인 PC)에서 열고
   구글 계정으로 로그인/동의하세요.
2) 로그인 후 리디렉션된 주소창의 전체 URL을 그대로 복사해서 터미널에 붙여넣으세요.
3) 스크립트가 구글 토큰 엔드포인트를 직접 호출해서, 앱 화면에는 안 나오는
   전체 응답(상태 코드/헤더/본문)을 그대로 보여줍니다.

login_client_secret.json이 현재 폴더(또는 blog/)에 있어야 합니다.
서버에 SSH로 접속해 blog 폴더에서 실행하거나, 같은 파일을 로컬에 두고 실행해도 됩니다.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import base64
import hashlib
import json
import secrets
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests

LOGIN_CLIENT_SECRET_PATH = Path("login_client_secret.json")
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = "openid https://www.googleapis.com/auth/userinfo.email"


def main() -> None:
    if not LOGIN_CLIENT_SECRET_PATH.exists():
        print(f"❌ {LOGIN_CLIENT_SECRET_PATH.resolve()} 파일이 없습니다. 이 스크립트를 blog 폴더에서 실행해주세요.")
        return

    data = json.loads(LOGIN_CLIENT_SECRET_PATH.read_text())
    section = data.get("web") or data.get("installed") or {}
    client_id = section.get("client_id", "")
    client_secret = section.get("client_secret", "")
    if not client_id or not client_secret:
        print("❌ login_client_secret.json에서 client_id/client_secret을 못 찾았습니다.")
        return

    print(f"client_id: {client_id}")
    print(f"client_secret: {client_secret[:6]}...{client_secret[-4:]} (길이 {len(client_secret)})")

    redirect_uri = input("\n리디렉션 URI [기본값 https://blog.superip.net]: ").strip() or "https://blog.superip.net"

    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    print(f"\n생성한 code_verifier (길이 {len(code_verifier)}): {code_verifier}")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "online",
        "prompt": "select_account",
        "state": code_verifier,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTH_URL}?{urlencode(params)}"

    print("\n" + "=" * 70)
    print("1) 아래 URL을 실제 브라우저에서 열고 로그인/동의하세요:")
    print(auth_url)
    print("=" * 70)

    redirected = input("\n2) 로그인 후 리디렉션된 주소창의 전체 URL을 붙여넣으세요:\n> ").strip()

    qs = parse_qs(urlparse(redirected).query)
    code = qs.get("code", [""])[0]
    returned_state = qs.get("state", [""])[0]
    error = qs.get("error", [""])[0]

    if error:
        print(f"\n❌ 구글이 인증 단계에서부터 에러를 반환했습니다: {error}")
        print(f"   전체 쿼리: {qs}")
        return

    if not code:
        print("\n❌ URL에서 code를 못 찾았습니다. 붙여넣은 URL을 확인해주세요.")
        print(f"   파싱된 쿼리: {qs}")
        return

    print(f"\ncode (길이 {len(code)}): {code[:20]}...")
    print(f"돌아온 state (길이 {len(returned_state)}): {returned_state[:20]}...")
    print(f"state == 우리가 만든 code_verifier?: {returned_state == code_verifier}")

    print("\n" + "=" * 70)
    print("3) 토큰 엔드포인트 직접 호출 중...")
    resp = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": returned_state,
        },
        timeout=15,
    )
    print(f"status_code: {resp.status_code}")
    print("headers:")
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")
    print("body:")
    print(resp.text)
    print("=" * 70)

    if resp.ok:
        print("\n✅ 토큰 교환 성공!")
    else:
        print("\n❌ 토큰 교환 실패. 위 body의 error/error_description을 확인하세요.")


if __name__ == "__main__":
    main()
