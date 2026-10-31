"""不发声的占位实现：只回文字，用于没装 edge-tts 或不想出声的场景。"""
from .base import TTSProvider, TTSResult


class StubTTSProvider(TTSProvider):
    async def synthesize(self, text: str) -> TTSResult:
        return TTSResult(audio=b"", format="mp3")
