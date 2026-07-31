"""콘텐츠 생성 모듈 — vLLM 우선, 불가 시 Claude 자동 fallback"""
from __future__ import annotations

import os
import json
import re
import requests as _requests
from bs4 import BeautifulSoup as _BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

_SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# 마지막으로 사용된 LLM 추적 (사이드바 표시용)
_last_provider: dict = {"name": None, "model": None}

# Blogger 라벨이 매 글마다 자유형 태그로 흩어지는 것을 막기 위한 고정 카테고리 목록
CATEGORIES = ["이슈/뉴스", "건강정보", "라이프", "테크/IT", "엔터테인먼트"]


# ── 실제 검색 결과 조사 (키워드 기반 지어내기 방지) ──────────────────────────

def _search_naver_news(keyword: str, limit: int = 4) -> list[dict]:
    """
    네이버 뉴스 검색 결과에서 실제 기사 제목·요약을 가져와 콘텐츠 생성의 근거로 사용.
    네이버 검색 결과는 sds-comps-text-type-headline1(제목)/-body1(요약) 클래스로
    구성되며(2026-07 기준 확인), 문서 순서상 1:1로 짝지어 나타난다.
    """
    try:
        resp = _requests.get(
            "https://search.naver.com/search.naver",
            params={"where": "news", "query": keyword, "sort": "1"},
            headers=_SEARCH_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        soup = _BeautifulSoup(resp.text, "html.parser")

        titles = [t.get_text(strip=True) for t in soup.select(".sds-comps-text-type-headline1")]
        summaries = [s.get_text(strip=True) for s in soup.select(".sds-comps-text-type-body1")]

        results = []
        for i, title in enumerate(titles[:limit]):
            if not title:
                continue
            results.append({
                "title": title,
                "summary": summaries[i] if i < len(summaries) else "",
            })
        return results
    except Exception:
        return []


def research_keywords(keywords: list[str], per_keyword: int = 3) -> list[dict]:
    """키워드별 실제 뉴스 검색 결과 수집 (실패해도 빈 리스트 반환, 생성 자체는 계속 진행됨)"""
    research = []
    for kw in keywords[:3]:
        for item in _search_naver_news(kw, limit=per_keyword):
            research.append({"keyword": kw, **item})
    return research


def _format_research_block(research: list[dict]) -> str:
    """프롬프트에 삽입할 실제 검색 결과 텍스트 블록 생성"""
    if not research:
        return ""

    lines = [f"- [{r['keyword']}] {r['title']}" + (f" — {r['summary']}" if r.get("summary") else "")
             for r in research]
    return (
        "\n\n# 실제 검색 결과 (반드시 아래 사실에 기반해서 작성하세요. 지어내지 마세요)\n"
        + "\n".join(lines)
        + "\n\n위 검색 결과와 모순되는 내용, 확인되지 않은 추측을 사실처럼 서술하지 마세요. "
        "검색 결과가 부족한 부분은 일반적이고 안전한 서술로 채우세요."
    )


# ── LLM 상태 확인 ──────────────────────────────────────────────────────────────

def check_llm_status() -> dict:
    """vLLM · Claude 사용 가능 여부 반환"""
    vllm_ok = _check_vllm_available()
    claude_ok = bool(os.getenv("ANTHROPIC_API_KEY", ""))
    return {
        "vllm_available":   vllm_ok,
        "vllm_addr":        os.getenv("LLM_ADDR", ""),
        "claude_available": claude_ok,
        "any_available":    vllm_ok or claude_ok,
        "last_provider":    _last_provider.get("name"),
        "last_model":       _last_provider.get("model"),
    }


def _check_vllm_available() -> bool:
    """vLLM 서버 ping (5초 타임아웃)"""
    addr = os.getenv("LLM_ADDR", "")
    if not addr:
        return False
    try:
        base = addr.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        resp = _requests.get(f"{base}/models", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


# ── 개별 LLM 호출 ──────────────────────────────────────────────────────────────

def _call_vllm(prompt: str) -> str:
    from openai import OpenAI
    base_url = os.getenv("LLM_ADDR", "").rstrip("/")
    if not base_url.endswith("/v1"):
        base_url += "/v1"
    api_key = os.getenv("LLM_API_KEY", "EMPTY")
    model   = os.getenv("LLM_MODEL", "google/gemma-4-31b-it")

    client = OpenAI(base_url=base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4096,
    )
    _last_provider["name"]  = "vLLM"
    _last_provider["model"] = model
    return resp.choices[0].message.content.strip()


def _call_claude(prompt: str) -> str:
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    model  = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    _last_provider["name"]  = "Claude"
    _last_provider["model"] = model
    return msg.content[0].text.strip()


# ── 통합 생성 함수 (vLLM → Claude 자동 fallback) ─────────────────────────────

def _generate(prompt: str) -> str:
    """
    vLLM 시도 → 실패 시 Claude로 자동 fallback.
    둘 다 실패하면 RuntimeError 발생.
    """
    vllm_addr = os.getenv("LLM_ADDR", "")

    # 1) vLLM 시도
    if vllm_addr:
        try:
            return _call_vllm(prompt)
        except Exception as e:
            print(f"⚠️ vLLM 실패 ({e}) → Claude fallback 시도")

    # 2) Claude fallback
    if os.getenv("ANTHROPIC_API_KEY", ""):
        try:
            return _call_claude(prompt)
        except Exception as e:
            raise RuntimeError(f"Claude fallback도 실패: {e}")

    # 3) 둘 다 불가
    raise RuntimeError(
        "사용 가능한 LLM이 없습니다. "
        "설정에서 vLLM 서버 주소 또는 Anthropic API 키를 입력해주세요."
    )


def _parse_json(text: str, fallback):
    """텍스트에서 JSON 추출 (마크다운 코드블록 포함)"""
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    for pattern in [r"\[.*\]", r"\{.*\}"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return fallback


# ── 공개 API ──────────────────────────────────────────────────────────────────

def suggest_topics(keywords: list[str], count: int = 5) -> list[dict]:
    kw_str = ", ".join(keywords)
    research_block = _format_research_block(research_keywords(keywords))
    prompt = f"""당신은 SEO 전문가이자 블로그 콘텐츠 전략가입니다.
다음은 오늘의 트렌드 키워드 목록입니다:
{kw_str}
{research_block}

위 키워드를 분석하여 블로그 포스팅에 적합한 주제 {count}개를 추천해주세요.

이 블로그는 신생/소규모 블로그라 대형 언론사·경쟁 블로그가 이미 상위를
차지한 키워드로는 검색 노출이 사실상 불가능합니다. 아래 기준을 반드시
지켜주세요:
- 키워드 자체(인물명, 사건명 등 한 단어짜리 대표 키워드)를 그대로 주제로
  삼지 마세요. 경쟁이 너무 치열해 순위에 노출될 가능성이 낮습니다.
- 대신 그 키워드에서 파생되는 더 구체적인 하위 주제·각도를 고르세요
  (배경 설명, 특정 궁금증 해소, 비교·정리, 실용 정보 등). 검색량이
  극단적으로 높은 대표 키워드보다, 검색될 가능성은 있으면서 경쟁은
  상대적으로 낮은 지점을 우선하세요.
- 반대로 너무 좁아서 아무도 검색하지 않을 주제도 피하세요. "검색될 가능성"과
  "경쟁 강도" 둘 다 균형 있게 고려해서 고르세요.

반드시 아래 JSON 형식으로만 답하세요 (마크다운 없이 순수 JSON 배열):
[
  {{
    "topic": "주제명",
    "title": "블로그 포스팅 제목 (클릭율 높은 형태)",
    "keywords": ["핵심키워드1", "핵심키워드2", "핵심키워드3"],
    "reason": "이 주제를 선택한 이유 — 검색 가능성과 경쟁 강도를 함께 언급 (1-2문장)"
  }}
]"""

    text = _generate(prompt)
    return _parse_json(text, [])


def generate_blog_post(title: str, keywords: list[str], tone: str = "정보전달") -> dict:
    kw_str = ", ".join(keywords)
    category_list = ", ".join(CATEGORIES)
    research_block = _format_research_block(research_keywords([title] + keywords))
    prompt = f"""# Role
당신은 10년 이상 블로그를 운영해온 실제 한국인 블로거입니다. 구글 SEO, 애드센스 정책, 그리고 구글의 AI 콘텐츠 감지 시스템을 누구보다 잘 알고 있습니다.

# Task
아래 키워드로 구글 애드센스 승인에 최적화된, 사람이 직접 쓴 것처럼 자연스러운 블로그 포스트를 작성하세요.

# 핵심 원칙: 인간적인 글쓰기 (AI 감지 회피)
아래 규칙을 반드시 지켜서 AI가 작성한 것처럼 보이지 않게 하세요:

1. **문장 길이 불규칙하게**: 짧은 문장(5-10자)과 긴 문장(30-50자)을 뒤섞으세요.
   예: "솔직히 말씀드릴게요. 저도 처음엔 반신반의했거든요. 근데 직접 써보니까 생각보다 훨씬 효과적이었어요."

2. **실제 경험담 구체적으로 삽입**: 막연한 "경험"이 아닌 구체적 숫자·날짜·상황 포함.
   예: "작년 11월에 직접 써봤는데, 3주 만에 방문자가 37% 늘었어요."

3. **구어체·감탄사 자연스럽게 사용**: "사실", "솔직히", "그런데 말이죠", "어, 근데", "아, 그리고" 등

4. **수사적 질문 포함**: "여러분은 어떻게 생각하세요?", "이거 알고 계셨나요?" 등

5. **AI 금지 표현 피하기**:
   - ❌ "~에 대해 알아보겠습니다" → ✅ "~얘기 한번 해볼게요"
   - ❌ "첫째, 둘째, 셋째" 나열 → ✅ 자연스러운 흐름으로 전환
   - ❌ "결론적으로" 단독 사용 → ✅ 자연스러운 마무리
   - ❌ 모든 단락 비슷한 길이 → ✅ 길이 다양하게

6. **E-E-A-T 강화**: H2·H3 구조, 전문 용어 적절히 사용, 출처 언급 스타일("~에 따르면" 등)

7. **감정·의견 적극 표현**: "개인적으로 이게 제일 중요하다고 생각해요", "솔직히 이건 좀 아쉬운 부분이에요"

8. **태그**: 핵심 키워드 + 연관 검색어 포함, 5~8개 생성
9. **카테고리**: 아래 목록 중 이 글에 가장 맞는 것 정확히 하나만 선택 — {category_list}

# Output Format
- [도입부]: 공감 유발 일화나 질문으로 시작 (<p> 태그, 2~3문단, 구어체) → {{IMAGE_1}} 삽입
- [본문]: H2(3~4개) + H3 활용, 각 H2 아래 2~4문단
  * 첫 번째 H2 뒤 → {{IMAGE_2}} 삽입
  * 마지막 H2 뒤 → {{IMAGE_3}} 삽입
- [결론]: <div class="conclusion">으로 감싸기, 댓글 유도 또는 행동 촉구
- <strong>으로 핵심 문장 강조 (3~5개)
- 전체 HTML 2500자 이상

⚠️ {{IMAGE_1}}, {{IMAGE_2}}, {{IMAGE_3}} 세 개 반드시 포함

# 작성 정보
- 핵심 키워드: {kw_str}
- 제목: {title}
- 톤: {tone}
- 타겟: 일반 한국인 인터넷 독자
{research_block}

반드시 아래 JSON 형식으로만 답하세요 (마크다운 없이 순수 JSON):
{{
  "title": "클릭을 유도하는 제목 (핵심 키워드 포함, 숫자나 의문형 활용)",
  "content_html": "HTML 본문 전체",
  "meta_description": "검색 결과 설명 (150자 이내, 핵심 키워드 포함, 구어체)",
  "category": "위 카테고리 목록 중 정확히 하나",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"],
  "image_prompts": [
    "IMAGE_1 이미지 설명 (영어, 50자 이내)",
    "IMAGE_2 이미지 설명 (영어, 50자 이내)",
    "IMAGE_3 이미지 설명 (영어, 50자 이내)"
  ]
}}"""

    text   = _generate(prompt)
    result = _parse_json(text, None)

    if result and isinstance(result, dict):
        if "image_prompts" not in result or len(result.get("image_prompts", [])) < 3:
            result["image_prompts"] = result.get("image_prompts", []) + [
                f"Blog illustration about {keywords[i % len(keywords)]}"
                for i in range(3 - len(result.get("image_prompts", [])))
            ]
        result["content_html"] = _ensure_image_placeholders(result.get("content_html", ""))
        result["content_html"] = _apply_readability_styles(result["content_html"])
        category = result.get("category", "")
        if category not in CATEGORIES:
            category = CATEGORIES[0]
        result["category"] = category
        result["tags"] = [category] + [t for t in result.get("tags", []) if t != category]
        return result

    return {
        "title":            title,
        "content_html":     f"<p>{text}</p>",
        "meta_description": "",
        "category":         CATEGORIES[0],
        "tags":             [CATEGORIES[0]] + keywords[:5],
        "image_prompts":    ["blog post illustration", "relevant image", "article image"],
    }


def _ensure_image_placeholders(html: str) -> str:
    placeholder_count = len(re.findall(r"\{IMAGE_\d+\}", html))
    if placeholder_count >= 3:
        return html

    needed = 3 - placeholder_count
    h2_positions = [m.end() for m in re.finditer(r"</h2>", html)]

    if h2_positions:
        if "{IMAGE_1}" not in html:
            html = html[:h2_positions[0]] + "{IMAGE_1}" + html[h2_positions[0]:]
            needed -= 1
        if "{IMAGE_2}" not in html and needed > 0:
            h2_positions = [m.end() for m in re.finditer(r"</h2>", html)]
            if len(h2_positions) > 1:
                html = html[:h2_positions[1]] + "{IMAGE_2}" + html[h2_positions[1]:]
                needed -= 1
        if "{IMAGE_3}" not in html and needed > 0:
            h2_positions = [m.end() for m in re.finditer(r"</h2>", html)]
            last_pos = max(h2_positions[-1] if h2_positions else 0, html.rfind("</div>"))
            if last_pos > 0:
                html = html[:last_pos] + "{IMAGE_3}" + html[last_pos:]
    else:
        conclusion_pos = html.find('<div class="conclusion">')
        base_pos = conclusion_pos if conclusion_pos > 0 else len(html)
        for i in range(1, needed + 1):
            ph = f"{{IMAGE_{i}}}"
            if ph not in html:
                html = html[:base_pos] + ph + html[base_pos:]
                base_pos += len(ph)

    return html


def _apply_readability_styles(html: str) -> str:
    """
    문단이 너무 촘촘해 보이지 않도록 글자크기·자간·줄간격·문단 여백을 인라인 스타일로 적용.
    Naver 발행은 문단 텍스트만 추출해 타이핑하므로 이 스타일과 무관하고,
    풀 HTML을 그대로 쓰는 Blogger 발행에만 실제로 반영된다.
    """
    soup = _BeautifulSoup(html, "html.parser")

    styles = {
        "p":          "font-size:16px; line-height:1.9; letter-spacing:-0.2px; margin:0 0 1.3em 0;",
        "li":         "font-size:16px; line-height:1.9; letter-spacing:-0.2px; margin:0 0 0.6em 0;",
        "h2":         "line-height:1.5; letter-spacing:-0.3px; margin:1.8em 0 0.8em 0;",
        "h3":         "line-height:1.5; letter-spacing:-0.3px; margin:1.4em 0 0.6em 0;",
        "blockquote": "font-size:16px; line-height:1.8; letter-spacing:-0.2px; margin:1em 0;",
    }
    for tag_name, style in styles.items():
        for tag in soup.find_all(tag_name):
            existing = (tag.get("style") or "").strip()
            if existing and not existing.endswith(";"):
                existing += ";"
            tag["style"] = existing + style

    return str(soup)


def refine_content(content_html: str, instruction: str) -> str:
    prompt = f"""다음 블로그 본문을 아래 지시사항에 따라 수정해주세요.
수정된 HTML 본문만 반환하세요 (JSON 없이, 마크다운 없이).

지시사항: {instruction}

원본 본문:
{content_html}"""
    return _generate(prompt)
