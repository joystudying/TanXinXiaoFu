"""FunASR（阿里开源，中文识别强，可自部署）。

这里只是 HTTP 客户端，真正的识别服务由 backend/services/funasr_server.py
独立进程提供（要 Python 3.10/3.11 环境，别和主后端混用）。

trust_env=False：本地直连，不走系统代理，否则 127.0.0.1 会被代理拦成 502。
"""
import base64

import httpx

from ..config import settings
from .base import ASRProvider, ProviderError, ProviderTimeout


class FunASRProvider(ASRProvider):
    def __init__(self, service_url: str | None = None):
        self.service_url = service_url or settings.funasr_service_url

    async def transcribe(self, audio: bytes, audio_format: str = "pcm16") -> str:
        if not audio:
            return ""
        try:
            async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
                resp = await client.post(
                    self.service_url,
                    json={
                        "audio_b64": base64.b64encode(audio).decode(),
                        "format": audio_format,
                    },
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("asr_timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"asr_unreachable: {exc}") from exc

        if resp.status_code != 200:
            raise ProviderError(f"asr_http_{resp.status_code}")
        return resp.json().get("text", "")
