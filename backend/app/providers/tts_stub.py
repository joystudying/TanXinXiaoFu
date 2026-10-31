"""占位 TTS：不发声，仅返回文字。"""
from .base import TTSProvider, TTSResult


class StubTTSProvider(TTSProvider):
    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        return TTSResult(audio=b"", format="none")
