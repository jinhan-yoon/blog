"""네이버 블로그 최초 1회 수동 로그인 → naver_session.json 저장

사용법:
    python naver_setup.py

브라우저 창이 열리면 직접 로그인(캡차·2단계 인증 포함)한 뒤,
블로그 홈으로 이동할 때까지 기다리면 세션이 자동 저장됩니다.
"""
from __future__ import annotations

from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION_PATH = Path("naver_session.json")
LOGIN_URL = "https://nid.naver.com/nidlogin.login"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1400, "height": 1000}, locale="ko-KR")
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        print("브라우저에서 네이버 계정으로 로그인하세요 (캡차/2단계 인증 포함).")
        print("로그인이 완료되면 자동으로 감지해 세션을 저장합니다... (최대 5분 대기)")

        try:
            page.wait_for_url(lambda url: "nidlogin" not in url, timeout=300_000)
        except Exception:
            print("⏱️ 5분 내에 로그인이 감지되지 않았습니다. 다시 실행해주세요.")
            browser.close()
            return

        # 로그인 직후 리다이렉트가 안정될 시간을 잠깐 대기
        page.wait_for_timeout(2000)
        context.storage_state(path=str(SESSION_PATH))
        print(f"✅ 세션 저장 완료: {SESSION_PATH.resolve()}")

        browser.close()


if __name__ == "__main__":
    main()
