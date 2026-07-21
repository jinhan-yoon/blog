"""당일 트렌드 키워드 수집 모듈 - 로워드(loword.co.kr) + Google Trends RSS"""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import xml.etree.ElementTree as ET


# ── 로워드 API (네이버 + 구글 실시간 검색어) ────────────────────────────────
LOWORD_API = "https://loword.co.kr/api/v1"
_LOWORD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Content-Type": "application/json",
    "Referer": "https://loword.co.kr/keywordTrend",
    "Origin": "https://loword.co.kr",
}


def get_loword_trends(date: str | None = None) -> dict:
    """
    로워드(loword.co.kr) API로 네이버 + 구글 실시간 검색어 수집.

    Returns:
        {
          "naver": [{"rank": str, "keyword": str, "caret": str}, ...],
          "google": [{"rank": int, "keyword": str, "approxTraffic": str}, ...]
        }
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    try:
        resp = requests.post(
            f"{LOWORD_API}/keyword/trend/getList",
            headers=_LOWORD_HEADERS,
            json={"date": date},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("rsltCd") == "00":
            return data["data"].get("keywordTrend", {"naver": [], "google": []})
    except Exception:
        pass

    return {"naver": [], "google": []}


# ── Google Trends RSS (로워드 구글 데이터 보완용) ────────────────────────────
def get_google_trends_rss() -> list[dict]:
    """Google Trends 실시간 급상승 검색어 RSS (한국, 상세 뉴스 포함)"""
    url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KR"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml-xml")
        items = soup.find_all("item")
        keywords = []
        for item in items[:30]:
            title_tag = item.find("title")
            traffic_tag = item.find("ht:approx_traffic")
            news_items = item.find_all("ht:news_item")
            news_titles = [
                n.find("ht:news_item_title").text.strip()
                for n in news_items[:2]
                if n.find("ht:news_item_title")
            ]
            keywords.append({
                "keyword": title_tag.text.strip() if title_tag else "",
                "traffic": traffic_tag.text.strip() if traffic_tag else "N/A",
                "related_news": news_titles,
                "source": "google_trends_rss",
            })
        return keywords
    except Exception as e:
        return [{"error": str(e), "keyword": "", "traffic": "", "related_news": [], "source": "google_trends_rss"}]


# ── 통합 수집 ────────────────────────────────────────────────────────────────
def collect_all_trends() -> dict:
    """로워드 API + Google Trends RSS 통합 수집"""
    loword = get_loword_trends()
    google_rss = get_google_trends_rss()

    naver_raw = loword.get("naver", [])
    google_raw = loword.get("google", [])

    # 로워드 네이버 키워드 정규화
    naver = [
        {
            "rank": int(kw.get("rank", i + 1)),
            "keyword": kw.get("keyword", ""),
            "caret": kw.get("caret", ""),
            "source": "naver",
        }
        for i, kw in enumerate(naver_raw)
        if kw.get("keyword")
    ]

    # 로워드 구글 키워드 정규화
    google_loword = [
        {
            "rank": kw.get("rank", i + 1),
            "keyword": kw.get("keyword", kw.get("title", "")),
            "traffic": kw.get("approxTraffic", "N/A"),
            "related_news": [],
            "source": "google_trends",
        }
        for i, kw in enumerate(google_raw)
        if kw.get("keyword") or kw.get("title")
    ]

    # Google RSS로 related_news 보완
    rss_map = {kw["keyword"]: kw for kw in google_rss if kw.get("keyword")}
    for kw in google_loword:
        if kw["keyword"] in rss_map:
            kw["related_news"] = rss_map[kw["keyword"]].get("related_news", [])

    # RSS 전용 키워드 (로워드 구글에 없는 것)
    loword_google_kws = {kw["keyword"] for kw in google_loword}
    rss_only = [
        {
            "rank": len(google_loword) + i + 1,
            "keyword": kw["keyword"],
            "traffic": kw.get("traffic", "N/A"),
            "related_news": kw.get("related_news", []),
            "source": "google_trends",
        }
        for i, kw in enumerate(google_rss)
        if kw.get("keyword") and kw["keyword"] not in loword_google_kws
    ]
    google = google_loword + rss_only

    # 통합 키워드 (중복 제거, 네이버 우선)
    seen: set[str] = set()
    merged = []
    for kw in naver:
        if kw["keyword"] and kw["keyword"] not in seen:
            seen.add(kw["keyword"])
            merged.append({
                "keyword": kw["keyword"],
                "traffic": f"#{kw['rank']}",
                "caret": kw.get("caret", ""),
                "source": "네이버",
            })
    for kw in google:
        if kw["keyword"] and kw["keyword"] not in seen:
            seen.add(kw["keyword"])
            merged.append({
                "keyword": kw["keyword"],
                "traffic": kw.get("traffic", ""),
                "caret": "",
                "source": "구글",
            })

    return {
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "naver": naver,
        "google": google,
        "merged": merged,
    }
