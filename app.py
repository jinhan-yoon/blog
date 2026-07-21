"""AI 블로그 자동화 대시보드 - 기능별 재구성 버전"""

import os
import json
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

load_dotenv()

# ── 페이지 설정 ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI 블로그 자동화 대시보드",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 전역 CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.step-header {
    background: linear-gradient(90deg, #4f46e5 0%, #7c3aed 100%);
    color: white;
    padding: 12px 20px;
    border-radius: 10px;
    margin-bottom: 16px;
    font-weight: bold;
    font-size: 1.1em;
}
.info-box {
    background: #f0f9ff;
    border-left: 4px solid #0ea5e9;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    margin: 8px 0;
}
.success-box {
    background: #f0fdf4;
    border-left: 4px solid #22c55e;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    margin: 8px 0;
}
.warn-box {
    background: #fffbeb;
    border-left: 4px solid #f59e0b;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    margin: 8px 0;
}
.keyword-chip {
    display: inline-block;
    background: #ede9fe;
    color: #5b21b6;
    padding: 4px 12px;
    border-radius: 20px;
    margin: 3px;
    font-size: 0.85em;
    font-weight: 500;
}
.post-preview {
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 24px;
    background: #fafafa;
    color: #1f2937;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.dark .post-preview {
    background: #1e293b;
    color: #f1f5f9;
}
</style>
""", unsafe_allow_html=True)

# ── 세션 초기화 ──────────────────────────────────────────────────────────────
def init_session():
    defaults = {
        # 트렌드 관련
        "trends": None,
        "trends_history": {},
        "selected_keywords": [],

        # 콘텐츠 작성 관련
        "post_topic": None,
        "post_title": "",
        "post_content_html": "",
        "post_meta_desc": "",
        "post_tags": [],
        "image_prompts": [],
        "topics": None,

        # 미디어 관련
        "image_urls": [],
        "final_html": "",

        # 발행 관련
        "publish_result": None,
        "publish_history": [],

        # UI 상태
        "content_mode": "create",  # "create" 또는 "edit"
        "target_tab": None,  # 다음 탭으로 이동할 때 사용
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# ── 탭 자동전환 헬퍼 ──────────────────────────────────────────────────────
def _auto_switch_tab(tab_index: int):
    """JavaScript로 지정한 인덱스의 탭을 클릭 (0-base)"""
    import streamlit.components.v1 as components
    components.html(
        f"""<script>
        setTimeout(function() {{
            var tabs = window.parent.document.querySelectorAll('button[role="tab"]');
            if (tabs.length > {tab_index}) tabs[{tab_index}].click();
        }}, 300);
        </script>""",
        height=0,
    )

# 다음 탭으로 이동
if st.session_state.get("target_tab") is not None:
    import time
    if not hasattr(st.session_state, '_tab_switched_at'):
        st.session_state._tab_switched_at = 0

    current_time = time.time()
    if current_time - st.session_state._tab_switched_at > 0.3:
        _auto_switch_tab(st.session_state.target_tab)
        st.session_state._tab_switched_at = current_time
        st.session_state.target_tab = None

# ── 사이드바 ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🤖 AI 블로그 자동화")
    st.caption("Google Trends → Gemini → Blogger")

    st.divider()

    # 진행 상황 요약
    st.markdown("### 📋 진행 상황")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("선택된 키워드", len(st.session_state.selected_keywords))
    with col2:
        st.metric("작성된 글", "✓" if st.session_state.post_title else "✗")

    st.divider()

    # API 상태 표시
    llm_ok = bool(os.getenv("LLM_ADDR", ""))
    blogger_ok = bool(os.getenv("BLOGGER_BLOG_ID", ""))
    image_provider = os.getenv("IMAGE_PROVIDER", "pollinations")

    st.caption("**API 연결 상태**")
    st.write(f"{'✅' if llm_ok else '❌'} vLLM 서버 ({os.getenv('LLM_ADDR', '미설정')})")
    st.write(f"{'✅' if blogger_ok else '❌'} Blogger ID")
    st.write(f"🖼️ 이미지: {image_provider.upper()}")

    if not llm_ok:
        st.warning("⚙️ 설정 탭에서 LLM 서버 주소를 입력해주세요.")

# ── 탭 구성 ──────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 트렌드 수집",
    "✍️ 콘텐츠 작성",
    "🎨 미디어",
    "🚀 발행",
    "⚙️ 설정",
])

# ════════════════════════════════════════════════════════
# TAB 1: 트렌드 수집
# ════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="step-header">📊 트렌드 수집 및 관리</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("""
        <div class="info-box">
        Google 트렌드, 네이버, 다음에서 실시간 급상승 검색어를 자동으로 수집합니다.
        </div>
        """, unsafe_allow_html=True)
    with col2:
        collect_btn = st.button("🔍 트렌드 수집 시작", type="primary", use_container_width=True)

    if collect_btn:
        with st.spinner("트렌드 키워드 수집 중..."):
            from modules.trend_collector import collect_all_trends
            st.session_state.trends = collect_all_trends()
        st.rerun()

    if st.session_state.trends:
        trends = st.session_state.trends

        # ── 수집된 키워드 리스트 표시 ──────────────────────────────────────
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
                    traffic_str = f"  `{traffic}`" if traffic and traffic != "N/A" else ""
                    st.markdown(f"`{str(kw['rank']).zfill(2)}` **{kw['keyword']}**{traffic_str}")
            else:
                st.info("구글 데이터 없음")

        st.divider()

        # ── 키워드 선택 ────────────────────────────────────────────────────
        st.markdown("**📌 콘텐츠 작성에 사용할 키워드를 선택하세요:**")
        merged = trends["merged"]

        selected = []
        cols = st.columns(3)
        for i, kw in enumerate(merged):
            with cols[i % 3]:
                caret = f" {kw.get('caret', '')}" if kw.get("caret") else ""
                label = f"**{kw['keyword']}**  \n`{kw['source']}`{caret} · {kw['traffic']}"
                checked = st.checkbox(
                    label,
                    key=f"kw_{i}",
                    value=kw["keyword"] in st.session_state.selected_keywords,
                )
                if checked:
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
                    st.session_state.target_tab = 1
                    st.rerun()

# ════════════════════════════════════════════════════════
# TAB 2: 콘텐츠 작성 (주제 선정 + 본문 생성 통합)
# ════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="step-header">✍️ 콘텐츠 작성</div>', unsafe_allow_html=True)

    if not st.session_state.selected_keywords:
        st.markdown('<div class="warn-box">⚠️ 먼저 "트렌드 수집" 탭에서 키워드를 선택해주세요.</div>', unsafe_allow_html=True)
    else:
        # ────────────────────────────────────────────────────────────────
        # STEP 1: 주제 선정 섹션
        # ────────────────────────────────────────────────────────────────
        st.markdown("### 🎯 STEP 1: 주제 선정")

        selected_kws = st.session_state.selected_keywords
        st.markdown(f"**선택된 키워드:** {', '.join(selected_kws)}")

        col1, col2 = st.columns([2, 1])
        with col1:
            topic_count = st.slider("추천 주제 수", 3, 8, 5)
        with col2:
            suggest_btn = st.button("🤖 주제 추천 받기", type="primary", use_container_width=True)

        topics = []
        if suggest_btn:
            with st.spinner("vLLM이 주제를 분석 중..."):
                try:
                    from modules.content_generator import suggest_topics
                    topics = suggest_topics(selected_kws, topic_count)
                except Exception as e:
                    st.error(f"오류: {e}")
            if topics:
                st.success(f"✅ {len(topics)}개 주제가 추천되었습니다!")
                st.rerun()

        # 이전에 추천받은 주제가 있으면 표시
        topic_container = st.container()
        with topic_container:
            if 'topics' in st.session_state and st.session_state.topics:
                topics = st.session_state.topics
                st.divider()
                st.markdown("**추천 주제 목록:**")

                for i, topic in enumerate(topics):
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        st.markdown(f"**{i+1}. {topic['title']}**")
                        st.caption(f"📌 주제: {topic['topic']}")
                        st.caption(f"💡 이유: {topic['reason']}")
                        chips = " ".join([f'<span class="keyword-chip">{k}</span>' for k in topic.get("keywords", [])])
                        st.markdown(chips, unsafe_allow_html=True)
                    with col2:
                        if st.button("📝 선택", key=f"topic_{i}", use_container_width=True):
                            st.session_state.post_topic = topic
                            st.session_state.post_title = topic["title"]
                            st.session_state.topics = None  # 주제 목록 초기화
                            st.success("주제가 선택되었습니다!")
                            st.rerun()
                    st.divider()

                # 직접 입력 옵션
                with st.expander("또는 직접 제목 입력"):
                    custom_title = st.text_input("사용자 정의 제목", value=st.session_state.post_title)
                    if custom_title and custom_title != st.session_state.post_title:
                        st.session_state.post_title = custom_title
                        st.success("제목이 입력되었습니다!")
                        st.rerun()

        # ────────────────────────────────────────────────────────────────
        # STEP 2: 본문 생성 섹션
        # ────────────────────────────────────────────────────────────────
        if st.session_state.post_title:
            st.divider()
            st.markdown("### ✍️ STEP 2: 본문 생성")

            st.markdown(f"**선택된 제목:** {st.session_state.post_title}")

            col1, col2, col3 = st.columns(3)
            with col1:
                tone = st.selectbox("톤앤매너", ["정보전달", "친근한", "전문적", "뉴스형"])
            with col2:
                topic_kws = st.session_state.post_topic.get("keywords", []) if st.session_state.post_topic else st.session_state.selected_keywords
                extra_kw = st.text_input("추가 키워드 (쉼표 구분)", value=", ".join(topic_kws))
            with col3:
                st.markdown("<br>", unsafe_allow_html=True)
                gen_btn = st.button("🤖 본문 생성", type="primary", use_container_width=True)

            if gen_btn:
                kws = [k.strip() for k in extra_kw.split(",") if k.strip()]
                with st.spinner("vLLM이 본문을 작성 중... (약 20-40초 소요)"):
                    try:
                        from modules.content_generator import generate_blog_post
                        result = generate_blog_post(st.session_state.post_title, kws, tone)
                        st.session_state.post_title = result.get("title", st.session_state.post_title)
                        st.session_state.post_content_html = result.get("content_html", "")
                        st.session_state.post_meta_desc = result.get("meta_description", "")
                        st.session_state.post_tags = result.get("tags", [])
                        st.session_state.image_prompts = result.get("image_prompts", [])
                        st.success("✅ 본문이 생성되었습니다!")
                    except Exception as e:
                        st.error(f"오류: {e}")
                st.rerun()

            # 본문 편집
            if st.session_state.post_content_html:
                st.divider()

                col1, col2 = st.columns([1, 1])
                with col1:
                    st.markdown("**📝 본문 편집**")
                    edited_html = st.text_area(
                        "HTML 본문 (직접 수정 가능)",
                        value=st.session_state.post_content_html,
                        height=400,
                    )
                    st.session_state.post_content_html = edited_html

                    # AI로 수정 요청
                    refine_instruction = st.text_input("✏️ AI에게 수정 요청 (예: '더 친근하게 바꿔줘', '길이를 늘려줘')")
                    if st.button("🤖 AI 수정 적용") and refine_instruction:
                        with st.spinner("수정 중..."):
                            try:
                                from modules.content_generator import refine_content
                                st.session_state.post_content_html = refine_content(edited_html, refine_instruction)
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
                        unsafe_allow_html=True
                    )

                st.divider()
                col1, col2 = st.columns(2)
                with col1:
                    tags_input = st.text_input("태그 (쉼표 구분)", value=", ".join(st.session_state.post_tags))
                    st.session_state.post_tags = [t.strip() for t in tags_input.split(",") if t.strip()]
                with col2:
                    meta_desc = st.text_area("메타 설명 (SEO)", value=st.session_state.post_meta_desc, height=80)
                    st.session_state.post_meta_desc = meta_desc

                st.divider()
                col1, col2 = st.columns([3, 1])
                with col2:
                    if st.button("🎨 미디어 →", type="primary", use_container_width=True):
                        st.session_state.target_tab = 2
                        st.rerun()

# ════════════════════════════════════════════════════════
# TAB 3: 미디어 (이미지 생성)
# ════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="step-header">🎨 미디어 · 이미지 생성 및 삽입</div>', unsafe_allow_html=True)

    if not st.session_state.post_content_html:
        st.markdown('<div class="warn-box">⚠️ "콘텐츠 작성" 탭에서 본문을 먼저 작성해주세요.</div>', unsafe_allow_html=True)
    else:
        provider = os.getenv("IMAGE_PROVIDER", "pollinations")
        st.markdown(f"**이미지 생성 방식:** `{provider.upper()}`  (설정 탭에서 변경)")

        # 항상 3개의 이미지 프롬프트 표시
        if not st.session_state.image_prompts:
            st.session_state.image_prompts = ["blog post illustration", "relevant image", "article image"]

        st.markdown("**AI가 제안한 이미지 프롬프트 (수정 가능):**")
        edited_prompts = []
        for i in range(3):
            current_prompt = st.session_state.image_prompts[i] if i < len(st.session_state.image_prompts) else ""
            edited = st.text_input(f"이미지 {i+1} 설명", value=current_prompt, key=f"img_prompt_{i}")
            edited_prompts.append(edited)
        st.session_state.image_prompts = edited_prompts

        gen_img_btn = st.button("🖼️ 이미지 생성 & 본문 삽입", type="primary")

        if gen_img_btn:
            prompts = st.session_state.image_prompts[:3]
            with st.spinner(f"{len(prompts)}개 이미지 생성 중..."):
                try:
                    from modules.image_generator import generate_images_for_post, insert_images_into_html
                    st.session_state.image_urls = generate_images_for_post(prompts, provider)
                    st.session_state.final_html = insert_images_into_html(
                        st.session_state.post_content_html,
                        st.session_state.image_urls,
                    )
                    st.success("✅ 이미지 삽입 완료!")
                except Exception as e:
                    st.error(f"오류: {e}")
            st.rerun()

        if st.session_state.image_urls:
            st.divider()
            st.markdown("**생성된 이미지 미리보기:**")
            cols = st.columns(min(len(st.session_state.image_urls), 3))
            for i, url in enumerate(st.session_state.image_urls):
                with cols[i % 3]:
                    st.image(url, caption=f"이미지 {i+1}", use_container_width=True)
            st.divider()

        if not st.session_state.final_html and st.session_state.post_content_html:
            st.divider()
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button("⏭️ 이미지 없이 다음 단계로 진행"):
                    st.session_state.final_html = st.session_state.post_content_html
                    st.success("이미지 단계를 건너뛰었습니다!")
                    st.rerun()
            with col2:
                pass

        if st.session_state.final_html:
            st.divider()
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("🚀 발행 →", type="primary", use_container_width=True):
                    st.session_state.target_tab = 3
                    st.rerun()

# ════════════════════════════════════════════════════════
# TAB 4: 발행 (미리보기 + 발행 + 포스팅 관리)
# ════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="step-header">🚀 발행 및 포스팅 관리</div>', unsafe_allow_html=True)

    final_html = st.session_state.final_html or st.session_state.post_content_html
    title = st.session_state.post_title

    if not final_html:
        st.markdown('<div class="warn-box">⚠️ 콘텐츠를 작성한 후 이 탭에서 발행하세요.</div>', unsafe_allow_html=True)
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
                unsafe_allow_html=True
            )

        with col2:
            st.markdown("**🚀 발행 설정**")

            final_title = st.text_input("제목 최종 확인", value=title)
            is_draft = st.checkbox("임시저장으로 발행 (바로 공개하지 않음)", value=False)

            st.divider()

            # Blogger 인증 상태 확인
            from modules.blogger_publisher import check_auth_status
            auth = check_auth_status()

            st.markdown("**인증 상태:**")
            st.write(f"{'✅' if auth['client_secret'] else '❌'} client_secret.json")
            st.write(f"{'✅' if auth.get('token_valid') else '⚠️'} OAuth 토큰")
            st.write(f"{'✅' if auth['blog_id'] else '❌'} Blog ID")

            st.divider()

            if not auth["ready"]:
                st.markdown("""
                <div class="warn-box">
                ⚠️ <b>Blogger 연동 미완료</b><br>
                설정 탭에서 client_secret.json 업로드 및 Blog ID를 설정하세요.
                </div>
                """, unsafe_allow_html=True)

            col_draft, col_pub = st.columns(2)
            with col_draft:
                if st.button("💾 임시저장", use_container_width=True):
                    from modules.blogger_publisher import publish_post
                    try:
                        with st.spinner("Blogger에 발행 중..."):
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
            with col_pub:
                if st.button("🚀 즉시 발행", type="primary", use_container_width=True):
                    from modules.blogger_publisher import publish_post
                    try:
                        with st.spinner("Blogger에 발행 중..."):
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
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("⚙️ 설정 →", type="primary", use_container_width=True):
                st.session_state.target_tab = 4
                st.rerun()

        # ────────────────────────────────────────────────────────────────
        # 포스팅 관리 섹션
        # ────────────────────────────────────────────────────────────────
        st.divider()
        st.markdown("### 📋 최근 포스팅")

        from modules.blogger_publisher import check_auth_status
        auth = check_auth_status()

        if st.button("🔄 포스팅 목록 새로고침"):
            if auth["ready"]:
                try:
                    from modules.blogger_publisher import list_recent_posts
                    posts = list_recent_posts()
                    for p in posts:
                        status_icon = "🟢" if p["status"] == "LIVE" else "📝"
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.markdown(f"{status_icon} [{p['title']}]({p.get('url', '#')}) · {p['published'][:10] if p['published'] else ''}")
                        with col2:
                            if st.button("삭제", key=f"delete_{p['id']}", use_container_width=True):
                                st.info("(삭제 기능은 다음 버전에서 추가됩니다)")
                except Exception as e:
                    st.error(f"조회 실패: {e}")
            else:
                st.warning("Blogger 인증이 필요합니다.")

# ════════════════════════════════════════════════════════
# TAB 5: 설정
# ════════════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="step-header">⚙️ 설정 · API 키 및 환경 구성</div>', unsafe_allow_html=True)

    env_path = Path(".env")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🤖 LLM 서버 (vLLM)")
        llm_addr = st.text_input(
            "LLM 서버 주소",
            value=os.getenv("LLM_ADDR", "http://210.127.59.40:8000"),
            help="vLLM OpenAI 호환 서버 주소 (예: http://host:8000)"
        )
        llm_model = st.text_input(
            "LLM 모델명",
            value=os.getenv("LLM_MODEL", "google/gemma-4-31b-it"),
        )
        llm_api_key = st.text_input(
            "LLM API Key",
            value=os.getenv("LLM_API_KEY", "EMPTY"),
            type="password",
            help="vLLM은 보통 EMPTY 사용"
        )

        st.markdown("### 🖼️ 이미지 생성")
        _provider_opts = ["pollinations", "claude", "dalle"]
        _cur_provider = os.getenv("IMAGE_PROVIDER", "pollinations")
        _provider_idx = _provider_opts.index(_cur_provider) if _cur_provider in _provider_opts else 0
        img_provider = st.selectbox(
            "이미지 생성 방식",
            _provider_opts,
            index=_provider_idx,
            help="pollinations: 무료 / claude: Claude 프롬프트 강화 후 Pollinations 렌더링 / dalle: OpenAI API 키 필요"
        )
        anthropic_key = st.text_input(
            "Anthropic API Key (Claude용)",
            value=os.getenv("ANTHROPIC_API_KEY", ""),
            type="password",
        )
        openai_key = st.text_input(
            "OpenAI API Key (DALL-E 3용)",
            value=os.getenv("OPENAI_API_KEY", ""),
            type="password",
        )

    with col2:
        st.markdown("### 📝 Google Blogger")
        blog_id = st.text_input(
            "Blogger Blog ID",
            value=os.getenv("BLOGGER_BLOG_ID", ""),
            help="블로그 URL: https://www.blogger.com/blog/posts/{Blog ID}"
        )

        st.markdown("### 🔑 OAuth 2.0 인증 파일")
        uploaded_secret = st.file_uploader(
            "client_secret.json 업로드",
            type="json",
            help="Google Cloud Console > APIs & Services > Credentials > OAuth 2.0 Client ID"
        )
        if uploaded_secret:
            with open("client_secret.json", "wb") as f:
                f.write(uploaded_secret.read())
            st.success("✅ client_secret.json 저장됨")

        if Path("client_secret.json").exists():
            st.success("✅ client_secret.json 존재")
        else:
            st.warning("⚠️ client_secret.json 없음")

        if Path("token.json").exists():
            st.success("✅ OAuth 토큰 존재")
            if st.button("🔄 토큰 재발급"):
                Path("token.json").unlink()
                st.info("토큰 삭제됨. 다음 발행 시 재인증이 필요합니다.")
        else:
            st.info("ℹ️ OAuth 토큰 없음 (최초 발행 시 브라우저 인증 필요)")

    st.divider()
    if st.button("💾 설정 저장", type="primary"):
        env_content = f"""# ── LLM 서버 (vLLM, OpenAI 호환) ──────────────────────────────
LLM_ADDR={llm_addr}
LLM_MODEL={llm_model}
LLM_API_KEY={llm_api_key}

# ── 이미지 생성 ────────────────────────────────────────────────
IMAGE_PROVIDER={img_provider}
ANTHROPIC_API_KEY={anthropic_key}
OPENAI_API_KEY={openai_key}

# ── Google Blogger ──────────────────────────────────────────────
BLOGGER_BLOG_ID={blog_id}
"""
        with open(".env", "w") as f:
            f.write(env_content)
        load_dotenv(override=True)
        st.success("✅ 설정이 .env 파일에 저장되었습니다. 페이지를 새로고침하세요.")

    st.divider()
    st.markdown("### 📚 설정 가이드")
    with st.expander("Claude (Anthropic) API 키 발급 방법"):
        st.markdown("""
        1. [Anthropic Console](https://console.anthropic.com) 접속
        2. 로그인 후 **API Keys** 클릭
        3. **Create Key** 로 새 키 생성 후 복사
        4. 위 Anthropic API Key 입력란에 붙여넣기 후 저장
        5. 이미지 생성 방식을 **claude** 로 선택하면 Claude가 프롬프트를 강화하여 Pollinations.ai로 이미지 생성
        """)
    with st.expander("Google Blogger API 설정 방법"):
        st.markdown("""
        1. [Google Cloud Console](https://console.cloud.google.com) 접속
        2. 새 프로젝트 생성 또는 기존 프로젝트 선택
        3. **APIs & Services > Library** 에서 **Blogger API v3** 활성화
        4. **Credentials > Create Credentials > OAuth 2.0 Client ID** 생성
           - Application type: **Desktop app**
        5. JSON 다운로드 후 위에서 업로드
        6. 블로그 ID 확인: Blogger 대시보드 URL에서 숫자 부분
        """)
    with st.expander("Pollinations.ai (무료 이미지)"):
        st.markdown("""
        - API 키 불필요, 완전 무료
        - 요청당 이미지 1024×576 픽셀 생성
        - 상업적 이용 가능
        - 속도: 생성에 5-15초 소요
        """)
