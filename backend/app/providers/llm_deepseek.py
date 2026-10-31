"""DeepSeek（OpenAI 兼容协议），用 httpx 直连。

保留我们原来的重试策略：超时 / 429 / 5xx 重试 2 次，4xx 立即失败。
没有引入 openai SDK——项目里只允许 model.py 这一个 HTTP 出口，换成 Provider 后
这条边界仍然成立（服务层 → providers → HTTP）。
"""
import asyncio

import httpx

from ..config import settings
from .base import LLMProvider, LLMResult, ProviderError, ProviderRejected, ProviderTimeout


class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.deepseek_api_key
        self.base_url = (base_url or settings.model_base_url).rstrip("/")
        self.model = model or settings.model_name

    async def chat(self, messages: list[dict], *, json_mode: bool = False) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": settings.temperature,
            "max_tokens": settings.model_max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last: Exception | None = None
        for attempt in range(3):  # 1 次 + 2 次重试
            try:
                async with httpx.AsyncClient(timeout=settings.model_timeout_s) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                if resp.status_code == 429 or resp.status_code >= 500:
                    last = ProviderError(f"http_{resp.status_code}")
                elif 400 <= resp.status_code < 500:
                    raise ProviderRejected(f"http_{resp.status_code}")
                else:
                    try:
                        data = resp.json()
                        text = data["choices"][0]["message"]["content"]
                    except (ValueError, KeyError, IndexError) as exc:
                        raise ProviderError(f"bad_response: {exc}") from exc
                    return LLMResult(text=text, usage=data.get("usage") or {})
            except httpx.TimeoutException:
                last = ProviderTimeout("timeout")
            except httpx.HTTPError as exc:
                last = ProviderError(str(exc))

            if attempt < 2:
                await asyncio.sleep(0.5 * (2 ** attempt))

        raise last or ProviderError("unknown")
