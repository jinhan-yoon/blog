"""콘텐츠 생성 모듈 — vLLM 우선, 불가 시 Claude 자동 fallback"""
from __future__ import annotations

import os
import json
import re
import requests as _requests
from dotenv import load_dotenv

load_dotenv()

# 마지막으로 사용된 LLM 추적 (사이드바 표시용)
_last_provider: dict = {"name": None, "model": None}


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
    prompt = f"""당신은 SEO 전문가이자 블로그 콘텐츠 전략가입니다.
다음은 오늘의 트렌드 키워드 목록입니다:
{kw_str}

위 키워드를 분석하여 블로그 포스팅에 적합한 주제 {count}개를 추천해주세요.
각 주제는 검색량이 높고 독자의 관심을 끌 수 있어야 합니다.

반드시 아래 JSON 형식으로만 답하세요 (마크다운 없이 순수 JSON 배열):
[
  {{
    "topic": "주제명",
    "title": "블로그 포스팅 제목 (클릭율 높은 형태)",
    "keywords": ["핵심키워드1", "핵심키워드2", "핵심키워드3"],
    "reason": "이 주제를 선택한 이유 (1-2문장)"
  }}
]"""

    text = _generate(prompt)
    return _parse_json(text, [])


def generate_blog_post(title: str, keywords: list[str], tone: str = "정보전달") -> dict:
    kw_str = ", ".join(keywords)
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

8. **태그**: 핵심 키워드 + 연관 검색어 + 주제 카테고리 포함, 8~10개 생성

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

반드시 아래 JSON 형식으로만 답하세요 (마크다운 없이 순수 JSON):
{{
  "title": "클릭을 유도하는 제목 (핵심 키워드 포함, 숫자나 의문형 활용)",
  "content_html": "HTML 본문 전체",
  "meta_description": "검색 결과 설명 (150자 이내, 핵심 키워드 포함, 구어체)",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5", "태그6", "태그7", "태그8"],
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
        return result

    return {
        "title":            title,
        "content_html":     f"<p>{text}</p>",
        "meta_description": "",
        "tags":             keywords[:5],
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


def refine_content(content_html: str, instruction: str) -> str:
    prompt = f"""다음 블로그 본문을 아래 지시사항에 따라 수정해주세요.
수정된 HTML 본문만 반환하세요 (JSON 없이, 마크다운 없이).

지시사항: {instruction}

원본 본문:
{content_html}"""
    return _generate(prompt)
