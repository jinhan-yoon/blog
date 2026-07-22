"""AI 블로그 자동화 대시보드 - 사이드바 네비게이션 버전"""

import os
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

st.set_page_config(
    page_title="AI 블로그 자동화 대시보드",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 페이지 정의 ──────────────────────────────────────────────────────────────
PAGES = [
    {"key": "trends",   "icon": "📊", "title": "트렌드 수집",   "step": 1},
    {"key": "content",  "icon": "✍️", "title": "콘텐츠 작성",   "step": 2},
    {"key": "media",    "icon": "🎨", "title": "미디어",         "step": 3},
    {"key": "publish",  "icon": "🚀", "title": "발행",           "step": 4},
    {"key": "settings", "icon": "⚙️", "title": "설정",           "step": None},
    {"key": "manual",   "icon": "📚", "title": "매뉴얼",         "step": None},
]
PROCESS_KEYS = ["trends", "content", "media", "publish"]
PAGE_KEYS    = [p["key"] for p in PAGES]

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── 사이드바 ── */
[data-testid="stSidebar"] { min-width: 230px; max-width: 260px; }

/* ── 전체화면 로딩 모달 (st.spinner() 자동 적용) ── */
[data-testid="stSpinner"] {
    position: fixed !important;
    inset: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    background: rgba(15, 12, 41, 0.88) !important;
    backdrop-filter: blur(3px) !important;
    -webkit-backdrop-filter: blur(3px) !important;
    z-index: 999999 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    margin: 0 !important;
    padding: 0 !important;
    flex-direction: column !important;
}
[data-testid="stSpinner"] > div {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    gap: 24px !important;
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(167,139,250,0.3) !important;
    border-radius: 24px !important;
    padding: 48px 72px !important;
    box-shadow: 0 30px 60px rgba(0,0,0,0.6) !important;
}
[data-testid="stSpinner"] svg {
    width: 64px !important;
    height: 64px !important;
    stroke: #a78bfa !important;
    filter: drop-shadow(0 0 12px #a78bfa) !important;
}
[data-testid="stSpinner"] p,
[data-testid="stSpinner"] span,
[data-testid="stSpinner"] div > div {
    color: #e2e8f0 !important;
    font-size: 1.15em !important;
    font-weight: 500 !important;
    text-align: center !important;
    margin: 0 !important;
    letter-spacing: 0.02em !important;
}

/* ── 메인 영역 ── */
.step-header {
    background: linear-gradient(90deg, #4f46e5 0%, #7c3aed 100%);
    color: white; padding: 12px 20px; border-radius: 10px;
    margin-bottom: 20px; font-weight: bold; font-size: 1.2em;
}
.info-box    { background:#f0f9ff; border-left:4px solid #0ea5e9; padding:12px 16px; border-radius:0 8px 8px 0; margin:8px 0; }
.success-box { background:#f0fdf4; border-left:4px solid #22c55e; padding:12px 16px; border-radius:0 8px 8px 0; margin:8px 0; }
.warn-box    { background:#fffbeb; border-left:4px solid #f59e0b; padding:12px 16px; border-radius:0 8px 8px 0; margin:8px 0; }
.keyword-chip { display:inline-block; background:#ede9fe; color:#5b21b6; padding:4px 12px; border-radius:20px; margin:3px; font-size:0.85em; font-weight:500; }
.post-preview { border:1px solid #e2e8f0; border-radius:12px; padding:24px; background:#fafafa; color:#1f2937; box-shadow:0 1px 4px rgba(0,0,0,0.08); }
.tech-card  { border:1px solid #e2e8f0; border-radius:10px; padding:16px; margin:10px 0; background:#f8fafc; }
.tech-badge { display:inline-block; background:#dbeafe; color:#1d4ed8; padding:3px 10px; border-radius:12px; font-size:0.8em; font-weight:600; margin:2px; }
</style>
""", unsafe_allow_html=True)

# ── 세션 초기화 ──────────────────────────────────────────────────────────────
def init_session():
    defaults = {
        "current_page":       "trends",
        "trends":             None,
        "selected_keywords":  [],
        "post_topic":         None,
        "post_title":         "",
        "post_content_html":  "",
        "post_meta_desc":     "",
        "post_tags":          [],
        "image_prompts":      [],
        "topics":             None,
        "image_urls":         [],
        "image_data":         [],
        "final_html":         "",
        "publish_result":     None,
        "publish_history":    [],
        "oauth_url":          None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# ── 사이드바 네비게이션 ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("🤖 AI 블로그 자동화")
    st.caption("Google Trends → vLLM → Blogger")
    st.divider()

    # 완료 상태 계산
    step_done = {
        "trends":  bool(st.session_state.selected_keywords),
        "content": bool(st.session_state.post_content_html),
        "media":   bool(st.session_state.final_html),
        "publish": bool(
            st.session_state.publish_result
            and not st.session_state.publish_result.get("error")
        ),
    }
    cur = st.session_state.current_page

    st.markdown("**📋 프로세스**")
    for page in PAGES[:4]:
        key   = page["key"]
        done  = step_done.get(key, False)
        is_cur = key == cur
        step_num = page["step"]

        if is_cur:
            prefix = "▶"
        elif done:
            prefix = "✅"
        else:
            prefix = str(step_num)

        label = f"{prefix}  {page['icon']} {page['title']}"
        if st.button(label, key=f"nav_{key}", use_container_width=True,
                     type="primary" if is_cur else "secondary"):
            st.session_state.current_page = key
            st.rerun()

    st.divider()
    st.markdown("**🔧 기타**")
    for page in PAGES[4:]:
        key   = page["key"]
        is_cur = key == cur
        label = f"{'▶  ' if is_cur else ''}{page['icon']} {page['title']}"
        if st.button(label, key=f"nav_{key}", use_container_width=True,
                     type="primary" if is_cur else "secondary"):
            st.session_state.current_page = key
            st.rerun()

    st.divider()

    # LLM / API 상태
    from modules.content_generator import check_llm_status
    llm_status = check_llm_status()
    blogger_ok = bool(os.getenv("BLOGGER_BLOG_ID", ""))
    img_prov   = os.getenv("IMAGE_PROVIDER", "pollinations")

    st.caption("**API 상태**")
    vllm_icon = "✅" if llm_status["vllm_available"] else "❌"
    claude_icon = "✅" if llm_status["claude_available"] else "⚪"
    st.markdown(
        f"{vllm_icon} vLLM &nbsp;|&nbsp; {claude_icon} Claude  \n"
        f"{'✅' if blogger_ok else '❌'} Blogger &nbsp;|&nbsp; 🖼️ {img_prov}",
        unsafe_allow_html=True,
    )
    if llm_status["last_provider"]:
        st.caption(f"사용중: {llm_status['last_provider']} · {llm_status['last_model']}")
    if not llm_status["any_available"]:
        st.warning("⚙️ LLM 설정 필요")

# ════════════════════════════════════════════════════════
# STEP 1: 트렌드 수집
# ════════════════════════════════════════════════════════
if cur == "trends":
    st.markdown('<div class="step-header">📊 STEP 1 · 트렌드 수집</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<div class="info-box">Google 트렌드, 네이버에서 실시간 급상승 검색어를 자동으로 수집합니다.</div>',
                    unsafe_allow_html=True)
    with col2:
        collect_btn = st.button("🔍 트렌드 수집 시작", type="primary", use_container_width=True)

    if collect_btn:
        with st.spinner("트렌드 키워드 수집 중..."):
            from modules.trend_collector import collect_all_trends
            st.session_state.trends = collect_all_trends()
        st.rerun()

    if st.session_state.trends:
        trends = st.session_state.trends
        col_n, col_g = st.columns(2)

        with col_n:
            st.markdown("#### 🟢 네이버 실시간 검색어")
            naver_kws = trends.get("naver", [])
            if naver_kws:
                for kw in naver_kws[:20]:
                    caret_icon = {"NEW": "🆕", "Up": "🔺", "Down": "🔻"}.get(kw.get("caret", ""), "➖")
                    st.markdown(f"`{str(kw['rank']).zfill(2)}` {caret_icon} **{kw['keyword']}**")
            else:
                st.info("네이버 데이터 없음")

        with col_g:
            st.markdown("#### 🔴 구글 실시간 검색어")
            google_kws = trends.get("google", [])
            if google_kws:
                for kw in google_kws[:20]:
                    traffic = kw.get("traffic", "")
                    ts = f"  `{traffic}`" if traffic and traffic != "N/A" else ""
                    st.markdown(f"`{str(kw['rank']).zfill(2)}` **{kw['keyword']}**{ts}")
            else:
                st.info("구글 데이터 없음")

        st.divider()
        st.markdown("**📌 콘텐츠 작성에 사용할 키워드를 선택하세요:**")
        merged = trends["merged"]

        selected = []
        cols = st.columns(3)
        for i, kw in enumerate(merged):
            with cols[i % 3]:
                caret = f" {kw.get('caret', '')}" if kw.get("caret") else ""
                label = f"**{kw['keyword']}**  \n`{kw['source']}`{caret} · {kw['traffic']}"
                if st.checkbox(label, key=f"kw_{i}",
                               value=kw["keyword"] in st.session_state.selected_keywords):
                    selected.append(kw["keyword"])

        st.session_state.selected_keywords = selected

        if selected:
            st.divider()
            st.markdown(f"**선택된 키워드 ({len(selected)}개):**")
            chips = " ".join([f'<span class="keyword-chip">{k}</span>' for k in selected])
            st.markdown(chips, unsafe_allow_html=True)

            st.divider()
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("✍️ 콘텐츠 작성 →", type="primary", use_container_width=True):
                    st.session_state.current_page = "content"
                    st.rerun()

# ════════════════════════════════════════════════════════
# STEP 2: 콘텐츠 작성
# ════════════════════════════════════════════════════════
elif cur == "content":
    st.markdown('<div class="step-header">✍️ STEP 2 · 콘텐츠 작성</div>', unsafe_allow_html=True)

    if not st.session_state.selected_keywords:
        st.markdown('<div class="warn-box">⚠️ 먼저 트렌드 수집에서 키워드를 선택해주세요.</div>',
                    unsafe_allow_html=True)
    else:
        # ── 2-1: 주제 선정 ──────────────────────────────────────────────────
        st.markdown("### 🎯 2-1 · 주제 선정")
        selected_kws = st.session_state.selected_keywords
        st.markdown(f"**선택된 키워드:** {', '.join(selected_kws)}")

        col1, col2 = st.columns([2, 1])
        with col1:
            topic_count = st.slider("추천 주제 수", 3, 8, 5)
        with col2:
            suggest_btn = st.button("🤖 주제 추천 받기", type="primary", use_container_width=True)

        if suggest_btn:
            with st.spinner("vLLM이 주제를 분석 중..."):
                try:
                    from modules.content_generator import suggest_topics
                    topics = suggest_topics(selected_kws, topic_count)
                    st.session_state.topics = topics
                    st.success(f"✅ {len(topics)}개 주제가 추천되었습니다!")
                except Exception as e:
                    st.error(f"오류: {e}")
                    st.session_state.topics = None
            st.rerun()

        if st.session_state.topics:
            st.divider()
            st.markdown("**추천 주제 목록:**")
            for i, topic in enumerate(st.session_state.topics):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"**{i+1}. {topic['title']}**")
                    st.caption(f"📌 주제: {topic['topic']}")
                    st.caption(f"💡 이유: {topic['reason']}")
                    chips = " ".join([f'<span class="keyword-chip">{k}</span>'
                                      for k in topic.get("keywords", [])])
                    st.markdown(chips, unsafe_allow_html=True)
                with col2:
                    if st.button("📝 선택", key=f"topic_{i}", use_container_width=True):
                        st.session_state.post_topic = topic
                        st.session_state.post_title = topic["title"]
                        st.session_state.topics = None
                        st.rerun()
                st.divider()

            with st.expander("직접 제목 입력"):
                custom_title = st.text_input("사용자 정의 제목", value=st.session_state.post_title)
                if st.button("✅ 이 제목 사용") and custom_title:
                    st.session_state.post_title = custom_title
                    st.session_state.topics = None
                    st.rerun()

        # ── 2-2: 본문 생성 ──────────────────────────────────────────────────
        if st.session_state.post_title:
            st.divider()
            st.markdown("### ✍️ 2-2 · 본문 생성")
            st.markdown(f"**선택된 제목:** {st.session_state.post_title}")

            col1, col2, col3 = st.columns(3)
            with col1:
                tone = st.selectbox("톤앤매너", ["정보전달", "친근한", "전문적", "뉴스형"])
            with col2:
                kw_default = st.session_state.post_topic.get("keywords", []) if st.session_state.post_topic else selected_kws
                extra_kw = st.text_input("추가 키워드 (쉼표 구분)", value=", ".join(kw_default))
            with col3:
                st.markdown("<br>", unsafe_allow_html=True)
                gen_btn = st.button("🤖 본문 생성", type="primary", use_container_width=True)

            if gen_btn:
                kws = [k.strip() for k in extra_kw.split(",") if k.strip()]
                with st.spinner("vLLM이 본문을 작성 중... (약 20-40초 소요)"):
                    try:
                        from modules.content_generator import generate_blog_post
                        result = generate_blog_post(st.session_state.post_title, kws, tone)
                        st.session_state.post_title        = result.get("title", st.session_state.post_title)
                        st.session_state.post_content_html = result.get("content_html", "")
                        st.session_state.post_meta_desc    = result.get("meta_description", "")
                        st.session_state.post_tags         = result.get("tags", [])
                        st.session_state.image_prompts     = result.get("image_prompts", [])
                        st.success("✅ 본문이 생성되었습니다!")
                    except Exception as e:
                        st.error(f"오류: {e}")
                st.rerun()

            if st.session_state.post_content_html:
                st.divider()
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**📝 본문 편집**")
                    edited_html = st.text_area(
                        "HTML 본문 (직접 수정 가능)",
                        value=st.session_state.post_content_html,
                        height=400,
                    )
                    st.session_state.post_content_html = edited_html

                    refine = st.text_input("✏️ AI에게 수정 요청 (예: '더 친근하게', '길이를 늘려줘')")
                    if st.button("🤖 AI 수정 적용") and refine:
                        with st.spinner("수정 중..."):
                            try:
                                from modules.content_generator import refine_content
                                st.session_state.post_content_html = refine_content(edited_html, refine)
                                st.rerun()
                            except Exception as e:
                                st.error(f"오류: {e}")

                with col2:
                    st.markdown("**👁️ 미리보기**")
                    st.markdown(
                        f'<div class="post-preview">'
                        f'<h2>{st.session_state.post_title}</h2>'
                        f'{st.session_state.post_content_html}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                st.divider()
                col1, col2 = st.columns(2)
                with col1:
                    tags_input = st.text_input("태그 (쉼표 구분)",
                                               value=", ".join(st.session_state.post_tags))
                    st.session_state.post_tags = [t.strip() for t in tags_input.split(",") if t.strip()]
                with col2:
                    meta_desc = st.text_area("메타 설명 (SEO)",
                                             value=st.session_state.post_meta_desc, height=80)
                    st.session_state.post_meta_desc = meta_desc

                st.divider()
                _, col2 = st.columns([3, 1])
                with col2:
                    if st.button("🎨 미디어 →", type="primary", use_container_width=True):
                        st.session_state.current_page = "media"
                        st.rerun()

# ════════════════════════════════════════════════════════
# STEP 3: 미디어
# ════════════════════════════════════════════════════════
elif cur == "media":
    st.markdown('<div class="step-header">🎨 STEP 3 · 미디어 · 이미지 생성</div>', unsafe_allow_html=True)

    if not st.session_state.post_content_html:
        st.markdown('<div class="warn-box">⚠️ 먼저 콘텐츠 작성 단계를 완료해주세요.</div>',
                    unsafe_allow_html=True)
    else:
        # ── 프로바이더 선택 ──────────────────────────────────────────────────
        _env_provider = os.getenv("IMAGE_PROVIDER", "pollinations")
        _provider_info = {
            "pollinations": "🆓 Pollinations.ai — API 키 불필요, AI 이미지 생성 (느릴 수 있음)",
            "picsum":       "⚡ Lorem Picsum — API 키 불필요, 고품질 사진 즉시 로드 (랜덤 사진)",
            "huggingface":  "🤗 HuggingFace SD XL — HF 무료 토큰 필요, AI 이미지 생성",
            "claude":       "🤖 Claude + Pollinations — Anthropic 키 필요, 프롬프트 강화 후 생성",
            "dalle":        "💰 DALL-E 3 — OpenAI 유료 키 필요, 최고 품질",
        }
        provider = st.selectbox(
            "이미지 생성 방식 선택",
            list(_provider_info.keys()),
            index=list(_provider_info.keys()).index(_env_provider) if _env_provider in _provider_info else 0,
            format_func=lambda x: _provider_info[x],
        )

        if provider == "huggingface" and not os.getenv("HUGGINGFACE_TOKEN"):
            st.markdown('<div class="warn-box">⚠️ 설정에서 HUGGINGFACE_TOKEN을 입력해주세요. (huggingface.co에서 무료 발급)</div>', unsafe_allow_html=True)
        if provider in ("claude",) and not os.getenv("ANTHROPIC_API_KEY"):
            st.markdown('<div class="warn-box">⚠️ 설정에서 Anthropic API Key를 입력해주세요.</div>', unsafe_allow_html=True)
        if provider == "dalle" and not os.getenv("OPENAI_API_KEY"):
            st.markdown('<div class="warn-box">⚠️ 설정에서 OpenAI API Key를 입력해주세요.</div>', unsafe_allow_html=True)

        st.divider()

        # ── 프롬프트 편집 ────────────────────────────────────────────────────
        if not st.session_state.image_prompts:
            st.session_state.image_prompts = ["blog post illustration", "relevant image", "article image"]

        st.markdown("**이미지 프롬프트 (수정 가능, 영어 권장):**")
        edited_prompts = []
        for i in range(3):
            cur_prompt = st.session_state.image_prompts[i] if i < len(st.session_state.image_prompts) else ""
            edited_prompts.append(st.text_input(f"이미지 {i+1} 설명", value=cur_prompt, key=f"ip_{i}"))
        st.session_state.image_prompts = edited_prompts

        st.divider()
        col1, col2, col3 = st.columns([2, 1, 1])
        with col2:
            gen_img_btn = st.button("🖼️ 이미지 생성 & 삽입", type="primary", use_container_width=True)
        with col3:
            skip_btn = st.button("⏭️ 이미지 건너뛰기", use_container_width=True)

        if gen_img_btn:
            from modules.image_generator import generate_images_for_post, insert_images_into_html

            log_area = st.empty()
            log_lines = []
            def _log(msg):
                log_lines.append(msg)
                log_area.markdown("\n\n".join(log_lines))

            prompts = st.session_state.image_prompts[:3]
            with st.spinner(f"이미지 3개 생성 중... ({provider})"):
                try:
                    results = generate_images_for_post(prompts, provider, log_callback=_log)
                    st.session_state.image_data = results
                    st.session_state.final_html = insert_images_into_html(
                        st.session_state.post_content_html, results
                    )
                    success_count = sum(1 for r in results if r.get("bytes"))
                    if success_count > 0:
                        st.success(f"✅ 이미지 {success_count}/3개 생성 완료!")
                    else:
                        st.error("❌ 이미지 생성 실패. 아래 오류를 확인하거나 다른 방식을 선택하세요.")
                        for r in results:
                            if r.get("error"):
                                st.code(r["error"])
                except Exception as e:
                    st.error(f"❌ 오류: {e}")
            st.rerun()

        if skip_btn:
            st.session_state.final_html = st.session_state.post_content_html
            st.session_state.image_data = []
            st.session_state.current_page = "publish"
            st.rerun()

        # ── 결과 미리보기 ────────────────────────────────────────────────────
        if st.session_state.get("image_data"):
            st.divider()
            st.markdown("**생성된 이미지 미리보기:**")
            cols = st.columns(3)
            for i, item in enumerate(st.session_state.image_data):
                with cols[i]:
                    if item.get("bytes"):
                        st.image(item["bytes"], caption=f"이미지 {i+1} ({item.get('provider','')})",
                                 use_container_width=True)
                    else:
                        st.error(f"이미지 {i+1} 실패")
                        if item.get("error"):
                            st.caption(item["error"][:100])

            success_count = sum(1 for r in st.session_state.image_data if r.get("bytes"))
            if success_count > 0:
                st.divider()
                _, col2 = st.columns([3, 1])
                with col2:
                    if st.button("🚀 발행 →", type="primary", use_container_width=True):
                        st.session_state.current_page = "publish"
                        st.rerun()

# ════════════════════════════════════════════════════════
# STEP 4: 발행
# ════════════════════════════════════════════════════════
elif cur == "publish":
    st.markdown('<div class="step-header">🚀 STEP 4 · 발행</div>', unsafe_allow_html=True)

    final_html = st.session_state.final_html or st.session_state.post_content_html
    title = st.session_state.post_title

    if not final_html:
        st.markdown('<div class="warn-box">⚠️ 콘텐츠를 먼저 작성해주세요.</div>',
                    unsafe_allow_html=True)
    else:
        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown("**📄 최종 포스팅 미리보기**")
            st.markdown(
                f'<div class="post-preview">'
                f'<h1 style="font-size:1.6em; margin-bottom:8px;">{title}</h1>'
                f'<p style="color:#6b7280; font-size:0.85em;">태그: {", ".join(st.session_state.post_tags)}</p>'
                f'<hr/>'
                f'{final_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown("**🚀 발행 설정**")
            final_title = st.text_input("제목 최종 확인", value=title)

            st.divider()

            from modules.blogger_publisher import check_auth_status
            auth = check_auth_status()

            st.markdown("**인증 상태:**")
            st.write(f"{'✅' if auth['client_secret'] else '❌'} client_secret.json")
            st.write(f"{'✅' if auth.get('token_valid') else '⚠️'} OAuth 토큰")
            st.write(f"{'✅' if auth['blog_id'] else '❌'} Blog ID")

            if not auth["ready"]:
                st.markdown('<div class="warn-box">⚠️ 설정 메뉴에서 Blogger 연동을 완료해주세요.</div>',
                            unsafe_allow_html=True)

            st.divider()

            # 로컬 저장 (Blogger 인증 없이도 가능)
            if st.button("💿 로컬 저장 (data 폴더)", use_container_width=True):
                try:
                    import json as _json
                    from datetime import datetime as _dt
                    data_dir = Path("data")
                    data_dir.mkdir(exist_ok=True)
                    safe_title = "".join(c for c in final_title if c.isalnum() or c in " _-")[:40].strip()
                    fname = data_dir / f"{_dt.now().strftime('%Y%m%d_%H%M%S')}_{safe_title}.json"
                    payload = {
                        "title": final_title,
                        "content_html": final_html,
                        "tags": st.session_state.post_tags,
                        "meta_description": st.session_state.post_meta_desc,
                        "saved_at": _dt.now().isoformat(),
                    }
                    fname.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    st.success(f"✅ 로컬 저장 완료: {fname}")
                except Exception as e:
                    st.error(f"저장 실패: {e}")

            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Blogger 임시저장", use_container_width=True):
                    from modules.blogger_publisher import publish_post
                    try:
                        with st.spinner("저장 중..."):
                            result = publish_post(
                                title=final_title,
                                content_html=final_html,
                                tags=st.session_state.post_tags,
                                is_draft=True,
                            )
                            st.session_state.publish_result = result
                            if not result.get("error"):
                                st.session_state.publish_history.append(result)
                        st.rerun()
                    except Exception as e:
                        st.session_state.publish_result = {"error": str(e)}
                        st.rerun()
            with c2:
                if st.button("🚀 즉시 발행", type="primary", use_container_width=True):
                    from modules.blogger_publisher import publish_post
                    try:
                        with st.spinner("발행 중..."):
                            result = publish_post(
                                title=final_title,
                                content_html=final_html,
                                tags=st.session_state.post_tags,
                                is_draft=False,
                            )
                            st.session_state.publish_result = result
                            if not result.get("error"):
                                st.session_state.publish_history.append(result)
                        st.rerun()
                    except Exception as e:
                        st.session_state.publish_result = {"error": str(e)}
                        st.rerun()

        if st.session_state.publish_result:
            result = st.session_state.publish_result
            if result.get("error"):
                st.error(f"❌ 발행 실패: {result['error']}")
            else:
                st.markdown(f"""
                <div class="success-box">
                ✅ <b>발행 성공!</b><br>
                📎 URL: <a href="{result.get('url', '')}" target="_blank">{result.get('url', '')}</a><br>
                📅 발행일: {result.get('published', '')}
                </div>
                """, unsafe_allow_html=True)

        st.divider()
        st.markdown("### 📋 최근 포스팅")

        if st.button("🔄 포스팅 목록 새로고침"):
            if auth["ready"]:
                try:
                    from modules.blogger_publisher import list_recent_posts
                    posts = list_recent_posts()
                    for p in posts:
                        status_icon = "🟢" if p["status"] == "LIVE" else "📝"
                        c1, c2 = st.columns([4, 1])
                        with c1:
                            st.markdown(f"{status_icon} [{p['title']}]({p.get('url', '#')}) · "
                                        f"{p['published'][:10] if p['published'] else ''}")
                        with c2:
                            if st.button("삭제", key=f"del_{p['id']}", use_container_width=True):
                                st.info("(삭제 기능은 다음 버전에서 추가됩니다)")
                except Exception as e:
                    st.error(f"조회 실패: {e}")
            else:
                st.warning("Blogger 인증이 필요합니다.")

# ════════════════════════════════════════════════════════
# 설정
# ════════════════════════════════════════════════════════
elif cur == "settings":
    st.markdown('<div class="step-header">⚙️ 설정 · API 키 및 환경 구성</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🤖 LLM 서버 (vLLM)")
        llm_addr    = st.text_input("LLM 서버 주소",  value=os.getenv("LLM_ADDR", "http://210.127.59.40:8000"))
        llm_model   = st.text_input("LLM 모델명",     value=os.getenv("LLM_MODEL", "google/gemma-4-31b-it"))
        llm_api_key = st.text_input("LLM API Key",    value=os.getenv("LLM_API_KEY", "EMPTY"), type="password")

        st.markdown("### 🤖 Claude (LLM Fallback / 이미지)")
        claude_model  = st.selectbox(
            "Claude 모델 (vLLM 불가 시 자동 사용)",
            ["claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-8"],
            index=["claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-8"].index(
                os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
            ) if os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6") in
                ["claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-8"] else 0,
        )

        st.markdown("### 🖼️ 이미지 생성")
        _opts     = ["pollinations", "picsum", "huggingface", "claude", "dalle"]
        _cur_prov = os.getenv("IMAGE_PROVIDER", "pollinations")
        _idx      = _opts.index(_cur_prov) if _cur_prov in _opts else 0
        img_provider   = st.selectbox("이미지 생성 방식", _opts, index=_idx)
        anthropic_key  = st.text_input("Anthropic API Key (Claude용)", value=os.getenv("ANTHROPIC_API_KEY", ""), type="password")
        openai_key     = st.text_input("OpenAI API Key (DALL-E 3용)", value=os.getenv("OPENAI_API_KEY", ""), type="password")
        hf_token       = st.text_input("HuggingFace Token (SD XL용, 무료)", value=os.getenv("HUGGINGFACE_TOKEN", ""), type="password",
                                       help="huggingface.co 회원가입 후 Settings > Access Tokens에서 무료 발급")

    with col2:
        st.markdown("### 📝 Google Blogger")
        blog_id = st.text_input("Blogger Blog ID", value=os.getenv("BLOGGER_BLOG_ID", ""))
        if st.button("🔌 블로그 연결 테스트", use_container_width=True):
            from modules.blogger_publisher import test_blog_connection
            with st.spinner("블로그 연결 확인 중..."):
                result = test_blog_connection(blog_id)
            if result["ok"]:
                st.success(f"✅ 연결 성공!\n블로그: {result['blog_name']}\nURL: {result['blog_url']}\n총 포스트: {result['posts']}개")
            else:
                st.error(f"❌ 연결 실패: {result['error']}")

        st.markdown("### 🔑 OAuth 2.0 인증")

        # Step 1: client_secret.json 업로드
        st.markdown("**① client_secret.json 업로드**")
        uploaded = st.file_uploader("client_secret.json 업로드", type="json", label_visibility="collapsed")
        if uploaded:
            with open("client_secret.json", "wb") as f:
                f.write(uploaded.read())
            st.success("✅ client_secret.json 저장됨")

        secret_ok = Path("client_secret.json").exists()
        st.write(f"{'✅' if secret_ok else '❌'} client_secret.json")

        # Step 2: OAuth 인증 URL 생성 및 코드 입력
        st.markdown("**② Google 계정 인증**")
        token_ok = Path("token.json").exists()

        if token_ok:
            st.success("✅ OAuth 토큰 존재 (인증 완료)")
            if st.button("🔄 토큰 재발급 (재인증)"):
                Path("token.json").unlink()
                st.rerun()
        else:
            st.warning("⚠️ OAuth 토큰 없음 — 아래 절차로 인증하세요")

            if secret_ok:
                if st.button("🔗 인증 URL 생성", use_container_width=True):
                    try:
                        from modules.blogger_publisher import get_oauth_url
                        url = get_oauth_url()
                        st.session_state.oauth_url = url
                    except Exception as e:
                        st.error(f"URL 생성 실패: {e}")

                if st.session_state.get("oauth_url"):
                    st.markdown("**1.** 아래 URL을 복사해 브라우저에서 열고 Google 계정으로 승인하세요:")
                    st.code(st.session_state.oauth_url, language=None)
                    st.markdown("**2.** 승인 후 브라우저 주소창의 URL 전체를 복사해 아래에 붙여넣으세요  \n"
                                "*(주소가 `http://localhost/?code=...` 형태)*")
                    code_input = st.text_input("리다이렉트 URL 또는 code= 값 붙여넣기",
                                               key="oauth_code_input", label_visibility="collapsed",
                                               placeholder="http://localhost/?code=4/0A... 또는 코드만")
                    if st.button("✅ 인증 완료", type="primary", use_container_width=True) and code_input:
                        try:
                            from modules.blogger_publisher import complete_oauth
                            complete_oauth(code_input)
                            st.session_state.oauth_url = None
                            st.success("🎉 Google OAuth 인증 성공! token.json 저장됨")
                            st.rerun()
                        except Exception as e:
                            st.error(f"인증 실패: {e}")
            else:
                st.info("① 먼저 client_secret.json을 업로드하세요.")

    st.divider()
    if st.button("💾 설정 저장", type="primary"):
        env_content = f"""# ── LLM 서버 ──────────────────────────────────────────
LLM_ADDR={llm_addr}
LLM_MODEL={llm_model}
LLM_API_KEY={llm_api_key}

# ── 이미지 생성 ──────────────────────────────────────
IMAGE_PROVIDER={img_provider}
ANTHROPIC_API_KEY={anthropic_key}
OPENAI_API_KEY={openai_key}
HUGGINGFACE_TOKEN={hf_token}
CLAUDE_MODEL={claude_model}

# ── Google Blogger ────────────────────────────────────
BLOGGER_BLOG_ID={blog_id}
"""
        with open(".env", "w") as f:
            f.write(env_content)
        load_dotenv(override=True)
        st.success("✅ 설정이 .env 파일에 저장되었습니다.")

    st.divider()
    st.markdown("### 📚 설정 가이드")
    with st.expander("Claude (Anthropic) API 키 발급"):
        st.markdown("""
1. [Anthropic Console](https://console.anthropic.com) 접속
2. **API Keys** > **Create Key** 로 새 키 생성
3. 위 Anthropic API Key 입력란에 붙여넣기 후 저장
4. 이미지 생성 방식을 **claude** 로 선택하면 프롬프트를 강화하여 Pollinations.ai로 이미지 생성
        """)
    with st.expander("Google Blogger API 설정"):
        st.markdown("""
1. [Google Cloud Console](https://console.cloud.google.com) 접속
2. **APIs & Services > Library** > **Blogger API v3** 활성화
3. **Credentials > Create Credentials > OAuth 2.0 Client ID** (Desktop app) 생성
4. JSON 다운로드 후 위에서 업로드
5. 블로그 ID: Blogger 대시보드 URL의 숫자 부분
        """)
    with st.expander("Pollinations.ai (무료 이미지)"):
        st.markdown("""
- API 키 불필요, 완전 무료
- 요청당 이미지 1024×576 픽셀 생성
- 상업적 이용 가능 / 생성 소요 시간: 5-15초
        """)

# ════════════════════════════════════════════════════════
# 매뉴얼
# ════════════════════════════════════════════════════════
elif cur == "manual":
    st.markdown('<div class="step-header">📚 기술 매뉴얼 · 사용된 기술 스택</div>', unsafe_allow_html=True)

    st.markdown("""
이 대시보드는 **AI 기반 블로그 자동화** 파이프라인으로,
트렌드 수집부터 Google Blogger 발행까지 전 과정을 자동화합니다.
    """)

    st.markdown("## 🔄 전체 파이프라인")
    st.code(
        "트렌드 수집 → 키워드 선택 → 주제 추천 (vLLM) → 본문 생성 (vLLM) → 이미지 생성 → Blogger 발행",
        language="text",
    )

    st.divider()
    st.markdown("## 🏗️ 기술 스택")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🖥️ 웹 프레임워크")
        st.markdown("""
<div class="tech-card">
<b>Streamlit</b> <span class="tech-badge">v1.35+</span><br>
Python으로 데이터 앱을 빠르게 만드는 오픈소스 프레임워크.<br>
<code>st.session_state</code>로 단계별 데이터를 유지하며,<br>
사이드바·컬럼·버튼 등 내장 컴포넌트를 활용합니다.
</div>
        """, unsafe_allow_html=True)

        st.markdown("### 🤖 AI / LLM")
        st.markdown("""
<div class="tech-card">
<b>vLLM</b> <span class="tech-badge">자체 호스팅</span> <span class="tech-badge">OpenAI 호환</span><br>
LLM을 고속 서빙하는 오픈소스 추론 엔진.<br>
OpenAI API 형식과 호환되어 <code>openai</code> SDK로 통신합니다.<br><br>
<b>Google Gemma 4 (31B-it)</b> <span class="tech-badge">LLM 모델</span><br>
주제 추천·본문 생성·수정 요청에 사용되는 한국어 지원 LLM 모델.<br><br>
<b>OpenAI SDK</b> <span class="tech-badge">v1.30+</span><br>
vLLM 서버 통신 클라이언트. <code>base_url</code>을 vLLM 주소로 교체하여 사용.
</div>
        """, unsafe_allow_html=True)

        st.markdown("### 🖼️ 이미지 생성")
        st.markdown("""
<div class="tech-card">
<b>Pollinations.ai</b> <span class="tech-badge">무료 · 기본값</span><br>
API 키 없이 URL 파라미터로 이미지를 생성하는 무료 서비스.<br><br>
<b>Anthropic Claude API</b> <span class="tech-badge">선택</span><br>
이미지 프롬프트를 영어로 강화(Prompt Enhancement)한 후<br>
Pollinations.ai로 렌더링하는 하이브리드 방식.<br><br>
<b>OpenAI DALL-E 3</b> <span class="tech-badge">유료 · 선택</span><br>
OpenAI API를 통해 고품질 이미지 생성. API 키 필요.
</div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("### 📊 트렌드 수집")
        st.markdown("""
<div class="tech-card">
<b>Loword API</b> (loword.co.kr) <span class="tech-badge">서드파티</span><br>
네이버 + 구글 실시간 검색어를 날짜 기반으로 제공하는 API.<br>
별도 인증 없이 JSON으로 순위·변동폭(caret)을 수집합니다.<br><br>
<b>Google Trends RSS</b> <span class="tech-badge">공식</span><br>
<code>trends.google.com</code> 공식 RSS 피드.<br>
한국(KR) 실시간 급상승 검색어와 관련 뉴스를 파싱합니다.<br><br>
<b>BeautifulSoup4 + lxml</b> <span class="tech-badge">v4.12+</span><br>
RSS XML 및 HTML 콘텐츠 파싱 라이브러리.
</div>
        """, unsafe_allow_html=True)

        st.markdown("### 📝 발행 (Google Blogger)")
        st.markdown("""
<div class="tech-card">
<b>Google Blogger API v3</b><br>
Blogger 블로그에 포스팅을 생성·조회하는 REST API.<br>
Google Cloud Console에서 활성화 후 사용.<br><br>
<b>google-api-python-client</b> <span class="tech-badge">v2.120+</span><br>
Google API 공식 Python 클라이언트 라이브러리.<br><br>
<b>google-auth-oauthlib</b> <span class="tech-badge">v1.2+</span><br>
OAuth 2.0 인증 흐름 처리.<br>
<code>client_secret.json</code> + <code>token.json</code>으로 토큰을 발급·갱신합니다.
</div>
        """, unsafe_allow_html=True)

        st.markdown("### 🛠️ 유틸리티")
        st.markdown("""
<div class="tech-card">
<b>python-dotenv</b> <span class="tech-badge">v1.0+</span><br>
<code>.env</code> 파일에서 환경 변수를 로드. API 키·서버 주소 등 관리.<br><br>
<b>Pillow</b> <span class="tech-badge">v10+</span><br>
이미지 처리 라이브러리. 생성된 이미지 검증·처리에 활용.<br><br>
<b>requests</b> <span class="tech-badge">v2.31+</span><br>
HTTP 요청 라이브러리. 트렌드 API 호출 및 이미지 URL 요청에 사용.
</div>
        """, unsafe_allow_html=True)

    st.divider()
    st.markdown("## 📁 프로젝트 구조")
    st.code("""
blog/
├── app.py                    # 메인 Streamlit 앱
├── requirements.txt          # Python 패키지 목록
├── .env                      # 환경 변수 (API 키 등, git 제외)
├── .env.example              # 환경 변수 예시
├── run.sh                    # 앱 실행 스크립트
├── blog-streamlit.service    # systemd 서비스 설정 (Linux)
└── modules/
    ├── trend_collector.py    # 트렌드 수집 (Loword + Google RSS)
    ├── content_generator.py  # LLM 콘텐츠 생성 (vLLM)
    ├── image_generator.py    # 이미지 생성 (Pollinations/Claude/DALL-E)
    └── blogger_publisher.py  # Blogger API 발행
    """, language="text")

    st.divider()
    st.markdown("## ⚙️ 환경 변수")
    st.markdown("""
| 변수명 | 설명 | 예시 |
|--------|------|------|
| `LLM_ADDR` | vLLM 서버 주소 | `http://192.168.1.1:8000` |
| `LLM_MODEL` | LLM 모델명 | `google/gemma-4-31b-it` |
| `LLM_API_KEY` | vLLM API 키 (보통 EMPTY) | `EMPTY` |
| `IMAGE_PROVIDER` | 이미지 생성 방식 | `pollinations` / `claude` / `dalle` |
| `ANTHROPIC_API_KEY` | Claude API 키 | `sk-ant-...` |
| `OPENAI_API_KEY` | OpenAI API 키 | `sk-...` |
| `BLOGGER_BLOG_ID` | Blogger 블로그 ID | `1234567890` |
    """)

    st.divider()
    st.markdown("## 🚀 실행 방법")
    st.code("""
# 1. 패키지 설치
pip install -r requirements.txt

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 API 키 입력

# 3. 앱 실행
streamlit run app.py --server.port 8501

# 또는 run.sh 사용
bash run.sh
    """, language="bash")
