"""네이버 블로그 발행 모듈 — Playwright 기반 UI 자동화 (공식 API 없음)"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# 일부 윈도우 콘솔(cp949 등)은 이모지를 출력하지 못해 UnicodeEncodeError로 죽으므로 강제 UTF-8 처리
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
SEL_POPUP_CANCEL = ".se-popup-button-cancel, button:has-text('취소')"
SEL_HELP_CLOSE = ".se-help-panel-close-button"
SEL_TITLE = ".se-title-text .se-text-paragraph"
# .se-component-content .se-text-paragraph만으로는 제목 영역도 같은 구조를 써서
# .first가 제목 문단을 다시 잡아버릴 수 있어, se-title-text 하위가 아닌 것만 선택
SEL_BODY = "xpath=//*[contains(concat(' ', normalize-space(@class), ' '), ' se-text-paragraph ')][not(ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' se-title-text ')])]"
# has-text는 부분일치라 "예약발행" 버튼도 걸려 잘못 클릭될 수 있어, 텍스트가 정확히
# "발행"인 버튼만 선택 (:text-is는 공백 트리밍 후 완전일치)
SEL_PUBLISH_OPEN = "button:text-is('발행')"
SEL_TAG_INPUT = "#tag-input"
SEL_PUBLISH_CONFIRM = "button:text-is('발행')"


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
            snippet = " / ".join(line.strip() for line in body_text.splitlines() if line.strip())[:400]
        except Exception:
            snippet = ""

        if any(k in snippet for k in ("캡차", "영수증", "추가 확인", "additional verification")):
            reason = "캡차/추가 인증 화면"
        else:
            reason = "원인 불명 (로그인 페이지에 그대로 머묾)"

        msg = f"네이버 자동 로그인 실패 — {reason}"
        if snippet:
            msg += f". 화면 내용: {snippet!r}"
        raise RuntimeError(msg)

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

    본문 HTML은 문단 텍스트만 추출해 실제 키 입력처럼 타이핑해 넣습니다.
    굵게/제목 등 서식과 이미지(<img>)는 반영되지 않는 평문 발행입니다.

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
            _dismiss_popups(frame)
            frame.locator(SEL_TITLE).first.click()
            page.keyboard.type(title, delay=10)

            _log(log_callback, "본문 삽입 중...")
            _dismiss_popups(frame)
            body_locator = frame.locator(SEL_BODY).first
            body_locator.click()
            for block in _html_to_text_blocks(content_html):
                page.keyboard.type(block, delay=3)
                page.keyboard.press("Enter")
            page.wait_for_timeout(800)

            _log(log_callback, "발행 설정 중...")
            # "발행" 버튼과 그 이후 설정 레이어는 iframe#mainFrame 밖 상위 페이지 헤더에 있는
            # 것으로 보이나, 확실치 않아 상위 페이지 우선 시도 후 iframe 안도 시도
            _click_first(page, frame, SEL_PUBLISH_OPEN)
            tag_input = _locate_first(page, frame, SEL_TAG_INPUT, timeout=8000)

            for tag in (tags or [])[:10]:
                tag_input.click()
                page.keyboard.type(tag, delay=30)
                page.keyboard.press("Enter")

            _log(log_callback, "발행 중...")
            # 발행 설정 레이어(팝업)는 보통 DOM에 나중에 추가되므로, 같은 "발행" 버튼 중
            # 마지막 것이 레이어 안의 최종 확인 버튼일 가능성이 높음 (.first는 상단 버튼 재클릭 위험)
            _click_last(page, frame, SEL_PUBLISH_CONFIRM)
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


def _locate_first(page, frame, sel: str, timeout: int = 8000):
    """상위 페이지에 먼저 있는지 보고, 없으면 iframe 안에서 첫 번째 매치를 반환"""
    try:
        loc = page.locator(sel).first
        loc.wait_for(state="visible", timeout=timeout)
        return loc
    except Exception:
        return frame.locator(sel).first


def _click_first(page, frame, sel: str, timeout: int = 8000) -> None:
    """상위 페이지에 먼저 있는지 보고, 없으면 iframe 안에서 첫 번째 매치를 클릭"""
    try:
        page.locator(sel).first.wait_for(state="visible", timeout=timeout)
        page.locator(sel).first.click()
    except Exception:
        frame.locator(sel).first.click()


def _click_last(page, frame, sel: str, timeout: int = 8000) -> None:
    """상위 페이지에 먼저 있는지 보고, 없으면 iframe 안에서 마지막 매치를 클릭"""
    try:
        page.locator(sel).last.wait_for(state="visible", timeout=timeout)
        page.locator(sel).last.click()
    except Exception:
        frame.locator(sel).last.click()


def _dismiss_popups(frame) -> None:
    """이어쓰기 확인창·도움말 패널·일반 알림(se-popup-alert) 등 화면을 가리는 팝업 정리"""
    for sel in (
        SEL_POPUP_CANCEL,
        SEL_HELP_CLOSE,
        ".se-popup-alert-confirm button",
        ".se-popup-alert button",
        ".se-popup-dim ~ * button",
    ):
        try:
            btn = frame.locator(sel).first
            # is_visible()은 timeout을 줘도 기다리지 않고 즉시 판정하므로,
            # 팝업이 늦게 뜨는 경우를 잡으려면 wait_for()로 실제로 기다려야 함
            btn.wait_for(state="visible", timeout=1200)
            btn.click()
        except Exception:
            pass


def _html_to_text_blocks(content_html: str) -> list[str]:
    """
    HTML 본문을 문단 단위 평문으로 변환.
    Smart Editor는 합성 ClipboardEvent를 통한 붙여넣기를 실제로 반영하지 않아
    (paste 이벤트는 발생해도 콘텐츠가 삽입되지 않음), 실제 키 입력을 흉내내는
    keyboard.type()으로 문단을 하나씩 입력하는 방식을 사용한다.
    이 과정에서 굵게/제목 등 서식과 <img>는 반영되지 않는다.
    """
    soup = BeautifulSoup(content_html, "html.parser")
    blocks = [
        text for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "li", "blockquote"])
        if (text := tag.get_text(" ", strip=True))
    ]
    if not blocks:
        text = soup.get_text(" ", strip=True)
        if text:
            blocks = [text]
    return blocks


def _log(log_callback, msg: str) -> None:
    print(msg)
    if log_callback:
        log_callback(msg)
