"""네이버 블로그 발행 모듈 — Playwright 기반 UI 자동화 (공식 API 없음)"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SESSION_PATH = Path("naver_session.json")
ERROR_DIR = Path("naver_errors")

LOGIN_URL = "https://nid.naver.com/nidlogin.login"
WRITE_URL = "https://blog.naver.com/{blog_id}?Redirect=Write&"

# 헤드리스 Chromium을 그대로 쓰면 navigator.webdriver 등으로 자동화가 감지돼
# 네이버가 로그인을 거부할 수 있어, launch 인자·UA·초기화 스크립트로 흔적을 지움
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_STEALTH_INIT_SCRIPT = "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"

# Smart Editor ONE의 클래스명은 네이버가 예고 없이 변경하므로, 발행이 실패하면
# 아래 셀렉터들을 최신 DOM 구조에 맞춰 갱신해야 할 수 있습니다.
SEL_POPUP_CANCEL = ".se-popup-button-cancel"
SEL_HELP_CLOSE = ".se-help-panel-close-button"
SEL_TITLE = ".se-title-text .se-text-paragraph"
SEL_BODY = ".se-component-content .se-text-paragraph"
SEL_PUBLISH_OPEN = "button.publish_btn_area, button:has-text('발행')"
SEL_TAG_INPUT = "#tag-input"
SEL_PUBLISH_CONFIRM = ".layer_btn button:has-text('발행'), button.btn_publish:has-text('발행')"


# ── 상태 확인 ──────────────────────────────────────────────────────────────

def check_session_status() -> dict:
    """세션 파일·환경변수 설정 여부 반환 (blogger_publisher.check_auth_status와 동일한 형식)"""
    has_session = SESSION_PATH.exists()
    naver_id = os.getenv("NAVER_ID", "")
    naver_pw = os.getenv("NAVER_PW", "")
    blog_id = os.getenv("NAVER_BLOG_ID", "")

    return {
        "session": has_session,
        "credentials": bool(naver_id and naver_pw),
        "blog_id": bool(blog_id),
        "ready": has_session and bool(naver_id and naver_pw) and bool(blog_id),
    }


def new_context(browser, storage_state: str | None = None):
    """자동화 탐지를 피하기 위한 설정이 적용된 브라우저 컨텍스트 생성"""
    context = browser.new_context(
        storage_state=storage_state,
        viewport={"width": 1400, "height": 1000},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        user_agent=_USER_AGENT,
    )
    context.add_init_script(_STEALTH_INIT_SCRIPT)
    return context


# ── 로그인 ────────────────────────────────────────────────────────────────

def _login(page, log_callback=None) -> None:
    """NAVER_ID/NAVER_PW로 자동 로그인 시도. 캡차·2단계 인증 시 예외 발생."""
    _log(log_callback, "네이버 자동 로그인 시도 중...")

    naver_id = os.getenv("NAVER_ID", "")
    naver_pw = os.getenv("NAVER_PW", "")
    if not naver_id or not naver_pw:
        raise RuntimeError("NAVER_ID / NAVER_PW가 .env에 설정되지 않았습니다.")

    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_selector("#id", timeout=15000)

    # 네이버는 마우스 이동 없이 값이 즉시 채워지는 것도 자동화 신호로 볼 수 있어
    # 필드 이동 전 마우스를 움직이고, 입력도 사람처럼 keyboard.type()으로 흉내냄
    page.mouse.move(200, 200)
    page.mouse.move(400, 320, steps=8)
    page.locator("#id").click()
    page.keyboard.type(naver_id, delay=80)
    page.mouse.move(420, 380, steps=5)
    page.locator("#pw").click()
    page.keyboard.type(naver_pw, delay=80)

    # 네이버 로그인 폼은 반응형 레이아웃별로 column/row 두 벌의 버튼을 동시에 DOM에 두고
    # CSS로 하나만 보여주므로, id로 특정한 뒤 실제로 보이는 쪽을 찾아 클릭해야 함
    # (텍스트 매칭은 "패스키 로그인" 버튼도 "로그인"을 포함해 오클릭될 수 있음)
    login_btn = None
    for sel in ("#loginBtn_column", "#loginBtn_row", "#log\\.login"):
        candidate = page.locator(sel)
        if candidate.count() and candidate.first.is_visible():
            login_btn = candidate.first
            break
    if login_btn is None:
        login_btn = page.locator("button.btn_done:has-text('로그인')").first
    login_btn.click()

    page.wait_for_load_state("networkidle", timeout=15000)

    if "nidlogin" in page.url:
        try:
            body_text = page.inner_text("body")
            snippet = " / ".join(line.strip() for line in body_text.splitlines() if line.strip())[:600]
        except Exception:
            snippet = ""
        detail = f" 현재 화면 텍스트: {snippet!r}" if snippet else " (화면 텍스트를 읽지 못함)"
        raise RuntimeError(
            f"네이버 자동 로그인 실패 (캡차/2단계 인증/자동화 탐지로 추정). url={page.url}{detail} "
            "터미널에서 `python naver_setup.py`를 실행해 수동으로 로그인 후 다시 시도하세요."
        )

    _log(log_callback, "✅ 네이버 로그인 성공")


def _is_logged_in(context) -> bool:
    """저장된 세션 쿠키에 로그인 토큰이 남아있는지 확인 (네트워크 요청 없이 빠른 체크)"""
    cookies = context.cookies("https://www.naver.com")
    names = {c["name"] for c in cookies}
    return "NID_AUT" in names and "NID_SES" in names


# ── 발행 ──────────────────────────────────────────────────────────────────

def publish_post(
    title: str,
    content_html: str,
    tags: list[str] | None = None,
    blog_id: str | None = None,
    headless: bool = True,
    log_callback=None,
) -> dict:
    """
    네이버 블로그에 포스팅 발행 (Playwright + Smart Editor ONE UI 자동화).

    본문은 기존에 생성된 HTML(이미지 포함)을 그대로 클립보드 붙여넣기 방식으로
    에디터에 주입합니다. 표·스티커 등 복잡한 컴포넌트는 지원하지 않습니다.

    Returns:
        {"url": str|None, "error": str|None, "screenshot": str|None}
    """
    from playwright.sync_api import sync_playwright

    blog_id = (blog_id or os.getenv("NAVER_BLOG_ID", "")).strip()
    if not blog_id:
        return {"url": None, "error": "NAVER_BLOG_ID가 설정되지 않았습니다.", "screenshot": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=LAUNCH_ARGS)
        context = new_context(browser, storage_state=str(SESSION_PATH) if SESSION_PATH.exists() else None)
        page = context.new_page()
        page.on("dialog", lambda d: d.dismiss())

        try:
            if not _is_logged_in(context):
                _login(page, log_callback)
                context.storage_state(path=str(SESSION_PATH))

            _log(log_callback, "네이버 블로그 글쓰기 페이지 이동 중...")
            page.goto(WRITE_URL.format(blog_id=blog_id), wait_until="domcontentloaded")
            page.wait_for_selector("iframe#mainFrame", timeout=30000)
            frame = page.frame_locator("iframe#mainFrame")

            _dismiss_popups(frame)

            _log(log_callback, "제목 입력 중...")
            frame.locator(SEL_TITLE).first.click()
            page.keyboard.type(title, delay=10)

            _log(log_callback, "본문 삽입 중...")
            frame.locator(SEL_BODY).first.click()
            _paste_html(frame, content_html)
            page.wait_for_timeout(1500)

            _log(log_callback, "발행 설정 중...")
            frame.locator(SEL_PUBLISH_OPEN).first.click()
            frame.locator(SEL_TAG_INPUT).wait_for(timeout=8000)

            for tag in (tags or [])[:10]:
                tag_input = frame.locator(SEL_TAG_INPUT)
                tag_input.click()
                page.keyboard.type(tag, delay=30)
                page.keyboard.press("Enter")

            _log(log_callback, "발행 중...")
            frame.locator(SEL_PUBLISH_CONFIRM).first.click()
            page.wait_for_url(f"**/{blog_id}/**", timeout=20000)

            final_url = page.url
            _log(log_callback, f"✅ 네이버 블로그 발행 완료: {final_url}")
            context.storage_state(path=str(SESSION_PATH))
            return {"url": final_url, "error": None, "screenshot": None}

        except Exception as e:
            ERROR_DIR.mkdir(exist_ok=True)
            shot_path = ERROR_DIR / f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            try:
                page.screenshot(path=str(shot_path), full_page=True)
            except Exception:
                shot_path = None
            err_msg = f"네이버 발행 실패: {e}"
            _log(log_callback, f"❌ {err_msg}")
            return {"url": None, "error": err_msg, "screenshot": str(shot_path) if shot_path else None}

        finally:
            browser.close()


def _dismiss_popups(frame) -> None:
    """이어쓰기 확인창·도움말 패널 등 글쓰기 진입 시 뜨는 팝업 정리"""
    for sel in (SEL_POPUP_CANCEL, SEL_HELP_CLOSE):
        try:
            btn = frame.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click()
        except Exception:
            pass


def _paste_html(frame, content_html: str) -> None:
    """포커스된 에디터 영역에 HTML을 클립보드 붙여넣기 이벤트로 주입 (raw HTML 입력 API가 없어 이 방식 사용)"""
    frame.locator(":focus").evaluate(
        """(el, html) => {
            const dt = new DataTransfer();
            dt.setData('text/html', html);
            const evt = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
            el.dispatchEvent(evt);
        }""",
        content_html,
    )


def _log(log_callback, msg: str) -> None:
    print(msg)
    if log_callback:
        log_callback(msg)
