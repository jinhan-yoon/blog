
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    make_response,
    redirect,
    render_template_string,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from modules.app_auth import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    check_password,
    complete_login,
    get_login_url,
    is_configured as google_auth_configured,
    is_password_configured,
    make_password_session_token,
    make_session_token,
    verify_password_session_token,
    verify_session_token,
)

load_dotenv()

APP_BASE_URL = os.getenv("APP_BASE_URL", "https://blog.superip.net").rstrip("/")
COOKIE_SECURE = APP_BASE_URL.lower().startswith("https://")
DATA_DIR = Path("data")
ERROR_DIR = Path("naver_errors")

app = Flask(__name__)
app.secret_key = os.getenv("APP_SESSION_SECRET") or os.getenv("FLASK_SECRET_KEY") or "change-me-in-env"

_START_TIME = time.monotonic()
_workspaces: dict[str, dict] = {}

DEFAULT_WORKSPACE = {
    "trends": None,
    "selected_keywords": [],
    "manual_keywords": [],
    "topics": None,
    "post_topic": None,
    "post_title": "",
    "post_content_html": "",
    "post_meta_desc": "",
    "post_tags": [],
    "image_prompts": [],
    "image_data": [],
    "final_html": "",
    "naver_content_html": "",
    "publish_result": None,
    "naver_publish_result": None,
    "naver_publish_running": False,
    "naver_publish_log": [],
    "publish_history": [],
    "blogger_recent_posts": None,
    "oauth_url": None,
    "oauth_redirect_uri": None,
    "oauth_code_verifier": None,
    "naver_login_state": None,
    "local_save_path": None,
    "quick_generate_running": False,
    "quick_generate_log": [],
    "quick_generate_error": None,
}


def _clone_default() -> dict:
    return json.loads(json.dumps(DEFAULT_WORKSPACE))


def _workspace() -> dict:
    wid = request.cookies.get("blog_workspace_id") or session.get("workspace_id")
    if not wid:
        wid = secrets.token_urlsafe(18)
        session["workspace_id"] = wid
    if wid not in _workspaces:
        _workspaces[wid] = _clone_default()
    return _workspaces[wid]


@app.after_request
def _ensure_workspace_cookie(resp):
    wid = session.get("workspace_id")
    if wid and not request.cookies.get("blog_workspace_id"):
        resp.set_cookie("blog_workspace_id", wid, max_age=SESSION_TTL_SECONDS, secure=COOKIE_SECURE, httponly=True, samesite="Lax", path="/")
    return resp


def _current_user() -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    token = unquote(token)
    email = verify_session_token(token)
    if email:
        return email
    if verify_password_session_token(token):
        return "관리자"
    return None


def _set_auth_cookie(resp, token: str):
    resp.set_cookie(SESSION_COOKIE_NAME, token, max_age=SESSION_TTL_SECONDS, secure=COOKIE_SECURE, httponly=True, samesite="Lax", path="/")
    return resp


def _clear_auth_cookie(resp):
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return resp


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _current_user():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def _tags_from_text(text: str) -> list[str]:
    return [t.strip() for t in (text or "").split(",") if t.strip()]


def _safe_saved_path(name: str) -> Path:
    # werkzeug의 secure_filename()은 한글 등 비-ASCII 문자를 제거해버려서,
    # 저장할 때 한글 제목이 그대로 들어간 실제 파일명과 불러올 때 이름이
    # 어긋나는 문제가 있었음 (예: "20260729_...구마모토강진.json" ->
    # "20260729_.json"). 경로 조작만 막고 유니코드 파일명은 그대로 허용한다.
    DATA_DIR.mkdir(exist_ok=True)
    name = (name or "").strip()
    if not name or "/" in name or "\\" in name or name.startswith(".") or not name.endswith(".json"):
        raise ValueError("잘못된 파일명입니다.")
    path = DATA_DIR / name
    if path.parent.resolve() != DATA_DIR.resolve():
        raise ValueError("잘못된 파일명입니다.")
    return path


def _saved_posts() -> list[dict]:
    DATA_DIR.mkdir(exist_ok=True)
    posts = []
    for path in sorted(DATA_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        posts.append({"name": path.name, "path": path, "data": data})
    return posts


def _save_local(ws: dict, title: str, content_html: str, tags: list, meta_description: str) -> Path:
    """작성 중인 글을 로컬에 저장. ws에 기록된 파일이 있으면 그 파일을 계속 덮어써서
    같은 글을 여러 번 자동저장해도 파일이 계속 새로 생기지 않게 한다."""
    DATA_DIR.mkdir(exist_ok=True)
    existing = ws.get("local_save_path")
    path = DATA_DIR / existing if existing else None
    if not path or path.parent.resolve() != DATA_DIR.resolve() or not path.exists():
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:40].strip() or "post"
        path = DATA_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_title}.json"
        ws["local_save_path"] = path.name
    payload = {
        "title": title,
        "content_html": content_html,
        "tags": tags,
        "meta_description": meta_description,
        "saved_at": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _save_env(form) -> None:
    existing_password = os.getenv("APP_PASSWORD", "")
    existing_secret = os.getenv("APP_SESSION_SECRET", "")
    env_content = f"""# -- LLM server -------------------------------------------------
LLM_ADDR={form.get('llm_addr', '')}
LLM_MODEL={form.get('llm_model', '')}
LLM_API_KEY={form.get('llm_api_key', '')}

# -- Image generation -------------------------------------------
IMAGE_PROVIDER={form.get('image_provider', 'pollinations')}
ANTHROPIC_API_KEY={form.get('anthropic_key', '')}
OPENAI_API_KEY={form.get('openai_key', '')}
HUGGINGFACE_TOKEN={form.get('hf_token', '')}
CLAUDE_MODEL={form.get('claude_model', 'claude-sonnet-4-6')}

# -- Google Blogger ---------------------------------------------
BLOGGER_BLOG_ID={form.get('blogger_blog_id', '')}
BLOGGER_BLOG_URL={form.get('blogger_blog_url', '')}

# -- Naver Blog --------------------------------------------------
NAVER_ID={form.get('naver_id', '')}
NAVER_PW={form.get('naver_pw', '')}
NAVER_BLOG_ID={form.get('naver_blog_id', '')}

# -- App login ---------------------------------------------------
APP_BASE_URL={form.get('app_base_url', APP_BASE_URL)}
ALLOWED_GOOGLE_EMAIL={form.get('allowed_email', '')}
APP_PASSWORD={form.get('app_password', existing_password)}
APP_SESSION_SECRET={existing_secret}
"""
    Path(".env").write_text(env_content, encoding="utf-8")
    load_dotenv(override=True)


@app.route("/", methods=["GET"])
def index():
    code = request.args.get("code")
    state = request.args.get("state", "")
    if code:
        try:
            email = complete_login(code, APP_BASE_URL, state)
        except Exception as exc:
            return render_login(error=f"구글 로그인 실패: {exc}"), 401
        resp = make_response(redirect(url_for("dashboard")))
        return _set_auth_cookie(resp, make_session_token(email))
    if not _current_user():
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        password = request.form.get("password", "")
        if check_password(password):
            resp = make_response(redirect(url_for("dashboard")))
            return _set_auth_cookie(resp, make_password_session_token())
        error = "비밀번호가 올바르지 않습니다."
    return render_login(error=error)


@app.route("/google-login")
def google_login():
    if not google_auth_configured():
        flash("구글 로그인 설정이 아직 완료되지 않았습니다.", "error")
        return redirect(url_for("login"))
    return redirect(get_login_url(APP_BASE_URL))


@app.route("/logout", methods=["POST"])
def logout():
    resp = make_response(redirect(url_for("login")))
    return _clear_auth_cookie(resp)


@app.route("/dashboard")
@login_required
def dashboard():
    return redirect(url_for("trends"))


@app.route("/trends", methods=["GET", "POST"])
@login_required
def trends():
    ws = _workspace()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "collect":
            from modules.trend_collector import collect_all_trends
            ws["trends"] = collect_all_trends()
            flash("트렌드 수집이 완료되었습니다.", "success")
        elif action == "add_manual":
            for kw in _tags_from_text(request.form.get("manual_keywords", "")):
                if kw not in ws["manual_keywords"]:
                    ws["manual_keywords"].append(kw)
        elif action == "remove_manual":
            kw = request.form.get("keyword", "")
            ws["manual_keywords"] = [k for k in ws["manual_keywords"] if k != kw]
        elif action == "clear_manual":
            ws["manual_keywords"] = []
        elif action == "select_keywords":
            chosen = request.form.getlist("keywords")
            for kw in ws["manual_keywords"]:
                if kw not in chosen:
                    chosen.append(kw)
            ws["selected_keywords"] = chosen
            flash(f"키워드 {len(chosen)}개를 선택했습니다.", "success")
            return redirect(url_for("content"))
        return redirect(url_for("trends"))
    return render_page("trends", TRENDS_TEMPLATE, ws=ws)


def _run_quick_generate(ws, title, keywords, tone):
    """본문 생성 + 이미지 생성을 이어서 백그라운드로 실행 (STEP2에서 바로 STEP4까지 건너뛰기용)."""
    from modules.content_generator import generate_blog_post
    from modules.image_generator import generate_images_for_post, insert_images_into_html

    def _log(msg):
        ws["quick_generate_log"].append(msg)

    try:
        _log("본문 생성 중...")
        result = generate_blog_post(title, keywords, tone)
        ws["post_title"] = result.get("title", title)
        ws["post_content_html"] = result.get("content_html", "")
        ws["post_meta_desc"] = result.get("meta_description", "")
        ws["post_tags"] = result.get("tags", [])
        ws["image_prompts"] = result.get("image_prompts", [])
        ws["final_html"] = ""
        ws["naver_content_html"] = ""
        _save_local(ws, ws["post_title"], ws["post_content_html"], ws["post_tags"], ws["post_meta_desc"])
        _log("본문 생성 완료. 이미지 생성 시작...")

        provider = os.getenv("IMAGE_PROVIDER", "pollinations")
        results = generate_images_for_post(ws["image_prompts"], provider, log_callback=_log)
        ws["final_html"] = insert_images_into_html(ws["post_content_html"], results)
        ws["image_data"] = [
            {k: v for k, v in r.items() if k != "bytes"} | {"has_bytes": bool(r.get("bytes"))}
            for r in results
        ]
        _save_local(ws, ws["post_title"], ws["final_html"], ws["post_tags"], ws["post_meta_desc"])
        _log("네이버용 버전도 다르게 준비하는 중 (중복 콘텐츠 방지)...")
        ws["naver_content_html"] = _build_naver_content(ws, ws["post_title"])
        _log("완료! 아래에서 구글용/네이버용 각각 바로 발행할 수 있습니다.")
    except Exception as exc:
        ws["quick_generate_error"] = str(exc)
        _log(f"오류: {exc}")
    finally:
        ws["quick_generate_running"] = False


@app.route("/content", methods=["GET", "POST"])
@login_required
def content():
    ws = _workspace()
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "suggest_topics":
                from modules.content_generator import suggest_topics
                keywords = ws.get("selected_keywords") or []
                if not keywords:
                    flash("먼저 트렌드 수집에서 키워드를 선택하거나 수동 키워드를 확정해주세요.", "error")
                    return redirect(url_for("trends"))
                count = int(request.form.get("topic_count", "10"))
                topics = suggest_topics(keywords, count)
                ws["topics"] = topics
                if topics:
                    flash(f"주제 {len(topics)}개가 추천되었습니다.", "success")
                else:
                    flash("주제 추천 결과가 비어 있습니다. 키워드를 더 구체적으로 선택해 다시 시도해주세요.", "error")
            elif action == "select_topic":
                idx = int(request.form.get("topic_index", "0"))
                topic = (ws.get("topics") or [])[idx]
                ws["post_topic"] = topic
                ws["post_title"] = topic.get("title", "")
                ws["topics"] = None
                ws["local_save_path"] = None
                ws["naver_content_html"] = ""
            elif action == "custom_title":
                ws["post_title"] = request.form.get("post_title", "").strip()
                ws["topics"] = None
                ws["local_save_path"] = None
                ws["naver_content_html"] = ""
            elif action == "generate_post":
                from modules.content_generator import generate_blog_post
                keywords = _tags_from_text(request.form.get("keywords", "")) or ws["selected_keywords"]
                result = generate_blog_post(request.form.get("title", ws["post_title"]), keywords, request.form.get("tone", "정보전달"))
                ws["post_title"] = result.get("title", ws["post_title"])
                ws["post_content_html"] = result.get("content_html", "")
                ws["post_meta_desc"] = result.get("meta_description", "")
                ws["post_tags"] = result.get("tags", [])
                ws["image_prompts"] = result.get("image_prompts", [])
                ws["final_html"] = ""
                ws["naver_content_html"] = ""
                _save_local(ws, ws["post_title"], ws["post_content_html"], ws["post_tags"], ws["post_meta_desc"])
                flash("본문이 생성되었습니다. (자동 저장됨)", "success")
            elif action == "quick_generate":
                if ws.get("quick_generate_running"):
                    flash("이미 본문+이미지 백그라운드 작성이 진행 중입니다.", "error")
                else:
                    keywords = _tags_from_text(request.form.get("keywords", "")) or ws["selected_keywords"]
                    title = request.form.get("title", ws["post_title"])
                    tone = request.form.get("tone", "정보전달")
                    ws["quick_generate_running"] = True
                    ws["quick_generate_log"] = []
                    ws["quick_generate_error"] = None
                    ws["local_save_path"] = None
                    threading.Thread(target=_run_quick_generate, args=(ws, title, keywords, tone), daemon=True).start()
                    flash("본문+이미지 백그라운드 작성을 시작했습니다. 발행 메뉴 상단에서 진행 상황을 볼 수 있어요.", "success")
            elif action == "save_edits":
                ws["post_title"] = request.form.get("title", ws["post_title"])
                ws["post_content_html"] = request.form.get("content_html", "")
                ws["post_tags"] = _tags_from_text(request.form.get("tags", ""))
                ws["post_meta_desc"] = request.form.get("meta_description", "")
                ws["final_html"] = ""
                ws["naver_content_html"] = ""
                _save_local(ws, ws["post_title"], ws["post_content_html"], ws["post_tags"], ws["post_meta_desc"])
                flash("수정 내용을 반영했습니다. (자동 저장됨)", "success")
            elif action == "refine":
                from modules.content_generator import refine_content
                instruction = request.form.get("instruction", "").strip()
                if not instruction:
                    flash("AI 수정 요청 내용을 입력해주세요.", "error")
                    return redirect(url_for("content"))
                if not ws.get("post_content_html"):
                    flash("수정할 본문이 없습니다. 먼저 본문을 생성해주세요.", "error")
                    return redirect(url_for("content"))
                try:
                    refined = refine_content(ws["post_content_html"], instruction)
                except Exception:
                    app.logger.exception("AI 수정 적용 실패 (instruction=%r)", instruction)
                    flash("AI 수정 적용 중 오류가 발생했습니다. LLM 서버/API 키 상태를 확인해주세요. 기존 본문은 그대로 남아있습니다.", "error")
                    return redirect(url_for("content"))
                if not refined or not refined.strip():
                    flash("AI가 빈 결과를 반환해 수정 내용을 적용하지 않았습니다. 요청 문구를 바꿔 다시 시도해주세요.", "error")
                    return redirect(url_for("content"))
                ws["post_content_html"] = refined
                ws["final_html"] = ""
                ws["naver_content_html"] = ""
                _save_local(ws, ws["post_title"], ws["post_content_html"], ws["post_tags"], ws["post_meta_desc"])
                flash("AI 수정이 적용되었습니다. (자동 저장됨)", "success")
        except Exception as exc:
            app.logger.exception("content() action=%r 처리 중 오류", action)
            flash(f"오류: {exc}", "error")
        return redirect(url_for("content"))
    return render_page("content", CONTENT_TEMPLATE, ws=ws)


@app.route("/media", methods=["GET", "POST"])
@login_required
def media():
    ws = _workspace()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "skip":
            ws["final_html"] = ws.get("post_content_html", "")
            ws["naver_content_html"] = ""
            flash("이미지 없이 발행 단계로 넘겼습니다.", "success")
            return redirect(url_for("publish"))
        if action == "generate_images":
            try:
                from modules.image_generator import generate_images_for_post, insert_images_into_html
                prompts = [request.form.get(f"prompt_{i}", "") for i in range(3)]
                provider = request.form.get("provider", "pollinations")
                results = generate_images_for_post(prompts, provider)
                ws["image_prompts"] = prompts
                ws["final_html"] = insert_images_into_html(ws["post_content_html"], results)
                ws["image_data"] = [
                    {k: v for k, v in r.items() if k != "bytes"} | {"has_bytes": bool(r.get("bytes"))}
                    for r in results
                ]
                _save_local(ws, ws["post_title"], ws["final_html"], ws["post_tags"], ws["post_meta_desc"])
                ws["naver_content_html"] = _build_naver_content(ws, ws["post_title"])
                flash("이미지 생성 및 삽입, 네이버용 버전 준비까지 완료되었습니다. (자동 저장됨)", "success")
            except Exception as exc:
                flash(f"이미지 생성 실패: {exc}", "error")
        return redirect(url_for("media"))
    return render_page("media", MEDIA_TEMPLATE, ws=ws)


def _build_naver_content(ws, title) -> str:
    """Blogger용 원문을 그대로 쓰지 않고, 중복 콘텐츠를 피하기 위해 다시 쓴 뒤
    같은 이미지를 재삽입하고 상하단에 Blogger 방문 링크를 넣은 네이버용 본문을 만든다."""
    base_html = ws.get("post_content_html") or ws.get("final_html") or ""
    if not base_html:
        return ws.get("final_html") or ""

    try:
        from modules.content_generator import rewrite_for_naver
        from modules.image_generator import insert_images_into_html
        rewritten = rewrite_for_naver(base_html, title)
        content_html = insert_images_into_html(rewritten, ws.get("image_data") or [])
    except Exception:
        content_html = ws.get("final_html") or base_html

    blog_url = os.getenv("BLOGGER_BLOG_URL", "").strip()
    if blog_url:
        # 네이버 발행 자동화는 태그별로 텍스트만 추출해 한 줄씩 입력하므로, URL을
        # 별도 <p>로 분리해야 네이버 에디터의 자동 링크 인식을 기대할 수 있다.
        link_html = f'<p>📌 이 글은 구글 블로그에도 같이 올려뒀어요.</p><p>{blog_url}</p>'
        content_html = link_html + content_html + link_html
    return content_html


_BLOCK_TAG_RE = re.compile(r"<(/?)([a-zA-Z0-9]+)([^>]*?)(/?)>", re.S)
_VOID_TAGS = {"img", "br", "hr", "meta", "input"}


def _split_content_blocks(html: str) -> list[str]:
    """HTML을 최상위(depth 0) 태그 단위로 잘라 블록별 복사가 가능하게 만든다."""
    blocks = []
    depth = 0
    start = None
    for m in _BLOCK_TAG_RE.finditer(html):
        closing, tag, _attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        void = bool(selfclose) or tag in _VOID_TAGS
        if not closing:
            if depth == 0:
                start = m.start()
            if void:
                if depth == 0:
                    blocks.append(html[start:m.end()])
                    start = None
            else:
                depth += 1
        else:
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    blocks.append(html[start:m.end()])
                    start = None
    return [b for b in blocks if b.strip()]


def _naver_blocks_for_display(naver_content_html: str) -> list[dict]:
    """네이버 수동 발행용: 블록별로 나누고, 이미지 블록이면 img src를 함께 반환."""
    blocks = []
    for block_html in _split_content_blocks(naver_content_html or ""):
        img_match = re.search(r'<img[^>]*\ssrc="([^"]*)"', block_html)
        blocks.append({"html": block_html, "img_url": img_match.group(1) if img_match else None})
    return blocks


def _build_blogger_content(final_html: str) -> str:
    """네이버 블로그 방문 링크를 상하단에 카드 형태로 넣은 Blogger용 본문을 만든다 (교차 유입용)."""
    naver_blog_id = os.getenv("NAVER_BLOG_ID", "").strip()
    if not naver_blog_id:
        return final_html
    naver_url = f"https://blog.naver.com/{naver_blog_id}"
    link_html = (
        '<div style="margin:22px 0;padding:14px 18px;background:#f3f6fb;'
        'border-left:4px solid #03c75a;border-radius:8px;">'
        '<p style="margin:0;font-size:0.95em;color:#333;">'
        '📌 이 글은 네이버 블로그에도 올라와 있어요 · '
        f'<a href="{naver_url}" target="_blank" rel="noopener" '
        'style="color:#03c75a;font-weight:600;text-decoration:none;">네이버에서 보기</a>'
        '</p></div>'
    )
    return link_html + final_html + link_html


def _start_naver_publish(ws, title):
    from modules.naver_blog_poster import publish_post as naver_publish_post
    ws["naver_publish_log"] = []
    ws["naver_publish_result"] = None
    ws["naver_publish_running"] = True
    tags = ws.get("post_tags", [])

    def _run(ws=ws, title=title, tags=tags):
        def _on_log(msg):
            ws["naver_publish_log"].append(msg)
        try:
            content_html = ws.get("naver_content_html")
            if content_html:
                _on_log("이미 준비된 네이버용 버전을 사용합니다.")
            else:
                _on_log("네이버용으로 다시 쓰는 중 (Blogger 원문과 중복 방지)...")
                content_html = _build_naver_content(ws, title)
            _on_log("네이버 발행 시작...")
            ws["naver_publish_result"] = naver_publish_post(title, content_html, tags, log_callback=_on_log)
        except Exception as exc:
            ws["naver_publish_result"] = {"url": None, "error": str(exc), "screenshot": None}
        finally:
            ws["naver_publish_running"] = False

    threading.Thread(target=_run, daemon=True).start()


@app.route("/publish", methods=["GET", "POST"])
@login_required
def publish():
    ws = _workspace()
    final_html = ws.get("final_html") or ws.get("post_content_html", "")
    if request.method == "POST":
        action = request.form.get("action")
        title = request.form.get("title", ws.get("post_title", ""))
        try:
            if action == "save_local":
                path = _save_local(ws, title, final_html, ws.get("post_tags", []), ws.get("post_meta_desc", ""))
                flash(f"로컬 저장 완료: {path.name}", "success")
            elif action in ("blogger_draft", "blogger_publish"):
                from modules.blogger_publisher import publish_post
                result = publish_post(title, _build_blogger_content(final_html), ws.get("post_tags", []), is_draft=(action == "blogger_draft"))
                ws["publish_result"] = result
                if not result.get("error"):
                    ws["publish_history"].append(result)
                flash("Blogger 작업이 완료되었습니다.", "success")
            elif action == "naver_publish":
                if ws.get("naver_publish_running"):
                    flash("이미 네이버 발행이 진행 중입니다.", "error")
                else:
                    _start_naver_publish(ws, title)
                    flash("네이버 발행을 시작했습니다. 진행 상황이 아래에 표시됩니다.", "success")
            elif action == "refresh_recent":
                from modules.blogger_publisher import list_recent_posts
                ws["blogger_recent_posts"] = list_recent_posts()
            elif action == "delete_blogger":
                from modules.blogger_publisher import delete_post, list_recent_posts
                delete_post(request.form.get("post_id", ""))
                ws["blogger_recent_posts"] = list_recent_posts()
                flash("Blogger 글을 삭제했습니다.", "success")
            elif action == "dismiss_quick_generate":
                ws["quick_generate_log"] = []
                ws["quick_generate_error"] = None
            elif action == "new_post":
                ws["post_topic"] = None
                ws["post_title"] = ""
                ws["post_content_html"] = ""
                ws["post_meta_desc"] = ""
                ws["post_tags"] = []
                ws["image_prompts"] = []
                ws["image_data"] = []
                ws["final_html"] = ""
                ws["naver_content_html"] = ""
                ws["publish_result"] = None
                ws["naver_publish_result"] = None
                ws["naver_publish_running"] = False
                ws["naver_publish_log"] = []
                ws["local_save_path"] = None
                ws["quick_generate_running"] = False
                ws["quick_generate_log"] = []
                ws["quick_generate_error"] = None
                ws["topics"] = None
                ws["selected_keywords"] = []
                flash("새 글을 시작합니다.", "success")
                return redirect(url_for("trends"))
        except Exception as exc:
            if action and action.startswith("blogger"):
                ws["publish_result"] = {"error": str(exc)}
            flash(f"오류: {exc}", "error")
        return redirect(url_for("publish"))
    naver_blocks = _naver_blocks_for_display(ws.get("naver_content_html"))
    return render_page("publish", PUBLISH_TEMPLATE, ws=ws, final_html=final_html, naver_blocks=naver_blocks)


@app.route("/saved", methods=["GET", "POST"])
@login_required
def saved():
    ws = _workspace()
    if request.method == "POST":
        action = request.form.get("action")
        try:
            path = _safe_saved_path(request.form.get("file", "")) if request.form.get("file") else None
            if action == "load" and path:
                data = json.loads(path.read_text(encoding="utf-8"))
                ws["post_title"] = data.get("title", "")
                ws["post_content_html"] = data.get("content_html", "")
                ws["final_html"] = data.get("content_html", "")
                ws["post_tags"] = data.get("tags", [])
                ws["post_meta_desc"] = data.get("meta_description", "")
                flash("저장된 글을 현재 작업으로 불러왔습니다.", "success")
                return redirect(url_for("publish"))
            if action == "delete" and path:
                path.unlink()
                flash("저장된 글을 삭제했습니다.", "success")
            if action == "update" and path:
                payload = {
                    "title": request.form.get("title", ""),
                    "content_html": request.form.get("content_html", ""),
                    "tags": _tags_from_text(request.form.get("tags", "")),
                    "meta_description": request.form.get("meta_description", ""),
                    "saved_at": request.form.get("saved_at", ""),
                    "updated_at": datetime.now().isoformat(),
                }
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                flash("저장된 글을 수정했습니다.", "success")
            if action == "publish" and path:
                from modules.blogger_publisher import publish_post
                data = json.loads(path.read_text(encoding="utf-8"))
                result = publish_post(data.get("title", ""), data.get("content_html", ""), data.get("tags", []), is_draft=False)
                ws["publish_result"] = result
                flash("저장된 글을 Blogger에 발행했습니다.", "success")
        except Exception as exc:
            flash(f"오류: {exc}", "error")
        return redirect(url_for("saved"))
    return render_page("saved", SAVED_TEMPLATE, ws=ws, posts=_saved_posts())


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    ws = _workspace()
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "save_env":
                _save_env(request.form)
                flash("설정이 .env 파일에 저장되었습니다. 서비스 재시작 후 완전히 반영됩니다.", "success")
            elif action == "upload_client_secret":
                upload = request.files.get("client_secret")
                if upload and upload.filename:
                    Path("client_secret.json").write_bytes(upload.read())
                    flash("client_secret.json 저장 완료", "success")
            elif action == "upload_login_secret":
                upload = request.files.get("login_client_secret")
                if upload and upload.filename:
                    Path("login_client_secret.json").write_bytes(upload.read())
                    flash("login_client_secret.json 저장 완료", "success")
            elif action == "oauth_start":
                from modules.blogger_publisher import get_oauth_url
                redirect_uri = request.form.get("redirect_uri", "http://localhost")
                result = get_oauth_url(redirect_uri=redirect_uri)
                ws["oauth_url"] = result["url"]
                ws["oauth_code_verifier"] = result["code_verifier"]
                ws["oauth_redirect_uri"] = redirect_uri
            elif action == "oauth_complete":
                from modules.blogger_publisher import complete_oauth
                complete_oauth(request.form.get("oauth_code", ""), ws.get("oauth_redirect_uri") or "http://localhost", ws.get("oauth_code_verifier") or "")
                ws["oauth_url"] = None
                ws["oauth_code_verifier"] = None
                ws["oauth_redirect_uri"] = None
                flash("Google OAuth 인증 성공", "success")
            elif action == "oauth_reset":
                Path("token.json").unlink(missing_ok=True)
                flash("token.json을 삭제했습니다. 재인증을 진행하세요.", "success")
            elif action == "blog_test":
                from modules.blogger_publisher import test_blog_connection
                result = test_blog_connection(request.form.get("blogger_blog_id", ""))
                flash(("연결 성공: " + result.get("blog_name", "")) if result.get("ok") else "연결 실패: " + result.get("error", ""), "success" if result.get("ok") else "error")
            elif action == "naver_login_start":
                from modules.naver_blog_poster import start_interactive_login
                state = start_interactive_login()
                if state.get("screenshot"):
                    state["screenshot_b64"] = base64.b64encode(state.pop("screenshot")).decode("ascii")
                ws["naver_login_state"] = state
            elif action == "naver_login_submit":
                from modules.naver_blog_poster import submit_login_challenge
                state = submit_login_challenge(request.form.get("session_id", ""), request.form.get("answer", ""))
                if state.get("screenshot"):
                    state["screenshot_b64"] = base64.b64encode(state.pop("screenshot")).decode("ascii")
                ws["naver_login_state"] = state
            elif action == "naver_login_cancel":
                from modules.naver_blog_poster import cancel_login_challenge
                state = ws.get("naver_login_state") or {}
                if state.get("session_id"):
                    cancel_login_challenge(state["session_id"])
                ws["naver_login_state"] = None
        except Exception as exc:
            flash(f"오류: {exc}", "error")
        return redirect(url_for("settings"))
    return render_page("settings", SETTINGS_TEMPLATE, ws=ws)


@app.route("/logs", methods=["GET", "POST"])
@login_required
def logs():
    if request.method == "POST":
        name = secure_filename(request.form.get("file", ""))
        path = ERROR_DIR / name
        if path.exists() and path.parent.resolve() == ERROR_DIR.resolve():
            path.unlink()
            flash("오류 스크린샷을 삭제했습니다.", "success")
        return redirect(url_for("logs"))
    shots = sorted(ERROR_DIR.glob("*.png"), reverse=True) if ERROR_DIR.exists() else []
    return render_page("logs", LOGS_TEMPLATE, shots=shots)


@app.route("/logs/image/<name>")
@login_required
def log_image(name: str):
    path = ERROR_DIR / secure_filename(name)
    if not path.exists() or path.parent.resolve() != ERROR_DIR.resolve():
        return "not found", 404
    return send_file(path)


@app.route("/manual")
@login_required
def manual():
    return render_page("manual", MANUAL_TEMPLATE)


@app.route("/healthz")
def healthz():
    """워치독(scripts/healthcheck.sh)이 주기적으로 호출하는 자체 점검 엔드포인트.
    프로세스가 살아있어도 응답이 멈춰있거나 데이터 디스크 쓰기가 막힌 경우를
    감지하기 위한 용도이므로, 외부 API(LLM/Blogger/네이버) 호출은 하지 않는다.
    """
    checks: dict[str, bool | str] = {}
    ok = True

    try:
        DATA_DIR.mkdir(exist_ok=True)
        probe = DATA_DIR / ".healthz_probe"
        probe.write_text(str(time.time()), encoding="utf-8")
        probe.unlink()
        checks["data_dir_writable"] = True
    except OSError as exc:
        checks["data_dir_writable"] = False
        checks["data_dir_error"] = str(exc)
        ok = False

    body = {
        "ok": ok,
        "app": "flask-blog-dashboard",
        "uptime_seconds": round(time.monotonic() - _START_TIME, 1),
        "checks": checks,
    }
    return body, (200 if ok else 503)


def _status() -> dict:
    from modules.blogger_publisher import check_auth_status
    from modules.content_generator import check_llm_status
    from modules.naver_blog_poster import check_session_status
    return {
        "llm": check_llm_status(),
        "blogger": check_auth_status(),
        "naver": check_session_status(),
        "image_provider": os.getenv("IMAGE_PROVIDER", "pollinations"),
    }


def render_login(error: str = ""):
    return render_template_string(LOGIN_TEMPLATE, css=BASE_CSS, error=error, google_enabled=google_auth_configured(), password_enabled=is_password_configured())


def render_page(active: str, body_template: str, **ctx):
    body = render_template_string(body_template, active=active, **ctx)
    ws = ctx.get("ws") or _workspace()
    return render_template_string(BASE_TEMPLATE, css=BASE_CSS, active=active, body=body, user=_current_user(), status=_status(), ws=ws)


BASE_CSS = """
<style>
:root { color-scheme: light; --ink:#172033; --muted:#657085; --line:#e3e8f2; --panel:#fff; --bg:#f4f6fb; --nav:#111827; --blue:#2563eb; --blue-ink:#1d4ed8; --green:#16a34a; --red:#dc2626; --amber:#b45309; --radius:12px; --shadow:0 1px 2px rgba(16,24,40,.05), 0 1px 3px rgba(16,24,40,.06); }
* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); -webkit-font-smoothing:antialiased; }
a { color:var(--blue-ink); }
.shell { min-height:100vh; display:grid; grid-template-columns:252px 1fr; }
.nav-toggle-checkbox { display:none; }
.nav-toggle-label { display:none; }
.nav-backdrop { display:none; }
aside { background:var(--nav); color:white; padding:20px 14px; position:sticky; top:0; height:100vh; overflow:auto; transition:transform .25s ease; }
aside h1 { font-size:18px; margin:0 0 4px; }
aside .caption { color:#9ca3af; font-size:12px; margin-bottom:18px; }
.nav-section { margin:18px 0 8px; color:#8b95a8; font-size:12px; font-weight:700; letter-spacing:.04em; text-transform:uppercase; }
.nav-link { display:flex; gap:10px; align-items:center; color:#d1d5db; text-decoration:none; padding:11px 12px; border-radius:9px; margin:3px 0; font-size:14.5px; transition:background .15s; }
.nav-link:hover { background:#1f2937; color:white; }
.nav-link.active { background:var(--blue); color:white; font-weight:700; }
.status { border-top:1px solid #273244; margin-top:18px; padding-top:14px; font-size:12px; color:#cbd5e1; line-height:1.8; }
main { padding:26px 32px 48px; max-width:1320px; width:100%; }
.topbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; gap:10px; }
.topbar form { margin:0; }
.bg-status { display:inline-flex; align-items:center; gap:6px; background:#fffbeb; color:#92400e; border:1px solid #fde68a; border-radius:999px; padding:6px 12px; font-size:12.5px; font-weight:700; text-decoration:none; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow); padding:22px; margin:0 0 18px; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
.grid3 { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
.grid4 { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
.header { background:linear-gradient(135deg,#2563eb,#1e3a8a); color:white; padding:14px 18px; border-radius:var(--radius); font-weight:800; margin-bottom:18px; box-shadow:var(--shadow); }
.notice { background:#eff6ff; border-left:4px solid var(--blue); padding:12px 14px; border-radius:0 8px 8px 0; margin:10px 0; }
.notice.success { background:#f0fdf4; border-left-color:var(--green); }
.notice.error { background:#fef2f2; border-left-color:var(--red); }
.notice.warn { background:#fffbeb; border-left-color:#f59e0b; }
.flash { padding:11px 14px; border-radius:8px; margin:8px 0; background:#eff6ff; border:1px solid #bfdbfe; }
.flash.success { background:#f0fdf4; border-color:#bbf7d0; }
.flash.error { background:#fef2f2; border-color:#fecaca; }
.btn, button { border:0; border-radius:8px; background:#374151; color:white; padding:10px 15px; font-weight:700; text-decoration:none; cursor:pointer; display:inline-block; font-size:14px; transition:filter .12s, transform .05s; }
.btn:hover, button:hover { filter:brightness(1.08); }
.btn:active, button:active { transform:translateY(1px); }
.btn.primary, button.primary { background:var(--blue); }
.btn.success, button.success { background:var(--green); }
.btn.danger, button.danger { background:var(--red); }
.btn.small, button.small { padding:7px 10px; font-size:12.5px; }
input, select, textarea { width:100%; padding:10px 12px; border:1px solid #cfd7e6; border-radius:8px; background:white; font:inherit; }
input:focus, select:focus, textarea:focus { outline:2px solid #bfdbfe; border-color:var(--blue); }
textarea { min-height:160px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
label { display:block; font-size:13px; font-weight:700; color:#334155; margin:10px 0 6px; }
.inline { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.chip { display:inline-flex; align-items:center; gap:5px; background:#eef2ff; color:#3730a3; padding:5px 9px; border-radius:999px; font-size:13px; font-weight:700; margin:3px; }
.checkbox-list { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
.checkbox { border:1px solid var(--line); background:#fff; border-radius:8px; padding:10px; min-height:54px; }
.preview { border:1px solid var(--line); border-radius:var(--radius); padding:18px; background:#fff; overflow:auto; }
.card { border:1px solid var(--line); border-radius:var(--radius); padding:14px; background:#fff; box-shadow:var(--shadow); }
.nvblock { border:1px solid var(--line); border-radius:10px; padding:12px 14px; background:#fff; margin-bottom:10px; }
.nvblock-content { overflow:auto; margin-bottom:8px; }
.nvblock-content img { max-width:100%; height:auto; border-radius:8px; }
.nvblock-actions { justify-content:flex-end; }
.user-menu { position:relative; }
.user-menu-dropdown { display:none; position:absolute; right:0; top:calc(100% + 6px); background:var(--panel); border:1px solid var(--line); border-radius:10px; box-shadow:var(--shadow); padding:12px; min-width:220px; z-index:600; }
.user-menu-dropdown.open { display:block; }
.muted { color:var(--muted); font-size:13px; }
hr { border:0; border-top:1px solid var(--line); margin:18px 0; }
code, pre { background:#f1f5f9; border-radius:6px; padding:2px 5px; }
pre { padding:12px; overflow:auto; white-space:pre-wrap; }
details { border:1px solid var(--line); border-radius:var(--radius); padding:12px; background:#fff; margin:10px 0; }
summary { cursor:pointer; font-weight:800; }
.login { min-height:100vh; display:grid; place-items:center; padding:24px; }
.login .panel { max-width:430px; width:100%; }

/* ── 모바일: 접이식 사이드바 (체크박스 해크, JS 불필요) ── */
@media (max-width:900px) {
  .shell { grid-template-columns:1fr; }
  aside {
    position:fixed; top:0; left:0; height:100vh; width:264px; z-index:1000;
    transform:translateX(-100%); box-shadow:2px 0 16px rgba(0,0,0,.25);
  }
  .nav-toggle-checkbox:checked ~ aside { transform:translateX(0); }
  .nav-toggle-checkbox:checked ~ .nav-backdrop {
    display:block; position:fixed; inset:0; background:rgba(15,23,42,.45); z-index:999;
  }
  main { padding:16px 16px 32px; }
  .grid2, .grid3, .grid4, .checkbox-list { grid-template-columns:1fr; }
  /* 상단 바(햄버거+로그아웃) 고정: main의 padding을 상쇄하고 화면 끝까지 붙인 뒤 sticky */
  .topbar {
    position:sticky; top:0; z-index:500;
    background:var(--bg); margin:-16px -16px 16px; padding:12px 16px;
    border-bottom:1px solid var(--line);
  }
  .bg-status { max-width:150px; }
  /* 햄버거 버튼: topbar 안의 일반 flex 아이템으로 배치 (더 이상 position:fixed 아님) */
  .topbar .nav-toggle-label {
    display:inline-flex; align-items:center; justify-content:center; flex:0 0 auto;
    width:38px; height:38px; border-radius:8px; line-height:1; box-sizing:border-box;
    background:var(--nav); color:white; font-size:18px; cursor:pointer;
  }
  .btn, button { min-height:44px; padding:11px 16px; }
  .btn.small, button.small { min-height:38px; }
  /* 로그아웃 버튼을 햄버거와 같은 38px 높이로 맞춤 */
  .topbar button.small {
    height:38px; min-height:38px; box-sizing:border-box;
    display:inline-flex; align-items:center; justify-content:center; line-height:1;
  }
  input, select, textarea { min-height:44px; font-size:16px; } /* 16px: iOS 자동 확대 방지 */
}

/* ── 페이지 전환/폼 제출 시 전체화면 로딩 오버레이 ── */
.page-loading {
  display:none; position:fixed; inset:0; z-index:2000;
  background:rgba(15,23,42,.55); backdrop-filter:blur(2px);
  align-items:center; justify-content:center; flex-direction:column; gap:14px;
}
.page-loading.show { display:flex; }
.page-loading .spinner { font-size:46px; animation:page-loading-spin 1s linear infinite; }
.page-loading .msg { color:white; font-weight:700; font-size:14px; }
@keyframes page-loading-spin { to { transform:rotate(360deg); } }
</style>
"""

PAGE_LOADING_HTML = """
<div class="page-loading" id="page-loading"><div class="spinner">⏳</div><div class="msg">처리 중입니다...</div></div>
<script>
(function(){
  var overlay = document.getElementById('page-loading');
  function show(){ overlay.classList.add('show'); }
  document.addEventListener('submit', function(){ show(); });
  document.addEventListener('click', function(e){
    var a = e.target.closest('a');
    if (a && a.href && !a.target && a.origin === location.origin) { show(); }
  });
  window.addEventListener('pageshow', function(){ overlay.classList.remove('show'); });
})();
</script>
"""

BASE_TEMPLATE = """
<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>AI 블로그 자동화</title>{{ css|safe }}</head>
<body>{{ page_loading|safe }}<div class="shell">
<input type="checkbox" id="nav-toggle" class="nav-toggle-checkbox">
<label for="nav-toggle" class="nav-backdrop" aria-label="메뉴 닫기"></label>
<aside><h1>AI 블로그 자동화</h1><div class="caption">Trends → AI → Media → Publish</div>
<div class="nav-section">프로세스</div>
<a class="nav-link {{ 'active' if active=='trends' else '' }}" href="{{ url_for('trends') }}">📊 트렌드 수집</a>
<a class="nav-link {{ 'active' if active=='content' else '' }}" href="{{ url_for('content') }}">✍️ 콘텐츠 작성</a>
<a class="nav-link {{ 'active' if active=='media' else '' }}" href="{{ url_for('media') }}">🎨 미디어</a>
<a class="nav-link {{ 'active' if active=='publish' else '' }}" href="{{ url_for('publish') }}">🚀 발행</a>
<div class="nav-section">관리</div>
<a class="nav-link {{ 'active' if active=='saved' else '' }}" href="{{ url_for('saved') }}">📂 저장된 글</a>
<a class="nav-link {{ 'active' if active=='settings' else '' }}" href="{{ url_for('settings') }}">⚙️ 설정</a>
<a class="nav-link {{ 'active' if active=='logs' else '' }}" href="{{ url_for('logs') }}">🪵 오류 로그</a>
<a class="nav-link {{ 'active' if active=='manual' else '' }}" href="{{ url_for('manual') }}">📚 매뉴얼</a>
<div class="status"><b>API 상태</b><br>{{ '✅' if status.llm.vllm_available else '❌' }} vLLM · {{ '✅' if status.llm.claude_available else '⚪' }} Claude<br>{{ '✅' if status.blogger.ready else '❌' }} Blogger · {{ '✅' if status.naver.ready else '❌' }} 네이버<br>🖼️ {{ status.image_provider }}</div>
</aside><main><div class="topbar"><label for="nav-toggle" class="nav-toggle-label" aria-label="메뉴 열기">☰</label>{% if ws.quick_generate_running or ws.naver_publish_running %}<a href="{{ url_for('publish') }}" class="bg-status">{% if ws.quick_generate_running %}⚡ 본문+이미지 작성 중…{% endif %}{% if ws.quick_generate_running and ws.naver_publish_running %} · {% endif %}{% if ws.naver_publish_running %}🟢 네이버 발행 중…{% endif %}</a>{% endif %}<div class="inline" style="margin-left:auto"><div class="user-menu"><button type="button" class="small" id="user-menu-btn">🟢 로그인됨 ▾</button><div class="user-menu-dropdown" id="user-menu-dropdown"><div class="muted" style="margin-bottom:10px;word-break:break-all">{{ user }}</div><form method="post" action="{{ url_for('logout') }}"><button class="small danger" type="submit" style="width:100%">로그아웃</button></form></div></div></div></div>
<script>(function(){var btn=document.getElementById('user-menu-btn');var dd=document.getElementById('user-menu-dropdown');if(!btn||!dd)return;btn.addEventListener('click',function(e){e.stopPropagation();dd.classList.toggle('open');});document.addEventListener('click',function(e){if(!dd.contains(e.target)&&e.target!==btn){dd.classList.remove('open');}});})();</script>
{% with messages = get_flashed_messages(with_categories=true) %}{% for cat,msg in messages %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}{% endwith %}
{{ body|safe }}</main></div></body></html>
"""

LOGIN_TEMPLATE = """
<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>AI 블로그 자동화</title>{{ css|safe }}</head>
<body class="login">{{ page_loading|safe }}<section class="panel"><h2>로그인이 필요합니다</h2>{% if error %}<p class="notice error">{{ error }}</p>{% endif %}
{% if google_enabled %}<p><a class="btn primary" href="{{ url_for('google_login') }}">구글 계정으로 로그인</a></p>{% endif %}
{% if password_enabled %}<form method="post"><label>비밀번호</label><input type="password" name="password" autocomplete="current-password" required><button class="primary" type="submit">비밀번호로 로그인</button></form>{% endif %}
{% if not google_enabled and not password_enabled %}<p class="notice error">로그인 설정이 없습니다. .env의 APP_PASSWORD 또는 Google 로그인 설정을 확인하세요.</p>{% endif %}</section></body></html>
"""

TRENDS_TEMPLATE = """
<div class="header">📊 STEP 1 · 트렌드 수집</div>
<div class="panel"><p class="notice">Google 트렌드, 네이버, signal.bz에서 실시간 키워드를 수집하거나 직접 입력합니다.</p><form method="post"><input type="hidden" name="action" value="collect"><button class="primary">트렌드 수집 시작</button></form></div>
<div class="panel"><h3>수동 키워드 입력</h3><form method="post" class="inline"><input type="hidden" name="action" value="add_manual"><input name="manual_keywords" placeholder="예: 장윤정, 구속송치, 연예인 논란"><button>추가</button></form>{% for kw in ws.manual_keywords %}<form method="post" style="display:inline"><input type="hidden" name="action" value="remove_manual"><input type="hidden" name="keyword" value="{{ kw }}"><button class="small">✕ {{ kw }}</button></form>{% endfor %}{% if ws.manual_keywords %}<form method="post"><input type="hidden" name="action" value="clear_manual"><button class="small danger">수동 키워드 전체 초기화</button></form>{% endif %}</div>
<form method="post"><input type="hidden" name="action" value="select_keywords">
{% if ws.trends %}<div class="panel"><h3>IT 뉴스 트렌드</h3>{% for kw in ws.trends.it_news[:20] %}<p><code>{{ '%02d'|format(kw.rank) }}</code> <b>{{ kw.keyword }}</b> <span class="muted">{{ kw.traffic }}</span></p>{% else %}<p class="muted">데이터 없음</p>{% endfor %}</div><div class="panel"><h3>자동 수집 키워드 선택</h3><div class="checkbox-list">{% for kw in ws.trends.merged %}<label class="checkbox"><input type="checkbox" name="keywords" value="{{ kw.keyword }}" {% if kw.keyword in ws.selected_keywords %}checked{% endif %}> <b>{{ kw.keyword }}</b><br><span class="muted">{{ kw.source }} · {{ kw.traffic }} {{ kw.caret }}</span></label>{% endfor %}</div></div>{% endif %}
{% if ws.manual_keywords or ws.trends %}<div class="panel"><h3>키워드 확정</h3>{% if ws.manual_keywords %}<p class="muted">수동 키워드는 자동으로 포함됩니다.</p>{% for kw in ws.manual_keywords %}<span class="chip">{{ kw }}</span>{% endfor %}{% endif %}<hr><button class="primary">선택한 키워드로 콘텐츠 작성</button></div>{% endif %}</form>
{% if ws.selected_keywords %}<div class="panel"><b>선택된 키워드:</b> {% for kw in ws.selected_keywords %}<span class="chip">{{ kw }}</span>{% endfor %}</div>{% endif %}
"""

CONTENT_TEMPLATE = """
<div class="header">✍️ STEP 2 · 콘텐츠 작성</div>{% if not ws.selected_keywords %}<div class="notice warn">먼저 트렌드 수집에서 키워드를 선택해주세요.</div>{% else %}<div class="panel"><h3>2-1 · 주제 선정</h3><p>{% for kw in ws.selected_keywords %}<span class="chip">{{ kw }}</span>{% endfor %}</p><form method="post" class="inline"><input type="hidden" name="action" value="suggest_topics"><label>추천 주제 수 <input type="number" name="topic_count" value="10" min="3" max="15"></label><button class="primary">주제 추천 받기</button></form><form method="post"><input type="hidden" name="action" value="custom_title"><label>직접 제목 입력</label><div class="inline"><input name="post_title" value="{{ ws.post_title }}"><button>이 제목 사용</button></div></form></div>{% if ws.topics %}<div class="panel"><h3>추천 주제 목록</h3>{% for topic in ws.topics %}<div class="card"><h4>{{ loop.index }}. {{ topic.title }}</h4><p class="muted">{{ topic.topic }} · {{ topic.reason }}</p>{% for kw in topic.keywords %}<span class="chip">{{ kw }}</span>{% endfor %}<form method="post"><input type="hidden" name="action" value="select_topic"><input type="hidden" name="topic_index" value="{{ loop.index0 }}"><button class="primary small">선택</button></form></div>{% endfor %}</div>{% endif %}{% if ws.post_title %}<div class="panel"><h3>2-2 · 본문 생성</h3>{% if ws.quick_generate_running %}<p class="notice warn">⚡ 본문+이미지 백그라운드 작성이 진행 중입니다. 발행 메뉴 상단에서 진행 상황을 확인하세요.</p>{% endif %}<form method="post"><div class="grid3"><div><label>제목</label><input name="title" value="{{ ws.post_title }}"></div><div><label>톤앤매너</label><select name="tone"><option>정보전달</option><option>친근한</option><option>전문적</option><option>뉴스형</option></select></div><div><label>키워드</label><input name="keywords" value="{{ (ws.post_topic.keywords if ws.post_topic else ws.selected_keywords)|join(', ') }}"></div></div><div class="grid2"><button class="primary" name="action" value="generate_post">본문 생성</button><button class="success" name="action" value="quick_generate">⚡ 본문+이미지 동시 작성 (백그라운드)</button></div></form></div>{% endif %}{% if ws.post_content_html %}<div class="grid2"><div class="panel"><h3>본문 편집</h3><form method="post"><input type="hidden" name="action" value="save_edits"><label>제목</label><input name="title" value="{{ ws.post_title }}"><label>HTML 본문</label><textarea name="content_html" style="min-height:420px">{{ ws.post_content_html }}</textarea><label>태그</label><input name="tags" value="{{ ws.post_tags|join(', ') }}"><label>메타 설명</label><textarea name="meta_description" style="min-height:70px">{{ ws.post_meta_desc }}</textarea><button class="primary">저장</button></form><hr><form method="post"><input type="hidden" name="action" value="refine"><label>AI 수정 요청</label><input name="instruction" placeholder="예: 더 친근하게" required><button>AI 수정 적용</button></form></div><div class="panel"><h3>미리보기</h3><div class="preview"><h2>{{ ws.post_title }}</h2>{{ ws.post_content_html|safe }}</div><p><a class="btn primary" href="{{ url_for('media') }}">미디어로 이동</a></p></div></div>{% endif %}{% endif %}
"""

MEDIA_TEMPLATE = """
<div class="header">🎨 STEP 3 · 미디어</div>{% if not ws.post_content_html %}<div class="notice warn">먼저 콘텐츠 작성 단계를 완료해주세요.</div>{% else %}<div class="panel"><form method="post"><input type="hidden" name="action" value="generate_images"><label>이미지 생성 방식</label><select name="provider"><option value="pollinations">Pollinations.ai</option><option value="huggingface">HuggingFace SD XL</option><option value="claude">Claude + Pollinations</option><option value="dalle">DALL-E 3</option></select><div class="grid3">{% for i in range(3) %}<div><label>이미지 {{ i+1 }} 설명</label><div class="inline"><input name="prompt_{{ i }}" id="mp-prompt-{{ i }}" value="{{ ws.image_prompts[i] if ws.image_prompts|length > i else ['blog post illustration','relevant image','article image'][i] }}"><button type="button" class="small mp-copy-input" data-target="mp-prompt-{{ i }}">📋</button></div></div>{% endfor %}</div><button class="primary">이미지 생성 & 삽입</button></form><form method="post" style="margin-top:10px"><input type="hidden" name="action" value="skip"><button>이미지 건너뛰기</button></form></div>{% if ws.image_data %}<div class="panel"><h3>생성 결과</h3><p class="muted">📋 버튼으로 이미지 생성 프롬프트를 복사해 Midjourney·Google Flow 등 다른 도구에도 바로 붙여넣을 수 있어요.</p><div class="grid3">{% for item in ws.image_data %}<div class="card">{% if item.url %}<img src="{{ item.url }}" style="width:100%;border-radius:6px">{% endif %}<p class="muted">{{ item.provider or 'failed' }}</p><p class="muted"><span class="mp-prompt-text">{{ item.prompt }}</span></p><div class="inline"><button type="button" class="small mp-copy-text">📋 프롬프트 복사</button></div>{% if item.error %}<p class="notice error">{{ item.error }}</p>{% endif %}</div>{% endfor %}</div><p><a class="btn primary" href="{{ url_for('publish') }}">발행으로 이동</a></p></div>{% endif %}<script>(function(){function flash(btn){var t=btn.textContent;btn.textContent='✅';setTimeout(function(){btn.textContent=t;},1200);}document.querySelectorAll('.mp-copy-input').forEach(function(btn){btn.addEventListener('click',function(){var input=document.getElementById(btn.dataset.target);navigator.clipboard.writeText(input.value).then(function(){flash(btn);}).catch(function(){alert('복사 실패: 브라우저 클립보드 권한을 확인해주세요.');});});});document.querySelectorAll('.mp-copy-text').forEach(function(btn){btn.addEventListener('click',function(){var span=btn.closest('.card').querySelector('.mp-prompt-text');var orig=btn.textContent;navigator.clipboard.writeText(span.textContent.trim()).then(function(){btn.textContent='✅ 복사됨';setTimeout(function(){btn.textContent=orig;},1200);}).catch(function(){alert('복사 실패: 브라우저 클립보드 권한을 확인해주세요.');});});});})();</script>{% endif %}
"""

PUBLISH_TEMPLATE = """
<div class="header">🚀 STEP 4 · 발행</div>{% if ws.quick_generate_running %}<div class="panel"><h3>⚡ 본문+이미지 백그라운드 작성 중...</h3><pre>{{ ws.quick_generate_log|join('\n') if ws.quick_generate_log else '시작하는 중...' }}</pre><p class="muted"><a class="btn" href="{{ url_for('publish') }}">🔄 지금 새로고침</a> · 완료되면 자동으로도 새로고침됩니다.</p><script>setTimeout(function(){ location.reload(); }, 2000);</script></div>{% elif ws.quick_generate_log %}<div class="panel"><h3>⚡ 백그라운드 작성 결과</h3><pre>{{ ws.quick_generate_log|join('\n') }}</pre>{% if ws.quick_generate_error %}<p class="notice error">{{ ws.quick_generate_error }}</p>{% else %}<p class="notice success">완료됐습니다. 아래에서 바로 확인/발행하세요.</p>{% endif %}<form method="post"><button name="action" value="dismiss_quick_generate">확인</button></form></div>{% endif %}{% if not final_html %}<div class="notice warn">콘텐츠를 먼저 작성해주세요.</div>{% else %}<div class="grid2"><div class="panel"><h3>최종 미리보기</h3><div class="preview"><h1>{{ ws.post_title }}</h1><p class="muted">태그: {{ ws.post_tags|join(', ') }}</p><hr>{{ final_html|safe }}</div></div><div class="panel" id="publish-panel"><h3>발행 설정</h3><form method="post"><label>제목 최종 확인</label><input name="title" value="{{ ws.post_title }}"><div class="grid2"><button name="action" value="save_local">로컬 저장</button><button name="action" value="blogger_draft">Blogger 임시저장</button><button class="primary" name="action" value="blogger_publish">구글 발행</button><button class="success" name="action" value="naver_publish">네이버 발행</button></div></form><hr><form method="post"><button name="action" value="refresh_recent">최근 Blogger 포스팅 새로고침</button></form><p><a href="{{ url_for('saved') }}">저장된 글 관리로 이동</a></p></div></div>{% endif %}{% if final_html %}<div class="panel" id="naver-manual"><h3>🟢 네이버 수동 발행용 (블록별 복사)</h3><p class="muted">자동 발행이 막히거나 직접 붙여넣고 싶을 때, 아래 블록을 순서대로 복사해 네이버 스마트에디터에 붙여넣으세요. 이미지는 다운로드하거나 클립보드로 바로 복사해 붙여넣을 수 있습니다.</p>{% if not ws.naver_content_html %}<p class="notice warn">콘텐츠 작성 단계에서 이미지 생성까지 완료하면 네이버용 버전이 여기 준비됩니다.</p>{% else %}<div class="nvblock"><div class="nvblock-content">{{ ws.post_title }}</div><div class="inline nvblock-actions"><button type="button" class="small nv-copy-text">📋 제목 복사</button></div></div><div class="nvblock"><div class="nvblock-content">{{ ws.post_tags|join(', ') }}</div><div class="inline nvblock-actions"><button type="button" class="small nv-copy-text">📋 태그 복사</button></div></div>{% for block in naver_blocks %}<div class="nvblock"><div class="nvblock-content">{{ block.html|safe }}</div><div class="inline nvblock-actions">{% if block.img_url %}<button type="button" class="small nv-download-img" data-url="{{ block.img_url }}">⬇️ 이미지 다운로드</button><button type="button" class="small nv-copy-img" data-url="{{ block.img_url }}">🖼️ 이미지 복사</button>{% else %}<button type="button" class="small nv-copy-text">📋 텍스트 복사</button>{% endif %}</div></div>{% endfor %}<script>(function(){function flash(btn){var t=btn.textContent;btn.textContent='✅ 복사됨';setTimeout(function(){btn.textContent=t;},1500);}document.querySelectorAll('#naver-manual .nv-copy-text').forEach(function(btn){btn.addEventListener('click',function(){var el=btn.closest('.nvblock').querySelector('.nvblock-content');navigator.clipboard.writeText(el.innerText.trim()).then(function(){flash(btn);}).catch(function(){alert('복사 실패: 브라우저 클립보드 권한을 확인해주세요.');});});});document.querySelectorAll('#naver-manual .nv-download-img').forEach(function(btn){btn.addEventListener('click',function(){var url=btn.dataset.url;fetch(url).then(function(r){return r.blob();}).then(function(blob){var a=document.createElement('a');var objUrl=URL.createObjectURL(blob);a.href=objUrl;a.download='naver-image.jpg';document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(objUrl);}).catch(function(){window.open(url,'_blank');});});});document.querySelectorAll('#naver-manual .nv-copy-img').forEach(function(btn){btn.addEventListener('click',function(){var url=btn.dataset.url;fetch(url).then(function(r){return r.blob();}).then(function(blob){return navigator.clipboard.write([new ClipboardItem({[blob.type]:blob})]);}).then(function(){flash(btn);}).catch(function(){alert('이미지 복사에 실패했습니다 (브라우저가 지원하지 않을 수 있어요). 다운로드 버튼을 이용해주세요.');});});});})();</script>{% endif %}</div>{% endif %}{% if ws.publish_result %}<div class="panel"><h3>Blogger 결과</h3>{% if ws.publish_result.error %}<p class="notice error">{{ ws.publish_result.error }}</p>{% else %}<p class="notice success">성공: <a href="{{ ws.publish_result.url }}" target="_blank">{{ ws.publish_result.url }}</a></p>{% endif %}</div>{% endif %}<div id="naver-progress">{% if ws.naver_publish_running %}<div class="panel"><h3>🟢 네이버 발행 진행 중...</h3><pre>{{ ws.naver_publish_log|join('\n') if ws.naver_publish_log else '시작하는 중...' }}</pre><p class="muted">보통 30초~1분 정도 걸립니다. 이 화면은 2초마다 자동으로 새로고침됩니다.</p><script>setTimeout(function(){ location.reload(); }, 2000);</script></div>{% endif %}{% if ws.naver_publish_result %}<div class="panel"><h3>네이버 결과</h3>{% if ws.naver_publish_result.error %}<p class="notice error">{{ ws.naver_publish_result.error }}</p>{% if ws.naver_publish_result.screenshot %}<p class="muted">스크린샷: {{ ws.naver_publish_result.screenshot }}</p>{% endif %}{% else %}<p class="notice success">성공: <a href="{{ ws.naver_publish_result.url }}" target="_blank">{{ ws.naver_publish_result.url }}</a></p>{% endif %}</div>{% endif %}</div>{% if ws.publish_result or ws.naver_publish_result %}<div class="panel"><form method="post"><button class="primary" name="action" value="new_post">✏️ 새 글 쓰기</button></form></div>{% endif %}{% if ws.naver_publish_running or ws.naver_publish_result %}<script>document.addEventListener('DOMContentLoaded',function(){var el=document.getElementById('naver-progress');if(el)el.scrollIntoView({block:'start'});});</script>{% elif ws.publish_result %}<script>document.addEventListener('DOMContentLoaded',function(){var el=document.getElementById('publish-panel');if(el)el.scrollIntoView({block:'start'});});</script>{% endif %}{% if ws.blogger_recent_posts %}<div class="panel"><h3>최근 Blogger 포스팅</h3>{% for p in ws.blogger_recent_posts %}<div class="card inline"><span>{{ '🟢' if p.status == 'LIVE' else '📝' }}</span><a href="{{ p.url }}" target="_blank">{{ p.title }}</a><span class="muted">{{ p.published[:10] if p.published }}</span><form method="post"><input type="hidden" name="post_id" value="{{ p.id }}"><button class="small danger" name="action" value="delete_blogger">삭제</button></form></div>{% endfor %}</div>{% endif %}
"""

SAVED_TEMPLATE = """
<div class="header">📂 저장된 글 관리</div>{% if not posts %}<div class="notice">저장된 글이 없습니다.</div>{% else %}<div class="panel"><p class="muted">총 {{ posts|length }}개의 저장된 글</p>{% for post in posts %}{% set data = post.data %}<details><summary>{{ data.title or post.name }} · {{ (data.saved_at or '')[:16].replace('T',' ') }}</summary><form method="post"><input type="hidden" name="action" value="update"><input type="hidden" name="file" value="{{ post.name }}"><input type="hidden" name="saved_at" value="{{ data.saved_at }}"><label>제목</label><input name="title" value="{{ data.title }}"><label>태그</label><input name="tags" value="{{ data.tags|join(', ') }}"><label>메타 설명</label><textarea name="meta_description" style="min-height:60px">{{ data.meta_description }}</textarea><label>본문 HTML</label><textarea name="content_html" style="min-height:260px">{{ data.content_html }}</textarea><button class="primary">저장</button></form><div class="inline" style="margin-top:8px"><form method="post"><input type="hidden" name="action" value="load"><input type="hidden" name="file" value="{{ post.name }}"><button>현재 글로 불러오기</button></form><form method="post"><input type="hidden" name="action" value="publish"><input type="hidden" name="file" value="{{ post.name }}"><button class="success">바로 Blogger 발행</button></form><form method="post"><input type="hidden" name="action" value="delete"><input type="hidden" name="file" value="{{ post.name }}"><button class="danger">삭제</button></form></div></details>{% endfor %}</div>{% endif %}
"""

SETTINGS_TEMPLATE = """
<div class="header">⚙️ 설정</div><form method="post"><input type="hidden" name="action" value="save_env"><div class="grid2"><div class="panel"><h3>LLM / 이미지</h3><label>LLM 서버 주소</label><input name="llm_addr" value="{{ os.getenv('LLM_ADDR','') }}"><label>LLM 모델명</label><input name="llm_model" value="{{ os.getenv('LLM_MODEL','') }}"><label>LLM API Key</label><input name="llm_api_key" value="{{ os.getenv('LLM_API_KEY','EMPTY') }}"><label>Claude 모델</label><input name="claude_model" value="{{ os.getenv('CLAUDE_MODEL','claude-sonnet-4-6') }}"><label>이미지 생성 방식</label><select name="image_provider"><option value="pollinations">pollinations</option><option value="huggingface">huggingface</option><option value="claude">claude</option><option value="dalle">dalle</option></select><label>Anthropic API Key</label><input name="anthropic_key" value="{{ os.getenv('ANTHROPIC_API_KEY','') }}"><label>OpenAI API Key</label><input name="openai_key" value="{{ os.getenv('OPENAI_API_KEY','') }}"><label>HuggingFace Token</label><input name="hf_token" value="{{ os.getenv('HUGGINGFACE_TOKEN','') }}"></div><div class="panel"><h3>블로그 / 로그인</h3><label>Blogger Blog ID</label><input name="blogger_blog_id" value="{{ os.getenv('BLOGGER_BLOG_ID','') }}"><label>Blogger 블로그 주소 (네이버 글 상하단 링크용)</label><input name="blogger_blog_url" value="{{ os.getenv('BLOGGER_BLOG_URL','') }}"><label>네이버 아이디</label><input name="naver_id" value="{{ os.getenv('NAVER_ID','') }}"><label>네이버 비밀번호</label><input name="naver_pw" value="{{ os.getenv('NAVER_PW','') }}"><label>네이버 블로그 ID</label><input name="naver_blog_id" value="{{ os.getenv('NAVER_BLOG_ID','') }}"><label>앱 접속 주소</label><input name="app_base_url" value="{{ os.getenv('APP_BASE_URL','https://blog.superip.net') }}"><label>허용 구글 이메일</label><input name="allowed_email" value="{{ os.getenv('ALLOWED_GOOGLE_EMAIL','') }}"><label>앱 비밀번호</label><input name="app_password" value="{{ os.getenv('APP_PASSWORD','') }}"><button class="primary">설정 저장</button></div></div></form><div class="grid2"><div class="panel"><h3>Google Blogger OAuth</h3><form method="post" enctype="multipart/form-data"><input type="hidden" name="action" value="upload_client_secret"><label>client_secret.json 업로드</label><input type="file" name="client_secret" accept=".json"><button>업로드</button></form><form method="post"><input type="hidden" name="action" value="oauth_reset"><button>토큰 재발급</button></form><form method="post"><input type="hidden" name="action" value="oauth_start"><label>리디렉션 URI</label><input name="redirect_uri" value="http://localhost"><button class="primary">인증 URL 생성</button></form>{% if ws.oauth_url %}<p class="notice">아래 URL을 열어 승인한 뒤, 리다이렉트 URL 또는 code 값을 붙여넣으세요.</p><pre>{{ ws.oauth_url }}</pre><form method="post"><input type="hidden" name="action" value="oauth_complete"><label>리다이렉트 URL 또는 code</label><input name="oauth_code"><button class="primary">인증 완료</button></form>{% endif %}<form method="post"><input type="hidden" name="action" value="blog_test"><input type="hidden" name="blogger_blog_id" value="{{ os.getenv('BLOGGER_BLOG_ID','') }}"><button>블로그 연결 테스트</button></form></div><div class="panel"><h3>앱 로그인 / 네이버 로그인</h3><form method="post" enctype="multipart/form-data"><input type="hidden" name="action" value="upload_login_secret"><label>login_client_secret.json 업로드</label><input type="file" name="login_client_secret" accept=".json"><button>업로드</button></form><hr><form method="post"><button class="primary" name="action" value="naver_login_start">네이버 로그인 시작</button></form>{% if ws.naver_login_state %}{% set ns = ws.naver_login_state %}{% if ns.status == 'success' %}<p class="notice success">네이버 로그인 성공. 세션이 저장되었습니다.</p>{% elif ns.status == 'challenge' %}<p class="notice warn">추가 인증이 필요합니다.</p><img src="data:image/png;base64,{{ ns.screenshot_b64 }}" style="max-width:100%;border:1px solid #ddd"><form method="post"><input type="hidden" name="action" value="naver_login_submit"><input type="hidden" name="session_id" value="{{ ns.session_id }}"><label>정답 입력</label><input name="answer"><button class="primary">제출</button></form><form method="post"><button name="action" value="naver_login_cancel">취소</button></form>{% elif ns.status == 'error' %}<p class="notice error">{{ ns.message }}</p>{% if ns.screenshot_b64 %}<img src="data:image/png;base64,{{ ns.screenshot_b64 }}" style="max-width:100%;border:1px solid #ddd">{% endif %}{% endif %}{% endif %}</div></div>
"""

LOGS_TEMPLATE = """
<div class="header">🪵 오류 로그</div>{% if not shots %}<div class="notice">저장된 오류 스크린샷이 없습니다.</div>{% else %}<div class="panel"><p class="muted">총 {{ shots|length }}개</p>{% for shot in shots %}<details {% if loop.first %}open{% endif %}><summary>{{ shot.name }}</summary><img src="{{ url_for('log_image', name=shot.name) }}" style="max-width:100%;border:1px solid #ddd"><form method="post"><input type="hidden" name="file" value="{{ shot.name }}"><button class="danger">삭제</button></form></details>{% endfor %}</div>{% endif %}
"""

MANUAL_TEMPLATE = """
<div class="header">📚 매뉴얼</div>
<div class="panel"><h3>사용 흐름 (한눈에 보기)</h3><p class="muted">트렌드 수집 → 키워드 선택 → 주제 추천 → 본문 생성 → 이미지 생성 → 발행(Blogger/네이버), 이 순서로 사이드바 메뉴를 위에서부터 따라가면 됩니다.</p><ol><li>트렌드 수집에서 자동 키워드를 가져오거나 수동 키워드를 입력합니다.</li><li>콘텐츠 작성에서 주제를 추천받고 본문을 생성한 뒤, 필요하면 "AI 수정 요청"으로 다듬습니다.</li><li>미디어에서 이미지 3개를 생성해 본문에 삽입합니다 (건너뛰기도 가능).</li><li>발행에서 로컬 저장, Blogger 임시저장/발행, 네이버 발행을 실행합니다.</li></ol></div>
<div class="panel"><h3>메뉴별 사용법</h3>
<div class="card" style="margin-bottom:10px"><h4>📊 트렌드 수집</h4><p class="muted">"트렌드 수집 시작"으로 Google News IT/테크 실시간 키워드를 가져오거나, "수동 키워드 입력"에 직접 원하는 주제를 적고 추가합니다. 체크박스로 고른 뒤 "선택한 키워드로 콘텐츠 작성"을 누릅니다.</p></div>
<div class="card" style="margin-bottom:10px"><h4>✍️ 콘텐츠 작성</h4><p class="muted">"주제 추천 받기"로 제목 후보를 받거나 "직접 제목 입력"으로 바로 씁니다. 톤앤매너를 고르고 "본문 생성"(또는 이미지까지 한 번에 만드는 "⚡ 본문+이미지 동시 작성")을 누릅니다. 본문은 직접 수정하거나, "AI 수정 요청"에 지시사항(예: 더 친근하게)을 입력하고 "AI 수정 적용"을 누르면 AI가 다시 다듬어줍니다 — 지시사항은 반드시 입력해야 합니다.</p></div>
<div class="card" style="margin-bottom:10px"><h4>🎨 미디어</h4><p class="muted">이미지 생성 방식을 고르고 프롬프트(설명)를 확인/수정한 뒤 "이미지 생성 & 삽입"을 누릅니다. 입력창 옆과 결과 카드의 📋 버튼으로 프롬프트를 복사해 Google Flow 등 다른 도구에도 붙여넣을 수 있습니다. 이미지가 필요 없으면 "이미지 건너뛰기"를 누릅니다.</p></div>
<div class="card" style="margin-bottom:10px"><h4>🚀 발행</h4><p class="muted">미리보기를 확인한 뒤 로컬 저장 / Blogger 임시저장·발행 / 네이버 발행 중 선택합니다. 자동 발행이 막히면 "네이버 수동 발행용 (블록별 복사)" 패널에서 블록·이미지를 하나씩 복사해 네이버 스마트에디터에 직접 붙여넣을 수 있습니다.</p></div>
<div class="card" style="margin-bottom:10px"><h4>📂 저장된 글</h4><p class="muted">로컬(data/)에 저장된 글 목록입니다. 제목/본문/태그를 다시 고쳐 저장하거나, 현재 작업으로 불러오거나, 바로 Blogger에 발행하거나, 삭제할 수 있습니다.</p></div>
<div class="card" style="margin-bottom:10px"><h4>⚙️ 설정</h4><p class="muted">LLM·이미지·Blogger·네이버·로그인 관련 값을 모두 여기서 설정합니다. 저장하면 서버의 .env가 갱신됩니다. Blogger 인증, 앱 로그인용 구글 인증, 네이버 로그인도 이 화면에서 진행합니다.</p></div>
<div class="card" style="margin-bottom:10px"><h4>🪵 오류 로그</h4><p class="muted">네이버 발행 실패 시 자동 저장된 스크린샷 목록입니다. 어디서 막혔는지 확인하고, 필요 없는 항목은 삭제할 수 있습니다.</p></div>
</div>
<div class="grid2">
<div class="panel"><h3>Blogger OAuth 팁</h3><p>설정 탭에서 <code>client_secret.json</code> 업로드 → "인증 URL 생성" → 뜨는 URL을 열어 승인 → 이동한 주소창의 전체 URL(또는 <code>code=</code> 뒷부분)을 복사해 앱에 붙여넣고 "인증 완료"를 누르면 <code>token.json</code>이 저장됩니다.</p><p><code>redirect_uri_mismatch</code>가 나오면 Desktop app 타입 OAuth 클라이언트를 새로 만드세요. 인증이 풀렸을 때(<code>invalid_grant</code>, <code>403</code> 등)도 "토큰 재발급" 후 같은 순서를 다시 밟으면 됩니다.</p></div>
<div class="panel"><h3>네이버 발행 팁</h3><p>세션이 만료되면 발행 시 오류가 뜹니다. 설정 탭에서 "네이버 로그인 시작"으로 다시 로그인하면 세션이 갱신됩니다. 캡차가 뜨면 화면에 그대로 표시되니 정답을 입력하고 제출하면 됩니다. 실패 스크린샷은 "🪵 오류 로그" 메뉴에서 확인할 수 있습니다.</p></div>
</div>
<div class="panel"><h3>기술 스택</h3><p>Flask, vLLM/OpenAI 호환 API, Claude fallback, Pollinations/HuggingFace/DALL-E, Google Blogger API v3, Playwright 기반 네이버 발행을 사용합니다. 배포는 GitHub Actions(self-hosted runner)로 main 브랜치 push 시 자동 실행되며, systemd(blog-flask.service)로 서비스가 관리됩니다. 자세한 아키텍처와 서버 설치 방법은 프로젝트 README.md를 참고하세요.</p></div>
"""

# Jinja templates need os in settings.
app.jinja_env.globals["os"] = os
app.jinja_env.globals["page_loading"] = PAGE_LOADING_HTML

if __name__ == "__main__":
    # threaded=True: 네이버 발행을 백그라운드 스레드로 돌리고 그 사이 진행 상황
    # 페이지를 폴링(2초 새로고침)하려면 동시에 여러 요청을 처리할 수 있어야 함
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8501")), threaded=True)
