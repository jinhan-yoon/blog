"""이미지 생성 모듈 (DALL-E 3 / Pollinations.ai / Claude+Pollinations)"""
from __future__ import annotations

import os
import re
import requests
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()


def generate_image_url(prompt: str, provider: str | None = None) -> str:
    """
    프롬프트로 이미지 URL 생성

    Args:
        prompt: 이미지 설명 (영어 권장)
        provider: "dalle" | "pollinations" | "claude" (None이면 환경변수 IMAGE_PROVIDER 사용)

    Returns:
        이미지 URL 문자열
    """
    if provider is None:
        provider = os.getenv("IMAGE_PROVIDER", "pollinations")

    if provider == "dalle":
        return _generate_dalle(prompt)
    elif provider == "claude":
        return _generate_claude(prompt)
    else:
        return _generate_pollinations(prompt)


def _generate_dalle(prompt: str) -> str:
    """OpenAI DALL-E 3로 이미지 생성"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    response = client.images.generate(
        model="dall-e-3",
        prompt=f"Blog post illustration: {prompt}. Professional, clean, modern style.",
        size="1024x576",
        quality="standard",
        n=1,
    )
    return response.data[0].url


def _generate_claude(prompt: str) -> str:
    """
    Claude로 이미지 프롬프트를 강화한 뒤 Pollinations.ai로 이미지 생성.
    Claude는 텍스트 전용이므로 프롬프트 최적화에 활용하고 실제 렌더링은 Pollinations에 위임.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are an expert image prompt engineer. "
                    "Enhance the following image description into a highly detailed, "
                    "vivid, and professional image generation prompt. "
                    "Include style, lighting, mood, composition, and color palette. "
                    "Return ONLY the enhanced prompt text, no explanation, no quotes.\n\n"
                    f"Original: {prompt}"
                ),
            }
        ],
    )
    enhanced_prompt = message.content[0].text.strip()
    return _generate_pollinations(enhanced_prompt)


def _generate_pollinations(prompt: str) -> str:
    """
    Pollinations.ai (무료, 키 불필요)로 이미지 URL 생성
    실제 이미지를 다운로드하지 않고 URL만 반환
    """
    safe_prompt = quote(f"blog post illustration: {prompt}, professional, clean, modern")
    seed = abs(hash(prompt)) % 100000
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=576&seed={seed}&nologo=true"
    return url


def generate_images_for_post(image_prompts: list[str], provider: str | None = None) -> list[str]:
    """
    포스팅에 필요한 이미지 URL 목록 생성

    Returns:
        이미지 URL 리스트 (image_prompts와 동일 순서)
    """
    urls = []
    for prompt in image_prompts:
        try:
            url = generate_image_url(prompt, provider)
            urls.append(url)
        except Exception as e:
            # 실패 시 플레이스홀더 이미지 사용
            urls.append(f"https://via.placeholder.com/1024x576?text={quote(prompt[:50])}")
    return urls


def insert_images_into_html(content_html: str, image_urls: list[str]) -> str:
    """
    HTML 본문의 {IMAGE_N} 플레이스홀더를 실제 이미지 태그로 교체

    Returns:
        이미지가 삽입된 HTML
    """
    result = content_html
    for i, url in enumerate(image_urls, 1):
        img_tag = (
            f'<div style="text-align:center; margin: 20px 0;">'
            f'<img src="{url}" alt="블로그 이미지 {i}" '
            f'style="max-width:100%; height:auto; border-radius:8px; '
            f'box-shadow: 0 2px 8px rgba(0,0,0,0.15);" />'
            f'</div>'
        )
        result = result.replace(f"{{IMAGE_{i}}}", img_tag)

    # 남은 플레이스홀더 제거
    result = re.sub(r"\{IMAGE_\d+\}", "", result)
    return result
