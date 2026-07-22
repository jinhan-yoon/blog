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


def generate_images_for_post(image_prompts: list[str], provider: str | None = None) -> list[bytes]:
    """
    포스팅에 필요한 이미지를 생성하고 bytes로 다운로드하여 반환.
    최소 3개 보장.

    Returns:
        이미지 bytes 리스트 (정확히 3개, 실패 시 None 포함 가능)
    """
    prompts = (image_prompts or ["blog post illustration", "relevant image", "article image"])[:3]
    while len(prompts) < 3:
        prompts.append(f"Blog illustration #{len(prompts)+1}")

    results = []
    for i, prompt in enumerate(prompts):
        try:
            url = generate_image_url(prompt, provider)
            # Pollinations는 요청 시 이미지를 생성하므로 timeout을 넉넉히 설정
            resp = requests.get(url, timeout=40, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code == 200 and resp.content:
                results.append(resp.content)
                print(f"✅ 이미지 {i+1} 다운로드 완료 ({len(resp.content)//1024}KB): {prompt[:50]}")
            else:
                results.append(None)
                print(f"⚠️ 이미지 {i+1} HTTP {resp.status_code}: {prompt[:50]}")
        except Exception as e:
            results.append(None)
            print(f"⚠️ 이미지 {i+1} 실패: {str(e)}")

    return results


def get_image_urls(image_prompts: list[str], provider: str | None = None) -> list[str]:
    """URL만 반환 (insert_images_into_html 용)"""
    prompts = (image_prompts or ["blog post illustration", "relevant image", "article image"])[:3]
    while len(prompts) < 3:
        prompts.append(f"Blog illustration #{len(prompts)+1}")
    return [generate_image_url(p, provider) for p in prompts]


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
