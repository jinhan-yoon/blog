"""vLLM (OpenAI 호환) 을 활용한 블로그 콘텐츠 생성 모듈"""
from __future__ import annotations

import os
import json
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def _get_client() -> OpenAI:
    base_url = os.getenv("LLM_ADDR", "http://210.127.59.40:8000/v1")
    # /v1 경로가 없으면 자동 추가
    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"
    api_key = os.getenv("LLM_API_KEY", "EMPTY")
    return OpenAI(base_url=base_url, api_key=api_key)


def _get_model() -> str:
    return os.getenv("LLM_MODEL", "google/gemma-4-31b-it")


def _generate(prompt: str) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=_get_model(),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4096,
    )
    return response.choices[0].message.content.strip()


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


def suggest_topics(keywords: list[str], count: int = 5) -> list[dict]:
    """
    트렌드 키워드 목록을 기반으로 블로그 주제 추천

    Returns:
        [{"topic": str, "title": str, "keywords": [str], "reason": str}]
    """
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
    """
    제목과 키워드를 받아 E-E-A-T 기반 SEO 최적화 HTML 블로그 본문 생성

    Args:
        tone: "정보전달" | "친근한" | "전문적" | "뉴스형"

    Returns:
        {"title": str, "content_html": str, "meta_description": str, "tags": [str], "image_prompts": [str]}
    """
    kw_str = ", ".join(keywords)
    prompt = f"""# Role
당신은 10년 차 이상의 전문 블로거이자, 구글 SEO 및 애드센스 정책을 완벽하게 이해하고 있는 '콘텐츠 마스터'입니다.

# Task
아래 핵심 키워드를 바탕으로, 독자에게 유용한 정보를 제공하고 동시에 블로그 수익(애드센스)을 극대화할 수 있는 고품질의 블로그 포스트를 작성해 주세요.

# Writing Guidelines (글쓰기 원칙)
1. E-E-A-T(경험, 전문성, 권위성, 신뢰성)를 최우선으로 반영하세요. 정보만 나열하지 말고, 반드시 '나의 실제 경험'이나 '개인적인 의견/인사이트'를 2~3문단 이상 자연스럽게 추가하세요.
2. 구글 SEO에 맞게 H2, H3 태그를 활용하여 구조화하고, 문단은 가독성 좋게 2~3줄 단위로 짧게 나누어 쓰세요.
3. 핵심 키워드는 제목, 서론, 결론, 그리고 본문 내에 자연스럽게 5~7회 반복 배치하되, 어색하지 않아야 합니다.
4. 독자의 공감을 이끌어내는 친근하고 전문적인 어조(해요체/하십시오체 혼용, 톤: {tone})를 사용하세요.
5. 글의 마지막에는 독자의 댓글을 유도하거나 추가 행동을 촉구하는 실용적인 요약 및 결론(Wrap-up)을 작성하세요.

# Output Format
- [도입부]: 문제 제기 및 호기심 유발 (<p> 태그로 2~3문단) → {{IMAGE_1}} 삽입
- [본문]: H2, H3 소제목을 활용한 핵심 정보 및 개인 의견 전개 (H2 3~4개)
  * 첫 번째 H2 뒤에 {{IMAGE_2}} 삽입
  * 마지막 H2 뒤에 {{IMAGE_3}} 삽입
- [결론]: 본문 요약 및 실용적인 조언, 마무리 (<div class="conclusion">으로 감싸기)
- <strong> 태그로 핵심 문장 강조
- 전체 HTML 길이: 2000자 이상
- ⚠️ 반드시 {{IMAGE_1}}, {{IMAGE_2}}, {{IMAGE_3}} 세 개 모두 포함해야 합니다

# Information
- 핵심 키워드: {kw_str}
- 제목: {title}
- 타겟 독자: 일반 인터넷 독자
- 개인 의견/경험: 키워드에 관한 전문가적 인사이트와 실용적인 정보 제공

반드시 아래 JSON 형식으로만 답하세요 (마크다운 없이 순수 JSON):
{{
  "title": "클릭을 유도하는 매력적인 최종 제목 (핵심 키워드 포함)",
  "content_html": "HTML 본문 전체 (도입부+본문+결론)",
  "meta_description": "검색 결과에 표시될 설명 (150자 이내, 핵심 키워드 포함)",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"],
  "image_prompts": [
    "IMAGE_1에 들어갈 이미지 설명 (영어, 50자 이내)",
    "IMAGE_2에 들어갈 이미지 설명 (영어, 50자 이내)",
    "IMAGE_3에 들어갈 이미지 설명 (영어, 50자 이내)"
  ]
}}"""

    text = _generate(prompt)
    result = _parse_json(text, None)

    if result and isinstance(result, dict):
        # 이미지 프롬프트가 3개 미만이면 기본값으로 채우기
        if "image_prompts" not in result or len(result.get("image_prompts", [])) < 3:
            result["image_prompts"] = result.get("image_prompts", []) + [
                f"Blog illustration about {keywords[i % len(keywords)]}"
                for i in range(3 - len(result.get("image_prompts", [])))
            ]

        # HTML에 이미지 플레이스홀더가 부족하면 자동으로 추가
        content_html = result.get("content_html", "")
        result["content_html"] = _ensure_image_placeholders(content_html)

        return result

    return {
        "title": title,
        "content_html": f"<p>{text}</p>",
        "meta_description": "",
        "tags": keywords[:5],
        "image_prompts": ["blog post illustration", "relevant image", "article image"],
    }


def _ensure_image_placeholders(html: str) -> str:
    """
    HTML에 이미지 플레이스홀더가 부족하면 자동으로 추가
    최소 3개의 플레이스홀더를 보장
    """
    # 현재 플레이스홀더 개수 확인 (단일 중괄호 {IMAGE_N} 형식)
    import re
    placeholder_count = len(re.findall(r"\{IMAGE_\d+\}", html))

    if placeholder_count >= 3:
        return html

    # 부족한 플레이스홀더 개수
    needed = 3 - placeholder_count

    # H2 태그를 기준으로 플레이스홀더 삽입
    h2_positions = [m.end() for m in re.finditer(r"</h2>", html)]

    if h2_positions:
        if "{IMAGE_1}" not in html and h2_positions:
            html = html[:h2_positions[0]] + "{IMAGE_1}" + html[h2_positions[0]:]
            needed -= 1

        if "{IMAGE_2}" not in html and len(h2_positions) > 1 and needed > 0:
            # h2_positions가 삽입으로 인해 변경되었을 수 있으므로 재검색
            h2_positions = [m.end() for m in re.finditer(r"</h2>", html)]
            html = html[:h2_positions[1]] + "{IMAGE_2}" + html[h2_positions[1]:]
            needed -= 1

        if "{IMAGE_3}" not in html and needed > 0:
            h2_positions = [m.end() for m in re.finditer(r"</h2>", html)]
            last_h2_pos = h2_positions[-1] if h2_positions else 0
            last_div_pos = html.rfind("</div>")
            insert_pos = max(last_h2_pos, last_div_pos)
            if insert_pos > 0:
                html = html[:insert_pos] + "{IMAGE_3}" + html[insert_pos:]
    else:
        # H2가 없으면 결론 div 앞 또는 끝에 균등 삽입
        conclusion_pos = html.find('<div class="conclusion">')
        base_pos = conclusion_pos if conclusion_pos > 0 else len(html)
        for i in range(1, needed + 1):
            placeholder = f"{{IMAGE_{i}}}"
            if placeholder not in html:
                html = html[:base_pos] + placeholder + html[base_pos:]
                base_pos += len(placeholder)

    return html


def refine_content(content_html: str, instruction: str) -> str:
    """기존 본문을 사용자 지시에 따라 수정"""
    prompt = f"""다음 블로그 본문을 아래 지시사항에 따라 수정해주세요.
수정된 HTML 본문만 반환하세요 (JSON 없이, 마크다운 없이).

지시사항: {instruction}

원본 본문:
{content_html}"""

    return _generate(prompt)
