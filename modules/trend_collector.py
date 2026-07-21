"""당일 트렌드 키워드 수집 모듈"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import xml.etree.ElementTree as ET


def get_google_trends_kr() -> list[dict]:
    """Google 트렌드 실시간 급상승 검색어 (한국) 수집"""
    url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KR"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
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

            news_titles = []
            for n in news_items[:2]:
                t = n.find("ht:news_item_title")
                if t:
                    news_titles.append(t.text.strip())

            keywords.append({
                "keyword": title_tag.text.strip() if title_tag else "",
                "traffic": traffic_tag.text.strip() if traffic_tag else "N/A",
                "related_news": news_titles,
                "source": "google_trends",
            })

        return keywords

    except Exception as e:
        return [{"error": str(e), "keyword": "", "traffic": "", "related_news": [], "source": "google_trends"}]


def get_naver_trends() -> list[dict]:
    """네이버 실시간 급상승 검색어 수집 (RSS)"""
    url = "https://www.naver.com/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")

        keywords = []
        # 네이버 실시간 검색어 CSS 셀렉터 (구조 변경 시 업데이트 필요)
        items = soup.select(".ah_item .ah_k")
        for i, item in enumerate(items[:20], 1):
            keywords.append({
                "rank": i,
                "keyword": item.text.strip(),
                "source": "naver",
            })

        return keywords

    except Exception as e:
        return []


def get_daum_trends() -> list[dict]:
    """다음 실시간 급상승 검색어 수집"""
    url = "https://www.daum.net/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")

        keywords = []
        items = soup.select(".rank_news .link_txt")
        for i, item in enumerate(items[:20], 1):
            keywords.append({
                "rank": i,
                "keyword": item.text.strip(),
                "source": "daum",
            })

        return keywords

    except Exception as e:
        return []


def collect_all_trends() -> dict:
    """모든 소스에서 트렌드 수집 후 통합 반환"""
    result = {
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "google": get_google_trends_kr(),
        "naver": get_naver_trends(),
        "daum": get_daum_trends(),
    }

    # 중복 제거 후 통합 키워드 목록
    seen = set()
    merged = []
    for kw in result["google"]:
        if kw.get("keyword") and kw["keyword"] not in seen:
            seen.add(kw["keyword"])
            merged.append({"keyword": kw["keyword"], "traffic": kw.get("traffic", ""), "source": "구글 트렌드"})

    for kw in result["naver"]:
        if kw.get("keyword") and kw["keyword"] not in seen:
            seen.add(kw["keyword"])
            merged.append({"keyword": kw["keyword"], "traffic": f"#{kw.get('rank', '')}", "source": "네이버"})

    for kw in result["daum"]:
        if kw.get("keyword") and kw["keyword"] not in seen:
            seen.add(kw["keyword"])
            merged.append({"keyword": kw["keyword"], "traffic": f"#{kw.get('rank', '')}", "source": "다음"})

    result["merged"] = merged
    return result
