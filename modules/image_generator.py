"""이미지 생성 모듈 - 다중 프로바이더 지원"""
from __future__ import annotations

import os
import re
import time
import requests
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── 개별 프로바이더 ──────────────────────────────────────────────────────────
# 모든 프로바이더는 AI로 신규 생성된 이미지만 반환 — 저작권자가 있는 실사진(스톡 사진)은 쓰지 않음

def _pollinations_url(prompt: str) -> str:
    safe = quote(f"blog post illustration: {prompt}, professional, clean, modern style")
    seed = abs(hash(prompt)) % 100000
    return f"https://image.pollinations.ai/prompt/{safe}?width=1024&height=576&seed={seed}&nologo=true&enhance=true"


def _generate_pollinations(prompt: str) -> bytes:
    """Pollinations.ai - 무료, API 키 불필요, AI 신규 생성"""
    resp = requests.get(_pollinations_url(prompt), timeout=45, headers=_HEADERS)
    resp.raise_for_status()
    return resp.content


def _generate_huggingface(prompt: str) -> bytes:
    """Hugging Face Inference API - Stable Diffusion XL (무료 토큰 필요)"""
    api_key = os.getenv("HUGGINGFACE_TOKEN", "")
    if not api_key:
        raise ValueError("HUGGINGFACE_TOKEN이 설정되지 않았습니다.")

    model = os.getenv("HF_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
    url = f"https://api-inference.huggingface.co/models/{model}"
    enhanced = f"blog post illustration, {prompt}, professional photography, clean modern style, high quality"

    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"inputs": enhanced, "parameters": {"width": 1024, "height": 576}},
        timeout=60,
    )
    resp.raise_for_status()
    if resp.headers.get("Content-Type", "").startswith("image/"):
        return resp.content
    raise ValueError(f"HuggingFace 응답 오류: {resp.text[:200]}")


def _generate_dalle(prompt: str) -> bytes:
    """OpenAI DALL-E 3 - 유료, 고품질"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.images.generate(
        model="dall-e-3",
        prompt=f"Blog post illustration: {prompt}. Professional, clean, modern style.",
        size="1024x1024",
        quality="standard",
        n=1,
    )
    img_url = response.data[0].url
    resp = requests.get(img_url, timeout=30, headers=_HEADERS)
    resp.raise_for_status()
    return resp.content


def _generate_claude_pollinations(prompt: str) -> bytes:
    """Claude로 프롬프트 강화 후 Pollinations 렌더링"""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                "Enhance this image prompt for an AI image generator. "
                "Add style, lighting, mood, composition details. "
                "Return ONLY the enhanced prompt, no explanation.\n\n"
                f"Original: {prompt}"
            ),
        }],
    )
    enhanced = msg.content[0].text.strip()
    return _generate_pollinations(enhanced)


# ── 프로바이더 선택 ──────────────────────────────────────────────────────────

PROVIDER_MAP = {
    "pollinations": _generate_pollinations,
    "huggingface":  _generate_huggingface,
    "dalle":        _generate_dalle,
    "claude":       _generate_claude_pollinations,
}

# 키 없이 항상 시도 가능한 pollinations만 자동 fallback으로 사용 (실사진 스톡 소스는 제외)
PROVIDER_FALLBACK_ORDER = ["pollinations"]


def generate_image_bytes(prompt: str, provider: str | None = None) -> tuple[bytes, str]:
    """
    단일 이미지를 bytes로 생성.
    실패 시 fallback 프로바이더 순서대로 재시도.

    Returns:
        (bytes, 사용된_프로바이더)
    """
    if provider is None:
        provider = os.getenv("IMAGE_PROVIDER", "pollinations")

    # 지정 프로바이더 시도
    if provider in PROVIDER_MAP:
        try:
            data = PROVIDER_MAP[provider](prompt)
            return data, provider
        except Exception as e:
            print(f"⚠️ [{provider}] 실패: {e}")

    # fallback 순서로 재시도
    for fallback in PROVIDER_FALLBACK_ORDER:
        if fallback == provider:
            continue
        try:
            data = PROVIDER_MAP[fallback](prompt)
            print(f"✅ fallback [{fallback}] 성공")
            return data, fallback
        except Exception as e:
            print(f"⚠️ [{fallback}] fallback 실패: {e}")

    raise RuntimeError(f"모든 이미지 프로바이더 실패 (prompt: {prompt[:40]})")


def generate_images_for_post(
    image_prompts: list[str],
    provider: str | None = None,
    log_callback=None,
) -> list[dict]:
    """
    포스팅용 이미지 3개 생성.

    Returns:
        [{"bytes": bytes|None, "provider": str, "url": str, "prompt": str, "error": str|None}, ...]
        url: Blogger HTML에 삽입할 외부 URL (base64 대신 사용)
    """
    prompts = (image_prompts or ["blog post illustration", "relevant image", "article image"])[:3]
    while len(prompts) < 3:
        prompts.append(f"Blog illustration #{len(prompts)+1}")

    results = []
    for i, prompt in enumerate(prompts):
        msg = f"이미지 {i+1}/3 생성 중: {prompt[:40]}..."
        if log_callback:
            log_callback(msg)
        print(msg)

        try:
            data, used_provider = generate_image_bytes(prompt, provider)
            # Blogger에 삽입할 외부 URL 생성 (base64 차단 회피)
            url = get_image_url(prompt)
            results.append({
                "bytes": data,
                "provider": used_provider,
                "url": url,
                "prompt": prompt,
                "error": None,
            })
            done_msg = f"✅ 이미지 {i+1} 완료 ({used_provider}, {len(data)//1024}KB)"
            print(done_msg)
            if log_callback:
                log_callback(done_msg)
        except Exception as e:
            err_msg = f"❌ 이미지 {i+1} 실패: {e}"
            print(err_msg)
            if log_callback:
                log_callback(err_msg)
            results.append({
                "bytes": None,
                "provider": None,
                "url": _pollinations_url(prompt),
                "prompt": prompt,
                "error": str(e),
            })

    return results


def get_image_url(prompt: str) -> str:
    """
    HTML 삽입용 URL 반환. dalle/huggingface는 생성된 바이트를 올려둘 고정 URL이 없으므로,
    저작권 걱정 없는 pollinations의 동일 프롬프트 URL로 대체한다 (실사진 스톡 소스는 쓰지 않음).
    """
    return _pollinations_url(prompt)


def insert_images_into_html(content_html: str, image_data: list[dict]) -> str:
    """
    HTML 본문의 {IMAGE_N} 플레이스홀더를 이미지 태그로 교체.
    Blogger는 base64 data: URL을 차단하므로 외부 URL을 우선 사용.
    image_data: generate_images_for_post()의 반환값
    """
    result = content_html
    for i, item in enumerate(image_data, 1):
        # 외부 URL 우선 (Blogger 호환) → base64 → pollinations fallback (실사진 스톡 소스는 쓰지 않음)
        if item.get("url"):
            src = item["url"]
        elif item.get("bytes"):
            import base64
            b64 = base64.b64encode(item["bytes"]).decode()
            src = f"data:image/jpeg;base64,{b64}"
        else:
            src = _pollinations_url(item.get("prompt", "blog post illustration"))

        img_tag = (
            f'<div style="text-align:center; margin:20px 0;">'
            f'<img src="{src}" alt="블로그 이미지 {i}" '
            f'style="max-width:100%; height:auto; border-radius:8px; '
            f'box-shadow:0 2px 8px rgba(0,0,0,0.15);" />'
            f'</div>'
        )
        result = result.replace(f"{{IMAGE_{i}}}", img_tag)

    result = re.sub(r"\{IMAGE_\d+\}", "", result)
    return result
