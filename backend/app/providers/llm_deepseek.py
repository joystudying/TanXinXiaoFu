"""DeepSeek（OpenAI 兼容协议）。

DeepSeek 的 API 兼容 OpenAI 协议，所以底层用 openai SDK + base_url 指向
api.deepseek.com。将来换成任何 OpenAI 兼容服务（通义/GLM 等）只需改配置。
"""
import httpx
from openai import AsyncOpenAI

from .base import LLMProvider, LLMResult


class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.model = model
        # trust_env=False：直连 DeepSeek，不读 Windows 系统代理。
        # （代理工具关闭后会残留「127.0.0.1:10090」这类死代理，导致连接被拒）
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.AsyncClient(
                trust_env=False, timeout=httpx.Timeout(600.0, connect=5.0)
            ),
        )

    async def chat(self, messages: list[dict], **kwargs) -> LLMResult:
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.8,
            stream=False,
        )
        text = (resp.choices[0].message.content or "").strip()
        return LLMResult(text=text, emotion=None)
