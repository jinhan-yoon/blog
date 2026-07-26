"""네이버 블로그 발행 모듈 — Playwright 기반 UI 자동화 (공식 API 없음)"""
from __future__ import annotations

import os
import sys
import secrets
from datetime import datetime
from pathlib import Path
import requests
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
# has-text는 부분일치라 "예약발행" 버튼도 걸려 잘못 클릭될 수 있어, 텍스트가 정확히
# "발행"인 요소만 선택 (:text-is는 공백 트리밍 후 완전일치). button 태그로 한정하지 않는 이유는
# 실제 발행 요소가 button이 아닌 div/a일 수 있어서 (확인 전까지는 태그 제한을 두지 않음)
SEL_PUBLISH_OPEN = "*:text-is('발행')"
SEL_TAG_INPUT = "#tag-input"
SEL_PUBLISH_CONFIRM = "*:text-is('발행')"


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

def _fill_and_submit_login(page, naver_id: str, naver_pw: str) -> None:
    """로그인 폼에 ID/PW를 입력하고 로그인 버튼을 클릭 (제출 결과는 호출자가 판단)"""
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


def _login(page, log_callback=None) -> None:
    """NAVER_ID/NAVER_PW로 자동 로그인 시도. 캡차·2단계 인증 시 예외 발생."""
    _log(log_callback, "네이버 자동 로그인 시도 중...")

    naver_id = os.getenv("NAVER_ID", "")
    naver_pw = os.getenv("NAVER_PW", "")
    if not naver_id or not naver_pw:
        raise RuntimeError("NAVER_ID / NAVER_PW가 .env에 설정되지 않았습니다.")

    _fill_and_submit_login(page, naver_id, naver_pw)

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


# ── 앱 내 대화형 로그인 (캡차를 화면에 보여주고 답을 입력받는 방식) ────────────
# Streamlit은 매 상호작용마다 스크립트를 처음부터 다시 실행하므로, 캡차 답을
# 기다리는 동안 살아있어야 하는 Playwright 브라우저를 세션 토큰 기준으로
# 서버 메모리에 보관해두고 다음 제출 때 다시 찾아 쓴다.
_pending_logins: dict[str, dict] = {}


def _has_solvable_challenge(page) -> bool:
    """
    실제로 답할 수 있는 캡차/추가 인증 화면인지 확인.
    네이버는 자동화를 의심하면 아무 문구·입력칸 없이 그냥 빈 로그인 폼으로 조용히
    돌려보내는 경우가 있는데, 이건 답할 캡차가 없으므로 구분해야 한다.
    """
    try:
        body_text = page.inner_text("body")
    except Exception:
        return False
    return any(k in body_text for k in ("캡차", "영수증", "빈 칸", "추가 확인", "인증번호"))


def start_interactive_login() -> dict:
    """
    앱 화면에서 네이버 로그인을 시작. ID/PW를 자동 입력하고 제출한다.
    바로 성공하면 {"status": "success"}.
    캡차 등 실제로 답할 수 있는 추가 인증이 뜨면
    {"status": "challenge", "session_id": str, "screenshot": bytes}
    (브라우저는 살려둔 채 반환 — submit_login_challenge()로 이어서 처리).
    실패(캡차 없이 조용히 차단된 경우 포함)하면 {"status": "error", "message": str, "screenshot": bytes|None}.
    """
    from playwright.sync_api import sync_playwright

    naver_id = os.getenv("NAVER_ID", "")
    naver_pw = os.getenv("NAVER_PW", "")
    if not naver_id or not naver_pw:
        return {"status": "error", "message": "NAVER_ID / NAVER_PW가 .env에 설정되지 않았습니다."}

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
    context = new_context(browser)
    page = context.new_page()

    try:
        _fill_and_submit_login(page, naver_id, naver_pw)

        if "nidlogin" not in page.url:
            context.storage_state(path=str(SESSION_PATH))
            browser.close()
            p.stop()
            return {"status": "success"}

        if _has_solvable_challenge(page):
            session_id = secrets.token_urlsafe(12)
            screenshot = page.screenshot(full_page=True)
            _pending_logins[session_id] = {"playwright": p, "browser": browser, "context": context, "page": page}
            return {"status": "challenge", "session_id": session_id, "screenshot": screenshot}

        # 캡차 문구·입력칸 없이 그냥 로그인 페이지에 머무름 — 조용한 자동화 차단으로 판단
        screenshot = page.screenshot(full_page=True)
        browser.close()
        p.stop()
        return {
            "status": "error",
            "message": (
                "캡차 없이 로그인 페이지에 그대로 머물러 있습니다 — 네이버가 자동화를 의심해 "
                "조용히 차단한 것으로 보입니다. 이 경우 GUI가 있는 PC에서 "
                "`python naver_setup.py`로 수동 로그인 후 세션 파일을 서버로 옮기는 방법을 권장합니다."
            ),
            "screenshot": screenshot,
        }

    except Exception as e:
        try:
            browser.close()
        except Exception:
            pass
        p.stop()
        return {"status": "error", "message": str(e)}


def cancel_login_challenge(session_id: str) -> None:
    """대기 중인 로그인 시도를 취소하고 브라우저 리소스 정리"""
    state = _pending_logins.pop(session_id, None)
    if not state:
        return
    try:
        state["browser"].close()
    except Exception:
        pass
    state["playwright"].stop()


def submit_login_challenge(session_id: str, answer: str) -> dict:
    """
    캡차 등 추가 인증 화면에 사용자가 입력한 답을 제출하고 결과를 반환.
    반환 형식은 start_interactive_login()과 동일.
    """
    state = _pending_logins.get(session_id)
    if not state:
        return {"status": "error", "message": "로그인 세션이 만료되었습니다. 처음부터 다시 시도해주세요."}

    page, context, browser, p = state["page"], state["context"], state["browser"], state["playwright"]

    def _cleanup():
        _pending_logins.pop(session_id, None)
        try:
            browser.close()
        except Exception:
            pass
        p.stop()

    try:
        # 캡차 정답 입력칸으로 추정되는, 화면에 보이는 마지막 텍스트 입력을 사용
        answer_input = page.locator("input[type='text'], input:not([type])").last
        answer_input.wait_for(state="visible", timeout=5000)
        answer_input.click()
        page.keyboard.type(answer, delay=50)

        confirm_btn = page.locator("button:has-text('확인')").first
        confirm_btn.click()
        page.wait_for_load_state("networkidle", timeout=15000)

        if "nidlogin" not in page.url:
            context.storage_state(path=str(SESSION_PATH))
            _cleanup()
            return {"status": "success"}

        if _has_solvable_challenge(page):
            # 여전히 로그인 페이지 — 재도전 화면으로 판단, 최신 화면을 다시 보여줌
            screenshot = page.screenshot(full_page=True)
            return {"status": "challenge", "session_id": session_id, "screenshot": screenshot}

        screenshot = page.screenshot(full_page=True)
        _cleanup()
        return {
            "status": "error",
            "message": "정답이 틀렸거나 추가로 조용히 차단된 것으로 보입니다. 다시 시도해주세요.",
            "screenshot": screenshot,
        }

    except Exception as e:
        _cleanup()
        return {"status": "error", "message": str(e)}


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

    본문 HTML의 문단 텍스트는 실제 입력처럼 타이핑해 넣고, <img> 태그는 원래 위치 그대로
    다운로드해 네이버 사진 업로드 기능으로 삽입합니다. 굵게/제목 등 세부 서식은 반영되지 않습니다.

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
            # 본문 placeholder 문단을 직접 클릭해서 거기 이어 타이핑하면 이상하게
            # 취소선 서식이 계속 남아있었음. 제목에서 Enter로 자연스럽게 본문으로 넘어가도
            # 동일하게 발생해, 개발자도구로 실제 원인을 확인함: 실제 취소선 토글 버튼은
            # 텍스트를 "선택"했을 때만 나타나는 속성 툴바(.se-strikethrough-toolbar-button)라
            # 커서만 있는 상태에서 확인/클릭해봐야 소용이 없었던 것 — 전체 선택 후 꺼야 함
            page.keyboard.press("Enter")
            for block in _html_to_blocks(content_html):
                if block["type"] == "image":
                    _insert_image(frame, page, block["src"], log_callback)
                else:
                    # keyboard.type()은 한 글자씩 눌러 "~~단어~~" 같은 패턴이 스마트에디터의
                    # 마크다운 단축 서식(취소선 등)으로 오인식됨 — insert_text는 완성된 문자열을
                    # 한 번에 넣어 단축 서식 감지를 우회한다
                    page.keyboard.insert_text(block["text"])
                    page.keyboard.press("Enter")
            page.wait_for_timeout(800)
            _clear_strike_on_selection(frame, page)

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


def _clear_strike_on_selection(frame, page) -> None:
    """
    본문 전체를 선택한 뒤, 개발자도구로 확인한 실제 취소선 토글 버튼
    (.se-strikethrough-toolbar-button, data-name="strikethrough")을 클릭해 끈다.
    이 버튼은 텍스트가 "선택"된 상태에서만 나타나는 속성 툴바 소속이라,
    커서만 있는 상태에서는 확인·클릭이 애초에 불가능했다.
    """
    try:
        page.keyboard.press("Control+a")
        btn = frame.locator(".se-strikethrough-toolbar-button").first
        btn.wait_for(state="visible", timeout=2000)
        pressed = btn.get_attribute("aria-pressed")
        is_active = pressed == "true" or "active" in (btn.get_attribute("class") or "")
        if is_active or pressed is None:
            btn.click()
    except Exception:
        pass


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


def _html_to_blocks(content_html: str) -> list[dict]:
    """
    HTML 본문을 원래 순서 그대로 텍스트/이미지 블록 리스트로 변환.
    {"type": "text", "text": str} 또는 {"type": "image", "src": str}

    본문은 Smart Editor가 합성 ClipboardEvent 붙여넣기를 실제로 반영하지 않아
    (이벤트는 발생해도 콘텐츠 미삽입), 실제 입력을 흉내내는 insert_text()로 문단을
    하나씩 입력한다. 굵게/제목 등 세부 서식은 반영되지 않는다.

    본문에 "~~단어~~" 같은 물결표 강조가 있으면(캐주얼한 한국어 블로그 문체에서 흔함)
    Smart Editor가 이를 취소선 마크다운 단축 서식으로 오인식해 실제로 취소선이 적용되므로,
    전각 물결(～)로 치환해 원래 어감은 유지하면서 오인식을 막는다.
    """
    soup = BeautifulSoup(content_html, "html.parser")
    blocks: list[dict] = []
    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "li", "blockquote", "img"]):
        if tag.name == "img":
            src = tag.get("src")
            if src:
                blocks.append({"type": "image", "src": src})
        else:
            text = tag.get_text(" ", strip=True)
            if text:
                blocks.append({"type": "text", "text": text.replace("~", "～")})

    if not blocks:
        text = soup.get_text(" ", strip=True).replace("~", "～")
        if text:
            blocks = [{"type": "text", "text": text}]
    return blocks


def _insert_image(frame, page, image_url: str, log_callback=None) -> None:
    """이미지 URL을 다운로드해 Smart Editor의 사진 업로드 input(type=file)으로 삽입"""
    try:
        resp = requests.get(image_url, timeout=30)
        resp.raise_for_status()
        image_bytes = resp.content
    except Exception as e:
        _log(log_callback, f"⚠️ 이미지 다운로드 실패, 건너뜀: {e}")
        return

    try:
        # "사진" 툴바 버튼을 먼저 눌러야 업로드 input이 현재 커서 위치를 인식하는 구조일 수 있어 시도
        photo_btn = frame.locator(":text-is('사진')").first
        photo_btn.wait_for(state="visible", timeout=2000)
        photo_btn.click()
    except Exception:
        pass

    try:
        file_input = frame.locator("input[type='file']").first
        file_input.set_input_files({
            "name": "image.jpg",
            "mimeType": "image/jpeg",
            "buffer": image_bytes,
        })
        page.wait_for_timeout(2500)
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        _log(log_callback, "🖼️ 이미지 삽입 완료")
    except Exception as e:
        _log(log_callback, f"⚠️ 이미지 삽입 실패, 건너뜀: {e}")


def _log(log_callback, msg: str) -> None:
    print(msg)
    if log_callback:
        log_callback(msg)
