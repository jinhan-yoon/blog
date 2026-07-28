"""Flask entry point for the AI blog dashboard.

This is the migration path away from Streamlit for authentication-sensitive
flows. It implements stable Google OAuth/password login with server-managed
cookies. The Streamlit app remains available while feature pages are moved over
incrementally.
"""
from __future__ import annotations

import os
from functools import wraps
from urllib.parse import unquote

from dotenv import load_dotenv
from flask import Flask, make_response, redirect, render_template_string, request, url_for

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

app = Flask(__name__)
app.secret_key = os.getenv("APP_SESSION_SECRET") or os.getenv("FLASK_SECRET_KEY") or "change-me-in-env"


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
    resp.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
        path="/",
    )
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


BASE_CSS = """
<style>
:root { color-scheme: light; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f7fb; color: #172033; }
.shell { min-height: 100vh; display: grid; grid-template-columns: 240px 1fr; }
aside { background: #111827; color: white; padding: 22px 18px; }
aside h1 { font-size: 18px; margin: 0 0 20px; }
aside a { display: block; color: #d1d5db; text-decoration: none; padding: 10px 12px; border-radius: 6px; margin: 4px 0; }
aside a:hover { background: #1f2937; color: white; }
main { padding: 28px; }
.panel { background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 22px; max-width: 960px; }
.login { min-height: 100vh; display: grid; place-items: center; padding: 24px; }
.login .panel { max-width: 420px; width: 100%; }
.btn { display: inline-block; border: 0; border-radius: 6px; background: #2563eb; color: white; padding: 10px 16px; font-weight: 700; text-decoration: none; cursor: pointer; }
.btn.secondary { background: #374151; }
input { width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 6px; margin: 8px 0 12px; }
.notice { background: #eff6ff; border-left: 4px solid #2563eb; padding: 12px 14px; border-radius: 0 6px 6px 0; }
.error { background: #fef2f2; border-left-color: #dc2626; }
@media (max-width: 760px) { .shell { grid-template-columns: 1fr; } aside { position: static; } }
</style>
"""


@app.route("/", methods=["GET"])
def index():
    code = request.args.get("code")
    state = request.args.get("state", "")
    if code:
        try:
            email = complete_login(code, APP_BASE_URL, state)
        except Exception as exc:
            return render_template_string(
                LOGIN_TEMPLATE,
                css=BASE_CSS,
                error=f"구글 로그인 실패: {exc}",
                google_enabled=google_auth_configured(),
                password_enabled=is_password_configured(),
            ), 401
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

    return render_template_string(
        LOGIN_TEMPLATE,
        css=BASE_CSS,
        error=error,
        google_enabled=google_auth_configured(),
        password_enabled=is_password_configured(),
    )


@app.route("/google-login")
def google_login():
    if not google_auth_configured():
        return redirect(url_for("login"))
    return redirect(get_login_url(APP_BASE_URL))


@app.route("/logout", methods=["POST"])
def logout():
    resp = make_response(redirect(url_for("login")))
    return _clear_auth_cookie(resp)


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template_string(DASHBOARD_TEMPLATE, css=BASE_CSS, user=_current_user())


@app.route("/healthz")
def healthz():
    return {"ok": True, "app": "flask-blog-dashboard"}


LOGIN_TEMPLATE = """
<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>로그인</title>{{ css|safe }}</head>
<body class="login">
  <section class="panel">
    <h2>로그인이 필요합니다</h2>
    {% if error %}<p class="notice error">{{ error }}</p>{% endif %}
    {% if google_enabled %}<p><a class="btn" href="{{ url_for('google_login') }}">구글 계정으로 로그인</a></p>{% endif %}
    {% if password_enabled %}
    <form method="post">
      <label>비밀번호</label>
      <input type="password" name="password" autocomplete="current-password" required>
      <button class="btn secondary" type="submit">비밀번호로 로그인</button>
    </form>
    {% endif %}
    {% if not google_enabled and not password_enabled %}<p class="notice error">로그인 설정이 없습니다. .env와 login_client_secret.json을 확인하세요.</p>{% endif %}
  </section>
</body>
</html>
"""


DASHBOARD_TEMPLATE = """
<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>AI 블로그 자동화</title>{{ css|safe }}</head>
<body>
  <div class="shell">
    <aside>
      <h1>AI 블로그 자동화</h1>
      <a href="{{ url_for('dashboard') }}">대시보드</a>
      <a href="#">트렌드 수집</a>
      <a href="#">콘텐츠 작성</a>
      <a href="#">미디어</a>
      <a href="#">발행</a>
      <form method="post" action="{{ url_for('logout') }}" style="margin-top:22px"><button class="btn secondary" type="submit">로그아웃</button></form>
    </aside>
    <main>
      <section class="panel">
        <h2>Flask 전환 준비 완료</h2>
        <p class="notice">{{ user }} 계정으로 로그인되었습니다. OAuth와 세션은 Flask에서 처리됩니다.</p>
        <p>기존 Streamlit 화면의 기능을 이 Flask 화면으로 단계적으로 옮길 수 있습니다.</p>
      </section>
    </main>
  </div>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8501")))
