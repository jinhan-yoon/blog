"""네이버 블로그 API 연동 모듈"""
from __future__ import annotations

import os
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from dotenv import load_dotenv

load_dotenv()

NAVER_TOKEN_PATH = Path("naver_token.json")
AUTH_URL   = "https://nid.naver.com/oauth2.0/authorize"
TOKEN_URL  = "https://nid.naver.com/oauth2.0/token"
BLOG_API   = "https://openapi.naver.com/blog/writePost.json"


def _client() -> tuple[str, str]:
    client_id     = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 설정되지 않았습니다.")
    return client_id, client_secret


def get_oauth_url(redirect_uri: str = "http://localhost") -> dict:
    """
    네이버 OAuth 인증 URL 생성.
    Returns: {"url": str, "state": str}
    """
    client_id, _ = _client()
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "state":         state,
    }
    url = AUTH_URL + "?" + urlencode(params)
    return {"url": url, "state": state}


def complete_oauth(
    code_or_url: str,
    state: str = "",
    redirect_uri: str = "http://localhost",
) -> None:
    """
    인증 코드 또는 리다이렉트 URL로 OAuth 완료 및 naver_token.json 저장.
    """
    client_id, client_secret = _client()

    raw = code_or_url.strip()
    if raw.startswith("http"):
        parsed_params = parse_qs(urlparse(raw).query)
        if "error" in parsed_params:
            raise ValueError(f"네이버 인증 오류: {parsed_params['error'][0]}")
        code = parsed_params.get("code", [""])[0]
        if not code:
            raise ValueError("URL에서 인증 코드를 찾을 수 없습니다.")
    else:
        code = raw

    params = {
        "grant_type":    "authorization_code",
        "client_id":     client_id,
        "client_secret": client_secret,
        "code":          code,
        "state":         state,
    }
    resp = requests.post(TOKEN_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise ValueError(f"토큰 발급 실패: {data.get('error_description', data['error'])}")

    data["saved_at"] = time.time()
    with open(NAVER_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_access_token() -> str:
    """저장된 access_token 반환, 만료 시 refresh"""
    if not NAVER_TOKEN_PATH.exists():
        raise RuntimeError("네이버 OAuth 토큰이 없습니다. 설정 탭에서 인증을 완료해주세요.")

    with open(NAVER_TOKEN_PATH, encoding="utf-8") as f:
        data = json.load(f)

    expires_in = int(data.get("expires_in", 3600))
    saved_at   = float(data.get("saved_at", 0))
    if time.time() - saved_at < expires_in - 60:
        return data["access_token"]

    # 만료 → refresh
    client_id, client_secret = _client()
    refresh_token = data.get("refresh_token", "")
    if not refresh_token:
        raise RuntimeError("refresh_token이 없습니다. 재인증이 필요합니다.")

    params = {
        "grant_type":    "refresh_token",
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    resp = requests.post(TOKEN_URL, params=params, timeout=15)
    resp.raise_for_status()
    new_data = resp.json()
    if "error" in new_data:
        raise RuntimeError(f"토큰 갱신 실패: {new_data.get('error_description', new_data['error'])}")

    new_data["refresh_token"] = refresh_token
    new_data["saved_at"] = time.time()
    with open(NAVER_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    return new_data["access_token"]


def publish_post(
    title: str,
    content_html: str,
    tags: list[str] | None = None,
) -> dict:
    """
    네이버 블로그에 포스팅 발행.
    Returns: {"ok": bool, "url": str, "error": str|None}
    """
    access_token = _get_access_token()

    tag_str = ",".join((tags or [])[:10])

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/x-www-form-urlencoded; charset=UTF-8",
    }
    body = {
        "title":    title,
        "contents": content_html,
        "tags":     tag_str,
    }

    resp = requests.post(BLOG_API, headers=headers, data=body, timeout=30)

    if resp.status_code == 200:
        result = resp.json()
        return {
            "ok":    True,
            "url":   result.get("blogUrl", ""),
            "error": None,
        }
    else:
        try:
            err = resp.json()
            msg = err.get("errorMessage") or err.get("message") or resp.text[:200]
        except Exception:
            msg = resp.text[:200]

        if resp.status_code == 401:
            msg = "인증 만료 — 설정 탭에서 네이버 재인증하세요."
        elif resp.status_code == 403:
            msg = "권한 없음 — 네이버 앱에 blog 권한이 있는지 확인하세요."

        return {"ok": False, "url": "", "error": msg}


def check_auth_status() -> dict:
    """네이버 인증 상태 확인"""
    client_id     = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    has_token = NAVER_TOKEN_PATH.exists()

    status = {
        "client_id":     bool(client_id),
        "client_secret": bool(client_secret),
        "token":         has_token,
        "ready":         bool(client_id) and bool(client_secret) and has_token,
    }

    if has_token:
        try:
            with open(NAVER_TOKEN_PATH, encoding="utf-8") as f:
                data = json.load(f)
            expires_in = int(data.get("expires_in", 3600))
            saved_at   = float(data.get("saved_at", 0))
            status["token_valid"] = (time.time() - saved_at) < (expires_in - 60)
        except Exception:
            status["token_valid"] = False

    return status
