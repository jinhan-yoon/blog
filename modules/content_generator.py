"""vLLM (OpenAI 호환) 을 활용한 블로그 콘텐츠 생성 모듈"""

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
    제목과 키워드를 받아 SEO 최적화된 HTML 블로그 본문 생성

    Args:
        tone: "정보전달" | "친근한" | "전문적" | "뉴스형"

    Returns:
        {"title": str, "content_html": str, "meta_description": str, "tags": [str], "image_prompts": [str]}
    """
    kw_str = ", ".join(keywords)
    prompt = f"""당신은 SEO 최적화 전문 블로그 작가입니다.
다음 조건으로 블로그 포스팅을 작성해주세요:

제목: {title}
핵심 키워드: {kw_str}
톤앤매너: {tone}

요구사항:
1. HTML 형식으로 작성 (본문만, <html>/<body> 태그 없이)
2. <h2> 소제목 3-4개 포함
3. <h3> 세부 소제목 포함
4. <p> 태그로 단락 구분
5. <strong> 태그로 핵심 문장 강조
6. 각 <h2> 섹션 뒤에 이미지 삽입 위치를 {{IMAGE_1}}, {{IMAGE_2}}, {{IMAGE_3}} 플레이스홀더로 표시
7. 전체 길이: 1500자 이상
8. SEO를 위해 키워드를 자연스럽게 본문에 녹여낼 것
9. 마지막에 <div class="conclusion"> 결론 섹션 추가

반드시 아래 JSON 형식으로만 답하세요 (마크다운 없이 순수 JSON):
{{
  "title": "최종 제목",
  "content_html": "HTML 본문 전체",
  "meta_description": "검색 결과에 표시될 설명 (150자 이내)",
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
        return result

    return {
        "title": title,
        "content_html": f"<p>{text}</p>",
        "meta_description": "",
        "tags": keywords[:5],
        "image_prompts": ["blog post illustration", "relevant image", "article image"],
    }


def refine_content(content_html: str, instruction: str) -> str:
    """기존 본문을 사용자 지시에 따라 수정"""
    prompt = f"""다음 블로그 본문을 아래 지시사항에 따라 수정해주세요.
수정된 HTML 본문만 반환하세요 (JSON 없이, 마크다운 없이).

지시사항: {instruction}

원본 본문:
{content_html}"""

    return _generate(prompt)
