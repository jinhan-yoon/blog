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
        "naver_publish_result": None,
        "publish_history":      [],
        "oauth_url":            None,
        "oauth_redirect_uri":   None,
        "oauth_code_verifier":  None,
        "manual_keywords":      [],
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
    from modules.naver_blog_poster import check_session_status as check_naver_status
    llm_status = check_llm_status()
    blogger_ok = bool(os.getenv("BLOGGER_BLOG_ID", ""))
    naver_status = check_naver_status()
    img_prov   = os.getenv("IMAGE_PROVIDER", "pollinations")

    st.caption("**API 상태**")
    vllm_icon = "✅" if llm_status["vllm_available"] else "❌"
    claude_icon = "✅" if llm_status["claude_available"] else "⚪"
    st.markdown(
        f"{vllm_icon} vLLM &nbsp;|&nbsp; {claude_icon} Claude  \n"
        f"{'✅' if blogger_ok else '❌'} Blogger &nbsp;|&nbsp; "
        f"{'✅' if naver_status['ready'] else '❌'} 네이버  \n"
        f"🖼️ {img_prov}",
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

    # ── 자동 수집 ──────────────────────────────────────────────
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

    # ── 수동 키워드 입력 ──────────────────────────────────────
    st.divider()
    st.markdown("### ✏️ 수동 키워드 입력")
    st.markdown('<div class="info-box">트렌드 수집 없이 직접 키워드를 입력할 수 있습니다. 자동 수집과 함께 사용 가능합니다.</div>',
                unsafe_allow_html=True)

    col_inp, col_add = st.columns([4, 1])
    with col_inp:
        manual_input = st.text_input(
            "키워드 입력 (쉼표로 여러 개 입력 가능)",
            placeholder="예: 장윤정, 구속송치, 연예인 논란",
            label_visibility="collapsed",
            key="manual_kw_input",
        )
    with col_add:
        add_btn = st.button("➕ 추가", use_container_width=True)

    if add_btn and manual_input.strip():
        new_kws = [k.strip() for k in manual_input.split(",") if k.strip()]
        existing = st.session_state.manual_keywords
        for kw in new_kws:
            if kw not in existing:
                existing.append(kw)
        st.session_state.manual_keywords = existing
        st.rerun()

    if st.session_state.manual_keywords:
        st.markdown("**추가된 수동 키워드:**")
        cols_m = st.columns(6)
        to_remove = []
        for i, kw in enumerate(st.session_state.manual_keywords):
            with cols_m[i % 6]:
                if st.button(f"✕ {kw}", key=f"rm_{i}", use_container_width=True,
                             help="클릭하면 제거됩니다"):
                    to_remove.append(kw)
        if to_remove:
            st.session_state.manual_keywords = [
                k for k in st.session_state.manual_keywords if k not in to_remove
            ]
            st.rerun()

        if st.button("🗑️ 수동 키워드 전체 초기화", use_container_width=False):
            st.session_state.manual_keywords = []
            st.rerun()

    # ── 자동 수집 결과 ──────────────────────────────────────
    auto_selected = []
    if st.session_state.trends:
        trends = st.session_state.trends
        st.divider()
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
        st.markdown("**📌 자동 수집 키워드에서 선택하세요:**")
        merged = trends["merged"]

        cols = st.columns(3)
        for i, kw in enumerate(merged):
            with cols[i % 3]:
                caret = f" {kw.get('caret', '')}" if kw.get("caret") else ""
                label = f"**{kw['keyword']}**  \n`{kw['source']}`{caret} · {kw['traffic']}"
                if st.checkbox(label, key=f"kw_{i}",
                               value=kw["keyword"] in st.session_state.selected_keywords):
                    auto_selected.append(kw["keyword"])

    # ── 최종 선택 키워드 (자동 + 수동 합산) ─────────────────
    all_selected = auto_selected + [
        k for k in st.session_state.manual_keywords if k not in auto_selected
    ]
    st.session_state.selected_keywords = all_selected

    if all_selected:
        st.divider()
        st.markdown(f"**선택된 키워드 ({len(all_selected)}개):**")
        chips = " ".join([f'<span class="keyword-chip">{k}</span>' for k in all_selected])
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

    pub_tab1, pub_tab2 = st.tabs(["📝 현재 작성 글 발행", "📂 저장된 글 관리"])

    # ── TAB 1: 현재 작성 글 발행 ──────────────────────────
    with pub_tab1:
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

                from modules.naver_blog_poster import check_session_status
                naver_auth = check_session_status()

                st.markdown("**네이버 블로그:**")
                st.write(f"{'✅' if naver_auth['credentials'] else '❌'} NAVER_ID / NAVER_PW")
                st.write(f"{'✅' if naver_auth['session'] else '⚠️'} naver_session.json")
                st.write(f"{'✅' if naver_auth['blog_id'] else '❌'} Blog ID")

                if not naver_auth["ready"]:
                    st.markdown('<div class="warn-box">⚠️ 설정 메뉴에서 네이버 계정을 입력하고, '
                                '터미널에서 <code>python naver_setup.py</code>를 실행해 로그인을 완료해주세요.</div>',
                                unsafe_allow_html=True)

                st.divider()

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
                        st.success(f"✅ 로컬 저장 완료: {fname.name}")
                    except Exception as e:
                        st.error(f"저장 실패: {e}")

                st.divider()
                c1, c2, c3 = st.columns(3)
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
                    if st.button("🚀 구글 발행", type="primary", use_container_width=True):
                        from modules.blogger_publisher import publish_post
                        try:
                            with st.spinner("구글 블로그 발행 중..."):
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
                with c3:
                    if st.button("🟢 네이버 발행", type="primary", use_container_width=True,
                                 disabled=not naver_auth["ready"]):
                        from modules.naver_blog_poster import publish_post as naver_publish_post
                        with st.spinner("네이버 블로그 발행 중..."):
                            st.session_state.naver_publish_result = naver_publish_post(
                                title=final_title,
                                content_html=final_html,
                                tags=st.session_state.post_tags,
                            )
                        st.rerun()

            if st.session_state.publish_result:
                result = st.session_state.publish_result
                if result.get("error"):
                    st.error(f"❌ Blogger 발행 실패: {result['error']}")
                else:
                    st.markdown(f"""
                    <div class="success-box">
                    ✅ <b>Blogger 발행 성공!</b><br>
                    📎 URL: <a href="{result.get('url', '')}" target="_blank">{result.get('url', '')}</a><br>
                    📅 발행일: {result.get('published', '')}
                    </div>
                    """, unsafe_allow_html=True)

            if st.session_state.naver_publish_result:
                naver_result = st.session_state.naver_publish_result
                if naver_result.get("error"):
                    st.error(f"❌ 네이버 발행 실패: {naver_result['error']}")
                    if naver_result.get("screenshot"):
                        st.caption(f"오류 스크린샷 저장됨: {naver_result['screenshot']}")
                else:
                    st.markdown(f"""
                    <div class="success-box">
                    ✅ <b>네이버 블로그 발행 성공!</b><br>
                    📎 URL: <a href="{naver_result.get('url', '')}" target="_blank">{naver_result.get('url', '')}</a>
                    </div>
                    """, unsafe_allow_html=True)

            st.divider()
            st.markdown("### 📋 최근 Blogger 포스팅")

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

    # ── TAB 2: 저장된 글 관리 ─────────────────────────────
    with pub_tab2:
        import json as _json

        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        saved_files = sorted(data_dir.glob("*.json"), reverse=True)

        if not saved_files:
            st.markdown('<div class="info-box">저장된 글이 없습니다. 현재 작성 글 발행 탭에서 "💿 로컬 저장"을 눌러 저장하세요.</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f"**총 {len(saved_files)}개의 저장된 글**")
            st.divider()

            # 선택된 파일 편집 상태 관리
            if "editing_file" not in st.session_state:
                st.session_state.editing_file = None

            for fpath in saved_files:
                try:
                    data = _json.loads(fpath.read_text(encoding="utf-8"))
                except Exception:
                    continue

                saved_at = data.get("saved_at", "")[:16].replace("T", " ")
                ftitle   = data.get("title", fpath.stem)
                tags_str = ", ".join(data.get("tags", []))

                with st.expander(f"📄 {ftitle}  |  {saved_at}", expanded=(st.session_state.editing_file == str(fpath))):
                    if st.session_state.editing_file == str(fpath):
                        # ── 편집 모드 ──────────────────────────
                        st.markdown("**✏️ 편집 모드**")
                        ed_title = st.text_input("제목", value=ftitle, key=f"ed_title_{fpath.name}")
                        ed_tags  = st.text_input("태그 (쉼표 구분)", value=tags_str, key=f"ed_tags_{fpath.name}")
                        ed_meta  = st.text_area("메타 설명", value=data.get("meta_description", ""),
                                                height=60, key=f"ed_meta_{fpath.name}")
                        ed_html  = st.text_area("본문 (HTML)", value=data.get("content_html", ""),
                                                height=300, key=f"ed_html_{fpath.name}")

                        bc1, bc2, bc3 = st.columns(3)
                        with bc1:
                            if st.button("💾 저장", key=f"save_{fpath.name}", use_container_width=True, type="primary"):
                                updated = {
                                    "title":           ed_title,
                                    "content_html":    ed_html,
                                    "tags":            [t.strip() for t in ed_tags.split(",") if t.strip()],
                                    "meta_description": ed_meta,
                                    "saved_at":        data.get("saved_at", ""),
                                    "updated_at":      __import__("datetime").datetime.now().isoformat(),
                                }
                                fpath.write_text(_json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
                                st.session_state.editing_file = None
                                st.success("✅ 저장 완료")
                                st.rerun()
                        with bc2:
                            if st.button("↩️ 취소", key=f"cancel_{fpath.name}", use_container_width=True):
                                st.session_state.editing_file = None
                                st.rerun()
                        with bc3:
                            if st.button("📥 현재 글로 불러오기", key=f"load_ed_{fpath.name}", use_container_width=True):
                                st.session_state.post_title        = ed_title
                                st.session_state.post_content_html = ed_html
                                st.session_state.final_html        = ed_html
                                st.session_state.post_tags         = [t.strip() for t in ed_tags.split(",") if t.strip()]
                                st.session_state.post_meta_desc    = ed_meta
                                st.session_state.editing_file      = None
                                st.session_state.current_page      = "publish"
                                st.success("✅ 글을 불러왔습니다. '현재 작성 글 발행' 탭에서 발행하세요.")
                                st.rerun()
                    else:
                        # ── 목록 모드 ──────────────────────────
                        st.markdown(f"**태그:** {tags_str or '없음'}")
                        st.markdown(f"**저장일:** {saved_at}")

                        mc1, mc2, mc3, mc4 = st.columns(4)
                        with mc1:
                            if st.button("📥 불러오기", key=f"load_{fpath.name}", use_container_width=True, type="primary"):
                                st.session_state.post_title        = data.get("title", "")
                                st.session_state.post_content_html = data.get("content_html", "")
                                st.session_state.final_html        = data.get("content_html", "")
                                st.session_state.post_tags         = data.get("tags", [])
                                st.session_state.post_meta_desc    = data.get("meta_description", "")
                                st.success(f"✅ '{ftitle}' 불러오기 완료! '현재 작성 글 발행' 탭에서 발행하세요.")
                                st.rerun()
                        with mc2:
                            if st.button("✏️ 편집", key=f"edit_{fpath.name}", use_container_width=True):
                                st.session_state.editing_file = str(fpath)
                                st.rerun()
                        with mc3:
                            # 바로 Blogger 발행
                            from modules.blogger_publisher import check_auth_status as _cas
                            _auth = _cas()
                            if _auth["ready"]:
                                if st.button("🚀 바로 발행", key=f"pub_{fpath.name}", use_container_width=True):
                                    from modules.blogger_publisher import publish_post as _pp
                                    try:
                                        with st.spinner("발행 중..."):
                                            r = _pp(
                                                title=data.get("title", ""),
                                                content_html=data.get("content_html", ""),
                                                tags=data.get("tags", []),
                                                is_draft=False,
                                            )
                                        if r.get("error"):
                                            st.error(f"❌ 발행 실패: {r['error']}")
                                        else:
                                            st.success(f"✅ 발행 성공! {r.get('url', '')}")
                                    except Exception as e:
                                        st.error(f"오류: {e}")
                            else:
                                st.button("🚀 바로 발행", key=f"pub_{fpath.name}",
                                          use_container_width=True, disabled=True,
                                          help="Blogger 인증 필요")
                        with mc4:
                            if st.button("🗑️ 삭제", key=f"del_{fpath.name}", use_container_width=True):
                                st.session_state[f"confirm_del_{fpath.name}"] = True
                                st.rerun()

                        if st.session_state.get(f"confirm_del_{fpath.name}"):
                            st.warning(f"⚠️ '{ftitle}' 을(를) 삭제하시겠습니까?")
                            d1, d2 = st.columns(2)
                            with d1:
                                if st.button("✅ 확인 삭제", key=f"do_del_{fpath.name}",
                                             use_container_width=True, type="primary"):
                                    fpath.unlink()
                                    del st.session_state[f"confirm_del_{fpath.name}"]
                                    st.success("삭제 완료")
                                    st.rerun()
                            with d2:
                                if st.button("취소", key=f"cancel_del_{fpath.name}", use_container_width=True):
                                    del st.session_state[f"confirm_del_{fpath.name}"]
                                    st.rerun()

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
        st.markdown("### 🟢 네이버 블로그")
        naver_id = st.text_input("네이버 아이디", value=os.getenv("NAVER_ID", ""))
        naver_pw = st.text_input("네이버 비밀번호", value=os.getenv("NAVER_PW", ""), type="password")
        naver_blog_id = st.text_input("네이버 블로그 ID", value=os.getenv("NAVER_BLOG_ID", ""),
                                       help="블로그 주소 blog.naver.com/{ID} 의 {ID} 부분")

        from modules.naver_blog_poster import check_session_status as _naver_status
        _nstat = _naver_status()
        st.write(f"{'✅' if _nstat['session'] else '⚠️'} naver_session.json "
                 f"{'(로그인 세션 있음)' if _nstat['session'] else '(로그인 필요)'}")
        if not _nstat["session"]:
            st.markdown(
                '<div class="warn-box">⚠️ 설정 저장 후 터미널에서 <code>python naver_setup.py</code>를 '
                '실행해 최초 1회 수동 로그인을 완료해주세요.</div>',
                unsafe_allow_html=True,
            )

        st.divider()

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

        # 클라이언트 타입 감지
        if secret_ok:
            from modules.blogger_publisher import get_client_type
            _ctype = get_client_type()
            if _ctype == "installed":
                st.success("✅ 클라이언트 타입: Desktop app (권장)")
            elif _ctype == "web":
                st.warning("⚠️ 클라이언트 타입: Web application")
                st.markdown("""
<div class="warn-box">
<b>Web application 타입은 추가 설정이 필요합니다:</b><br>
Google Cloud Console → Credentials → 해당 OAuth 클라이언트 → Authorized redirect URIs에<br>
<code>http://localhost</code> 를 추가하거나,<br>
아래 '서버 콜백 URL' 필드에 이 서버의 실제 주소를 입력하세요.<br><br>
<b>권장:</b> Google Cloud Console에서 새 OAuth 클라이언트를 <b>Desktop app</b> 타입으로 생성하면 이 문제 없이 사용 가능합니다.
</div>
                """, unsafe_allow_html=True)

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
                # Web app 타입: redirect URI 입력 필드 표시
                _ctype2 = get_client_type() if secret_ok else "installed"
                _redirect_uri = "http://localhost"
                if _ctype2 == "web":
                    _redirect_uri = st.text_input(
                        "서버 콜백 URL (Google Cloud Console Authorized redirect URIs에 등록된 주소)",
                        value="http://localhost",
                        help="Desktop app 타입이면 http://localhost 그대로 두세요. Web app 타입이면 실제 서버 URL 입력."
                    )

                if st.button("🔗 인증 URL 생성", use_container_width=True):
                    try:
                        from modules.blogger_publisher import get_oauth_url
                        result = get_oauth_url(redirect_uri=_redirect_uri)
                        st.session_state.oauth_url = result["url"]
                        st.session_state.oauth_code_verifier = result["code_verifier"]
                        st.session_state.oauth_redirect_uri = _redirect_uri
                    except Exception as e:
                        st.error(f"URL 생성 실패: {e}")

                if st.session_state.get("oauth_url"):
                    st.markdown("**1.** 아래 URL을 복사해 브라우저에서 열고 Google 계정으로 승인하세요:")
                    st.code(st.session_state.oauth_url, language=None)
                    _ruri = st.session_state.get("oauth_redirect_uri", "http://localhost")
                    if _ruri == "http://localhost":
                        st.markdown("""
<div class="info-box">
<b>2.</b> 승인 후 브라우저가 <code>http://localhost</code> 로 이동하며 <b>'연결할 수 없음'</b> 오류가 표시됩니다.<br>
<b>이것은 정상입니다!</b> 주소창의 전체 URL을 복사해 아래에 붙여넣으세요.<br>
<small>(주소 예시: <code>http://localhost/?code=4/0AX4XfWh...</code>)</small>
</div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"**2.** 승인 후 `{_ruri}` 로 리다이렉트됩니다. 주소창 전체 URL을 아래에 붙여넣으세요.")

                    code_input = st.text_input(
                        "리다이렉트 URL 또는 code= 값 붙여넣기",
                        key="oauth_code_input",
                        label_visibility="collapsed",
                        placeholder="http://localhost/?code=4/0A... 또는 코드만"
                    )
                    if st.button("✅ 인증 완료", type="primary", use_container_width=True) and code_input:
                        try:
                            from modules.blogger_publisher import complete_oauth
                            _saved_ruri = st.session_state.get("oauth_redirect_uri", "http://localhost")
                            _saved_verifier = st.session_state.get("oauth_code_verifier", "")
                            complete_oauth(
                                code_input,
                                redirect_uri=_saved_ruri,
                                code_verifier=_saved_verifier,
                            )
                            st.session_state.oauth_url = None
                            st.session_state.oauth_redirect_uri = None
                            st.session_state.oauth_code_verifier = None
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

# ── 네이버 블로그 ──────────────────────────────────────
NAVER_ID={naver_id}
NAVER_PW={naver_pw}
NAVER_BLOG_ID={naver_blog_id}
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
    with st.expander("Google Blogger API 설정 (OAuth 인증 오류 해결 포함)"):
        st.markdown("""
**기본 설정:**
1. [Google Cloud Console](https://console.cloud.google.com) 접속
2. **APIs & Services > Library** > **Blogger API v3** 활성화
3. **Credentials > Create Credentials > OAuth 2.0 Client ID** 선택
4. 애플리케이션 유형: **Desktop app** 선택 ← 중요!
5. JSON 다운로드 후 위에서 업로드
6. 블로그 ID: Blogger 대시보드 URL의 숫자 부분

---
**⚠️ "redirect_uri_mismatch" 오류가 나는 경우:**

원인: OAuth 클라이언트가 **Web application** 타입으로 생성됨

해결방법 A (권장): **Desktop app** 타입으로 새 OAuth 클라이언트 생성
- Cloud Console → Credentials → Create Credentials → OAuth 2.0 Client ID → Desktop app

해결방법 B: 기존 Web app 클라이언트의 Authorized redirect URIs에 `http://localhost` 추가
- Cloud Console → Credentials → 해당 클라이언트 클릭 → Authorized redirect URIs → `http://localhost` 추가

---
**ℹ️ 인증 후 "연결할 수 없음" 오류가 나는 경우:**
Desktop app 타입에서는 정상입니다. 브라우저 주소창의 URL(http://localhost/?code=...)을 복사해 붙여넣으면 됩니다.
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
    st.markdown('<div class="step-header">📚 매뉴얼 · 사용 가이드 및 기술 스택</div>', unsafe_allow_html=True)

    tab_guide, tab_stack, tab_trouble, tab_changelog = st.tabs(
        ["📖 사용 가이드", "🏗️ 기술 스택", "🔧 문제 해결", "📋 변경 이력"]
    )

    # ── 사용 가이드 ───────────────────────────────────────────
    with tab_guide:
        st.markdown("## 🔄 전체 파이프라인")
        st.code(
            "📊 트렌드 수집 → ✍️ 콘텐츠 작성 → 🎨 미디어 → 🚀 발행",
            language="text",
        )

        st.markdown("### 📊 STEP 1 · 트렌드 수집")
        st.markdown("""
<div class="tech-card">
1. <b>🔍 트렌드 수집 시작</b> 버튼 클릭<br>
2. 네이버·구글 실시간 검색어 목록 확인<br>
3. 포스팅에 사용할 키워드 체크박스로 선택<br>
4. <b>✍️ 콘텐츠 작성 →</b> 버튼으로 다음 단계 이동
</div>
        """, unsafe_allow_html=True)

        st.markdown("### ✍️ STEP 2 · 콘텐츠 작성")
        st.markdown("""
<div class="tech-card">
<b>2-1. 주제 선정</b><br>
- <b>🤖 주제 추천 받기</b>: vLLM/Claude가 선택한 키워드로 블로그 주제 5개 추천<br>
- 원하는 주제 <b>📝 선택</b> 또는 직접 제목 입력<br><br>
<b>2-2. 본문 생성</b><br>
- 톤 선택 (정보전달/친근한/전문적/뉴스형)<br>
- <b>🤖 본문 생성</b>: AI가 SEO 최적화 HTML 본문 자동 작성<br>
- 생성된 본문 직접 편집 또는 AI 수정 요청 가능<br>
- 태그·메타 설명 확인 및 수정
</div>
        """, unsafe_allow_html=True)

        st.markdown("### 🎨 STEP 3 · 미디어")
        st.markdown("""
<div class="tech-card">
- 이미지 생성 방식 선택 (Pollinations 권장)<br>
- 이미지 프롬프트 3개 확인·수정 (영어 권장)<br>
- <b>🖼️ 이미지 생성 & 삽입</b>: 이미지 3개 자동 생성 후 본문에 삽입<br>
- 실패 시 자동으로 Picsum 사진으로 대체
</div>
        """, unsafe_allow_html=True)

        st.markdown("### 🚀 STEP 4 · 발행")
        st.markdown("""
<div class="tech-card">
- <b>💿 로컬 저장</b>: OAuth 없이 data/ 폴더에 JSON 저장<br>
- <b>💾 Blogger 임시저장</b>: 블로그에 Draft로 저장 (OAuth 필요)<br>
- <b>🚀 즉시 발행</b>: 블로그에 즉시 발행 (OAuth 필요)<br><br>
<b>발행 전 필수:</b> 설정 탭에서 Google OAuth 인증 완료
</div>
        """, unsafe_allow_html=True)

        st.divider()
        st.markdown("## 🔑 Google OAuth 인증 방법")
        st.markdown("""
<div class="tech-card">
<b>① Google Cloud Console 설정</b><br>
1. <a href="https://console.cloud.google.com">console.cloud.google.com</a> 접속<br>
2. APIs & Services → Library → <b>Blogger API v3</b> 활성화<br>
3. Credentials → Create Credentials → <b>OAuth 2.0 Client ID</b><br>
4. 애플리케이션 유형: <b>Desktop app</b> ← 반드시 Desktop app!<br>
5. JSON 다운로드<br><br>

<b>② 앱에서 인증</b><br>
1. 설정 탭 → client_secret.json 업로드<br>
2. 🔗 인증 URL 생성 클릭<br>
3. URL 복사 → 브라우저에서 열기 → Google 계정 승인<br>
4. 브라우저가 <code>http://localhost/?code=...</code>로 이동<br>
   → <b>"연결할 수 없음" 오류는 정상!</b> 주소창 URL을 복사하면 됩니다<br>
5. 복사한 URL을 입력창에 붙여넣기 → ✅ 인증 완료 클릭
</div>
        """, unsafe_allow_html=True)

    # ── 기술 스택 ──────────────────────────────────────────────
    with tab_stack:
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
<b>Anthropic Claude API</b> <span class="tech-badge">Fallback</span><br>
vLLM 불가 시 자동으로 Claude로 전환. <code>claude-sonnet-4-6</code> 기본값.
</div>
            """, unsafe_allow_html=True)

            st.markdown("### 🖼️ 이미지 생성 (5가지 프로바이더)")
            st.markdown("""
<div class="tech-card">
<b>Pollinations.ai</b> <span class="tech-badge">무료 · 기본값</span><br>
API 키 없이 URL 파라미터로 이미지를 생성하는 무료 서비스.<br><br>
<b>Lorem Picsum</b> <span class="tech-badge">무료 · 항상 성공</span><br>
고품질 랜덤 실사 사진. 속도 빠름. Pollinations 실패 시 자동 fallback.<br><br>
<b>HuggingFace SD XL</b> <span class="tech-badge">무료 토큰</span><br>
Stable Diffusion XL AI 이미지 생성.<br><br>
<b>Claude + Pollinations</b> <span class="tech-badge">선택</span><br>
Claude가 프롬프트를 영어로 강화 후 Pollinations으로 렌더링.<br><br>
<b>OpenAI DALL-E 3</b> <span class="tech-badge">유료</span><br>
최고 품질 AI 이미지. OpenAI API 키 필요.
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
<b>google-auth-oauthlib · Flow</b> <span class="tech-badge">v1.2+</span><br>
OAuth 2.0 PKCE S256 방식 인증.<br>
<code>client_secret.json</code> + <code>token.json</code>으로 토큰을 발급·갱신합니다.
</div>
            """, unsafe_allow_html=True)

            st.markdown("### 📝 AI 감지 회피")
            st.markdown("""
<div class="tech-card">
<b>구글 AdSense AI 감지 회피 전략</b> <span class="tech-badge">프롬프트 최적화</span><br>
- 문장 길이 불규칙 (짧은 ↔ 긴 문장 혼재)<br>
- 구체적 숫자·날짜·경험담 삽입<br>
- 구어체·감탄사·수사적 질문 활용<br>
- AI 전형 표현 회피 ("알아보겠습니다" → "얘기해볼게요")<br>
- E-E-A-T (경험·전문성·권위성·신뢰성) 반영<br>
- 태그 8~10개 (핵심 키워드 + 연관 검색어)
</div>
            """, unsafe_allow_html=True)

            st.markdown("### 🛠️ 유틸리티")
            st.markdown("""
<div class="tech-card">
<b>python-dotenv</b> <span class="tech-badge">v1.0+</span><br>
<code>.env</code> 파일에서 환경 변수를 로드. API 키·서버 주소 등 관리.<br><br>
<b>requests</b> <span class="tech-badge">v2.31+</span><br>
HTTP 요청. 트렌드 API 호출 및 이미지 다운로드에 사용.
</div>
            """, unsafe_allow_html=True)

        st.divider()
        st.markdown("## 📁 프로젝트 구조")
        st.code("""
blog/
├── app.py                    # 메인 Streamlit 앱 (사이드바 네비게이션)
├── requirements.txt          # Python 패키지 목록
├── .env                      # 환경 변수 (API 키 등, git 제외)
├── client_secret.json        # Google OAuth 비밀키 (git 제외)
├── token.json                # OAuth 토큰 (자동 생성, git 제외)
├── data/                     # 로컬 저장 포스팅 (JSON)
└── modules/
    ├── trend_collector.py    # 트렌드 수집 (Loword + Google RSS)
    ├── content_generator.py  # LLM 생성 (vLLM → Claude fallback)
    ├── image_generator.py    # 이미지 생성 (5가지 프로바이더)
    └── blogger_publisher.py  # Blogger 발행 (PKCE OAuth)
        """, language="text")

        st.markdown("## ⚙️ 환경 변수")
        st.markdown("""
| 변수명 | 설명 | 예시 |
|--------|------|------|
| `LLM_ADDR` | vLLM 서버 주소 | `http://192.168.1.1:8000` |
| `LLM_MODEL` | LLM 모델명 | `google/gemma-4-31b-it` |
| `ANTHROPIC_API_KEY` | Claude API 키 (fallback) | `sk-ant-...` |
| `CLAUDE_MODEL` | Claude 모델 | `claude-sonnet-4-6` |
| `IMAGE_PROVIDER` | 이미지 생성 방식 | `pollinations` |
| `HUGGINGFACE_TOKEN` | HF 토큰 (선택) | `hf_...` |
| `OPENAI_API_KEY` | OpenAI 키 (DALL-E용) | `sk-...` |
| `BLOGGER_BLOG_ID` | Blogger 블로그 ID | `1234567890` |
        """)

    # ── 문제 해결 ──────────────────────────────────────────────
    with tab_trouble:
        st.markdown("## 🔧 자주 발생하는 문제")

        with st.expander("OAuth 오류: redirect_uri_mismatch", expanded=False):
            st.markdown("""
**원인**: OAuth 클라이언트가 Web application 타입으로 생성됨

**해결**:
- Google Cloud Console → Credentials → 새 OAuth 2.0 Client ID 생성
- 애플리케이션 유형: **Desktop app** 선택
- 기존 client_secret.json을 새것으로 교체 후 재인증
            """)

        with st.expander("OAuth 오류: invalid_grant / Missing code verifier", expanded=False):
            st.markdown("""
**원인**: 이전에 생성한 인증 URL을 재사용하거나, 코드가 만료됨

**해결**:
1. 설정 탭 → 🔄 토큰 재발급 클릭
2. 🔗 인증 URL 생성을 다시 클릭해 새 URL 생성
3. 새 URL로 다시 인증 진행
            """)

        with st.expander("이미지 생성 실패 (Pollinations 오류)", expanded=False):
            st.markdown("""
**원인**: Pollinations.ai 서버 응답 지연 또는 타임아웃

**해결**:
- 미디어 탭에서 이미지 생성 방식을 **Picsum** 으로 변경 후 재시도
- Pollinations는 자동으로 Picsum으로 fallback되므로 결과는 표시됨
- 잠시 후 다시 Pollinations 시도
            """)

        with st.expander("블로그 발행 실패 (HttpError 403)", expanded=False):
            st.markdown("""
**원인**: OAuth 인증한 Google 계정이 해당 블로그의 소유자·관리자가 아님

**해결**:
1. 설정 탭 → 🔄 토큰 재발급
2. 블로그를 소유한 Google 계정으로 재인증
3. 블로그 연결 테스트로 확인
            """)

        with st.expander("블로그 발행 실패 (HttpError 404)", expanded=False):
            st.markdown("""
**원인**: 블로그 ID가 잘못됨

**해결**:
1. Blogger 관리 페이지 (blogger.com) 접속
2. 해당 블로그 선택 → 주소창 URL에서 숫자 ID 확인
   예: `www.blogger.com/blog/posts/1234567890123456789` → ID: `1234567890123456789`
3. 설정 탭 → Blog ID 수정 후 저장
            """)

        with st.expander("vLLM 연결 안 됨", expanded=False):
            st.markdown("""
**증상**: 사이드바에 ❌ vLLM 표시

**해결**:
- 설정 탭에서 LLM 서버 주소 확인
- vLLM 서버가 실행 중인지 확인
- vLLM 불가 시 Claude로 자동 전환됨 (ANTHROPIC_API_KEY 필요)
            """)

    # ── 변경 이력 ──────────────────────────────────────────────
    with tab_changelog:
        st.markdown("## 📋 변경 이력")
        st.markdown("""
| 날짜 | 변경 내용 |
|------|-----------|
| 2026-07-22 | AI 감지 회피 프롬프트 강화, 태그 8~10개로 확대 |
| 2026-07-22 | OAuth PKCE S256 직접 구현 (invalid_grant 오류 완전 해결) |
| 2026-07-22 | OAuth Flow 클래스로 교체 (InstalledAppFlow PKCE 충돌 제거) |
| 2026-07-22 | OAuth 클라이언트 타입 감지 (Desktop app / Web app) 및 안내 |
| 2026-07-22 | 블로그 연결 테스트 기능 추가 (설정 탭) |
| 2026-07-22 | 로컬 data 폴더 저장 기능 추가 (OAuth 없이도 저장 가능) |
| 2026-07-22 | 전체화면 로딩 모달 (CSS st.spinner 오버레이) |
| 2026-07-22 | vLLM → Claude 자동 fallback, 사이드바 실시간 LLM 상태 표시 |
| 2026-07-22 | 이미지 다중 프로바이더 + 자동 fallback (5가지) |
| 2026-07-22 | 사이드바 네비게이션 UI 전면 개편 (탭 → 사이드바) |
| 2026-07-22 | 매뉴얼 페이지 추가 |
        """)
