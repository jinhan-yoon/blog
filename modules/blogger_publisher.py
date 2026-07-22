"""Google Blogger API v3 연동 모듈"""
from __future__ import annotations

import os
import json
from pathlib import Path
from dotenv import load_dotenv

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/blogger"]
TOKEN_PATH = Path("token.json")
CLIENT_SECRET_PATH = Path("client_secret.json")

# localhost OAuth 허용 (HTTP)
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def _get_credentials() -> Credentials:
    """OAuth 2.0 인증 토큰 로드 또는 갱신"""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError(
                "OAuth 토큰이 없습니다. 설정 탭 > Google OAuth 인증 섹션에서 "
                "인증을 완료해주세요."
            )

    return creds


def get_client_type() -> str:
    """client_secret.json의 클라이언트 타입 반환: 'installed' 또는 'web'"""
    if not CLIENT_SECRET_PATH.exists():
        return "unknown"
    try:
        with open(CLIENT_SECRET_PATH) as f:
            data = json.load(f)
        if "installed" in data:
            return "installed"
        if "web" in data:
            return "web"
    except Exception:
        pass
    return "unknown"


def get_oauth_url(redirect_uri: str = "http://localhost") -> dict:
    """
    서버 환경용 OAuth 인증 URL 생성 (PKCE S256 방식).

    Returns:
        {"url": str, "code_verifier": str}
        code_verifier는 complete_oauth() 호출 시 반드시 전달해야 함.
    """
    import hashlib
    import base64
    import secrets as _sec

    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError("client_secret.json 파일이 없습니다.")

    # PKCE 파라미터 생성
    code_verifier = _sec.token_urlsafe(96)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )

    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH), SCOPES, redirect_uri=redirect_uri
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return {"url": auth_url, "code_verifier": code_verifier}


def complete_oauth(
    code_or_url: str,
    redirect_uri: str = "http://localhost",
    code_verifier: str = "",
) -> None:
    """
    인증 코드 또는 리다이렉트 URL로 OAuth 완료 및 token.json 저장.

    Args:
        code_or_url: 구글이 리다이렉트한 전체 URL (http://localhost/?code=xxx...)
                     또는 code= 값만 붙여넣어도 됩니다.
        redirect_uri: get_oauth_url() 에서 사용한 redirect_uri와 동일해야 함.
        code_verifier: get_oauth_url() 반환값의 code_verifier 값.
    """
    from urllib.parse import urlparse, parse_qs

    raw = code_or_url.strip()

    if raw.startswith("http"):
        parsed_params = parse_qs(urlparse(raw).query)
        if "error" in parsed_params:
            raise ValueError(f"Google 인증 오류: {parsed_params['error'][0]}")
        code = parsed_params.get("code", [""])[0]
        if not code:
            raise ValueError(
                "URL에서 인증 코드를 찾을 수 없습니다.\n"
                "브라우저 주소창의 전체 URL을 복사해 붙여넣어 주세요."
            )
    else:
        code = raw

    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH), SCOPES, redirect_uri=redirect_uri
    )

    fetch_kwargs: dict = {"code": code}
    if code_verifier:
        fetch_kwargs["code_verifier"] = code_verifier

    flow.fetch_token(**fetch_kwargs)

    with open(TOKEN_PATH, "w") as f:
        f.write(flow.credentials.to_json())


def get_blog_info(blog_id: str | None = None) -> dict:
    """블로그 기본 정보 조회"""
    blog_id = blog_id or os.getenv("BLOGGER_BLOG_ID", "")
    if not blog_id:
        raise ValueError("BLOGGER_BLOG_ID가 설정되지 않았습니다.")

    creds = _get_credentials()
    service = build("blogger", "v3", credentials=creds)
    blog = service.blogs().get(blogId=blog_id).execute()
    return blog


def publish_post(
    title: str,
    content_html: str,
    tags: list[str] | None = None,
    blog_id: str | None = None,
    is_draft: bool = False,
) -> dict:
    """
    Blogger에 포스팅 발행

    Args:
        is_draft: True면 임시저장, False면 즉시 발행

    Returns:
        발행된 포스트 정보 (url, id 등)
    """
    blog_id = blog_id or os.getenv("BLOGGER_BLOG_ID", "")
    if not blog_id:
        raise ValueError("BLOGGER_BLOG_ID가 설정되지 않았습니다.")

    creds = _get_credentials()
    service = build("blogger", "v3", credentials=creds)

    body = {
        "kind": "blogger#post",
        "title": title,
        "content": content_html,
    }
    if tags:
        body["labels"] = tags

    result = service.posts().insert(
        blogId=blog_id,
        body=body,
        isDraft=is_draft,
    ).execute()

    return {
        "id": result.get("id"),
        "url": result.get("url"),
        "title": result.get("title"),
        "status": result.get("status"),
        "published": result.get("published"),
    }


def list_recent_posts(blog_id: str | None = None, max_results: int = 10) -> list[dict]:
    """최근 포스팅 목록 조회"""
    blog_id = blog_id or os.getenv("BLOGGER_BLOG_ID", "")
    if not blog_id:
        raise ValueError("BLOGGER_BLOG_ID가 설정되지 않았습니다.")

    creds = _get_credentials()
    service = build("blogger", "v3", credentials=creds)

    result = service.posts().list(
        blogId=blog_id,
        maxResults=max_results,
        status=["live", "draft"],
    ).execute()

    posts = result.get("items", [])
    return [
        {
            "id": p.get("id"),
            "title": p.get("title"),
            "url": p.get("url"),
            "status": p.get("status"),
            "published": p.get("published", ""),
        }
        for p in posts
    ]


def check_auth_status() -> dict:
    """인증 상태 확인"""
    has_secret = CLIENT_SECRET_PATH.exists()
    has_token = TOKEN_PATH.exists()
    blog_id = os.getenv("BLOGGER_BLOG_ID", "")

    status = {
        "client_secret": has_secret,
        "token": has_token,
        "blog_id": bool(blog_id),
        "ready": has_secret and has_token and bool(blog_id),
    }

    if has_token:
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            status["token_valid"] = creds.valid
            status["token_expired"] = creds.expired
        except Exception:
            status["token_valid"] = False
            status["token_expired"] = True

    return status


def test_blog_connection(blog_id: str | None = None) -> dict:
    """
    Blogger API 연결 및 블로그 ID 유효성 테스트.
    Returns: {"ok": bool, "blog_name": str, "blog_url": str, "error": str}
    """
    blog_id = (blog_id or os.getenv("BLOGGER_BLOG_ID", "")).strip()
    if not blog_id:
        return {"ok": False, "error": "블로그 ID가 설정되지 않았습니다."}
    try:
        creds = _get_credentials()
        service = build("blogger", "v3", credentials=creds)
        blog = service.blogs().get(blogId=blog_id).execute()
        return {
            "ok": True,
            "blog_name": blog.get("name", ""),
            "blog_url": blog.get("url", ""),
            "posts": blog.get("posts", {}).get("totalItems", 0),
            "error": None,
        }
    except Exception as e:
        err = str(e)
        if "HttpError 403" in err or "forbidden" in err.lower():
            hint = "권한 없음 — 이 블로그의 소유자 계정으로 OAuth 인증했는지 확인하세요."
        elif "HttpError 404" in err or "not found" in err.lower():
            hint = "블로그 ID를 찾을 수 없습니다 — ID가 정확한지 확인하세요."
        elif "OAuth" in err or "token" in err.lower():
            hint = "OAuth 토큰 오류 — 설정 탭에서 재인증해주세요."
        else:
            hint = err
        return {"ok": False, "error": hint}
