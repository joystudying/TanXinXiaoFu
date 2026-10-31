"""FunASR（阿里开源，中文识别强，可自部署）。

这里只是一个 HTTP 客户端，真正的识别服务由 `backend/services/funasr_server.py`
独立进程提供（建议跑在 Python 3.10/3.11 环境）。解耦后主后端不受 FunASR 依赖影响。
"""
import base64

import httpx

from .base import ASRProvider


class FunASRProvider(ASRProvider):
    def __init__(self, service_url: str):
        self.service_url = service_url

    async def transcribe(self, audio: bytes, audio_format: str = "pcm16") -> str:
        # trust_env=False：本地服务直连，不走系统代理（否则 127.0.0.1 会被代理拦截返回 502）
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            resp = await client.post(
                self.service_url,
                json={
                    "audio_b64": base64.b64encode(audio).decode(),
                    "format": audio_format,
                },
            )
            resp.raise_for_status()
            return resp.json().get("text", "")
