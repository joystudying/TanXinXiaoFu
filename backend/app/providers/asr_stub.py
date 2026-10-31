"""未接入识别服务时的占位实现：不报错，返回空串，让上层走"没听清"分支。"""
from .base import ASRProvider


class StubASRProvider(ASRProvider):
    async def transcribe(self, audio: bytes, audio_format: str = "pcm16") -> str:
        return ""
