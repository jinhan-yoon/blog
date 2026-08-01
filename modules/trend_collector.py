"""당일 IT 트렌드 키워드 수집 모듈 - Google News IT/테크 토픽 RSS(한국어)"""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from datetime import datetime


# ── IT/테크 뉴스 트렌드 (블로그가 IT 분야에 집중하기로 하여 이걸 기본 소스로 사용) ──
def get_it_trends_rss(limit: int = 40) -> list[dict]:
    """Google News IT/테크 토픽 RSS(한국어)에서 최신 IT 트렌드 헤드라인 수집"""
    url = "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(
            url, params={"hl": "ko", "gl": "KR", "ceid": "KR:ko"}, headers=headers, timeout=15
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml-xml")
        items = soup.find_all("item")

        results = []
        for i, item in enumerate(items[:limit]):
            title_tag = item.find("title")
            source_tag = item.find("source")
            if not title_tag or not title_tag.text.strip():
                continue
            title = title_tag.text.strip()
            source_name = source_tag.text.strip() if source_tag else ""
            # Google News 제목은 보통 "헤드라인 - 매체명" 형식이라 매체명은 분리해서 traffic에 넣는다
            if source_name and title.endswith(f" - {source_name}"):
                title = title[: -(len(source_name) + 3)].strip()
            results.append({
                "rank": i + 1,
                "keyword": title,
                "traffic": source_name,
                "caret": "",
                "source": "IT뉴스",
            })
        return results
    except Exception:
        return []


# ── 통합 수집 ────────────────────────────────────────────────────────────────
def collect_all_trends() -> dict:
    """IT/테크 뉴스 트렌드 수집 (블로그가 IT 분야에 집중하기로 하여 IT 소스만 사용)"""
    it_news = get_it_trends_rss()

    seen: set[str] = set()
    merged = []
    for kw in it_news:
        if kw["keyword"] and kw["keyword"] not in seen:
            seen.add(kw["keyword"])
            merged.append(kw)

    return {
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "it_news": it_news,
        "merged": merged,
    }
