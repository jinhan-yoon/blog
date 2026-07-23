"""네이버 블로그 로그인 세션 저장 → naver_session.json

사용법:
    python naver_setup.py              # 브라우저 창을 직접 보고 수동 로그인 (GUI 환경 필요)
    python naver_setup.py --headless   # NAVER_ID/NAVER_PW로 자동 로그인 시도 (GUI 없는 서버용)

--headless 모드는 캡차·2단계 인증이 뜨면 실패합니다. 그 경우 GUI가 있는 PC에서
플래그 없이 실행해 수동으로 로그인한 뒤, 생성된 naver_session.json을 서버로 옮기세요.
"""
from __future__ import annotations

import sys
from datetime import datetime
from playwright.sync_api import sync_playwright

from modules.naver_blog_poster import _login, LOGIN_URL, SESSION_PATH, ERROR_DIR, LAUNCH_ARGS, new_context


def _manual_login(page) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    print("브라우저에서 네이버 계정으로 로그인하세요 (캡차/2단계 인증 포함).")
    print("로그인이 완료되면 자동으로 감지해 세션을 저장합니다... (최대 5분 대기)")
    try:
        page.wait_for_url(lambda url: "nidlogin" not in url, timeout=300_000)
    except Exception:
        raise RuntimeError("5분 내에 로그인이 감지되지 않았습니다. 다시 실행해주세요.")
    page.wait_for_timeout(2000)


def main() -> None:
    headless = "--headless" in sys.argv[1:]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=LAUNCH_ARGS)
        context = new_context(browser)
        page = context.new_page()

        try:
            if headless:
                _login(page)
            else:
                _manual_login(page)

            context.storage_state(path=str(SESSION_PATH))
            print(f"✅ 세션 저장 완료: {SESSION_PATH.resolve()}")

        except Exception as e:
            print(f"❌ {e}")
            if headless:
                ERROR_DIR.mkdir(exist_ok=True)
                shot = ERROR_DIR / f"setup_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                try:
                    page.screenshot(path=str(shot), full_page=True)
                    print(f"오류 스크린샷 저장: {shot}")
                except Exception:
                    pass
                print("GUI 환경에서 `python naver_setup.py`(플래그 없이)로 재시도해 직접 로그인해주세요.")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
