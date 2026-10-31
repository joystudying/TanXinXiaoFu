"""占位 ASR：未接入真实服务时使用，语音输入会返回空文字。"""
from .base import ASRProvider


class StubASRProvider(ASRProvider):
    async def transcribe(self, audio: bytes, audio_format: str = "pcm16") -> str:
        return ""
