"""Google Blogger API v3 연동 모듈"""

import os
import json
import pickle
from pathlib import Path
from dotenv import load_dotenv

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/blogger"]
TOKEN_PATH = Path("token.json")
CLIENT_SECRET_PATH = Path("client_secret.json")


def _get_credentials() -> Credentials:
    """OAuth 2.0 인증 토큰 로드 또는 갱신"""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_PATH.exists():
                raise FileNotFoundError(
                    "client_secret.json 파일이 없습니다. "
                    "Google Cloud Console에서 OAuth 2.0 클라이언트 ID를 다운로드하여 "
                    "프로젝트 루트에 저장해주세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


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
