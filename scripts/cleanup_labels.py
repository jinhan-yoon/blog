"""기존 Blogger 게시글의 라벨을 고정 카테고리로 일괄 정리하는 1회성 스크립트.

각 글 제목을 LLM으로 CATEGORIES 중 하나로 분류한 뒤, 그 글의 라벨을
[카테고리] 하나로 교체한다 (기존에 쌓인 자유형 태그 제거).

실행 (서버에서):
    venv/bin/python scripts/cleanup_labels.py --dry-run   # 미리보기만
    venv/bin/python scripts/cleanup_labels.py              # 실제 반영
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from googleapiclient.discovery import build

from modules.blogger_publisher import _get_credentials
from modules.content_generator import CATEGORIES, _generate

load_dotenv()


def classify_category(title: str) -> str:
    category_list = ", ".join(CATEGORIES)
    prompt = f"""다음 블로그 글 제목을 아래 카테고리 중 정확히 하나로 분류해주세요.

카테고리: {category_list}

제목: {title}

반드시 카테고리 이름 중 하나만 그대로 출력하세요. 다른 설명 없이."""
    text = _generate(prompt).strip()
    for cat in CATEGORIES:
        if cat in text:
            return cat
    return CATEGORIES[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="실제로 반영하지 않고 결과만 출력")
    args = parser.parse_args()

    blog_id = os.getenv("BLOGGER_BLOG_ID", "")
    if not blog_id:
        raise SystemExit("BLOGGER_BLOG_ID가 설정되지 않았습니다.")

    creds = _get_credentials()
    service = build("blogger", "v3", credentials=creds)

    posts: list[dict] = []
    request = service.posts().list(blogId=blog_id, maxResults=500, fetchBodies=False)
    while request is not None:
        response = request.execute()
        posts.extend(response.get("items", []))
        request = service.posts().list_next(request, response)

    print(f"총 {len(posts)}개 게시글 발견\n")

    for post in posts:
        title = post.get("title", "")
        old_labels = post.get("labels", [])
        category = classify_category(title)

        print(f"- {title}")
        print(f"    기존 라벨({len(old_labels)}개): {old_labels}")
        print(f"    새 카테고리: {category}")

        if not args.dry_run:
            service.posts().patch(
                blogId=blog_id,
                postId=post["id"],
                body={"labels": [category]},
            ).execute()

    print("\n(dry-run — 실제 반영 안 함)" if args.dry_run else "\n완료 — 모든 게시글 라벨 정리됨")


if __name__ == "__main__":
    main()
