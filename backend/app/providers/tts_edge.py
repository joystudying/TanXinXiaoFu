"""edge-tts：免费、无需 GPU 的神经音色，当前 TTS 的默认实现。

将来有 GPU 就换 IndexTTS2 / CosyVoice，新增一个实现类即可，接口不变。
"""
import edge_tts

from ..config import settings
from .base import ProviderError, TTSProvider, TTSResult


class EdgeTTSProvider(TTSProvider):
    def __init__(self, voice: str | None = None, rate: str | None = None):
        self.voice = voice or settings.tts_voice
        self.rate = rate or settings.tts_rate

    async def synthesize(self, text: str) -> TTSResult:
        if not text.strip():
            return TTSResult(audio=b"", format="mp3")
        buffer = bytearray()
        try:
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    buffer.extend(chunk["data"])
        except Exception as exc:  # noqa: BLE001 —— 合成失败不该让整轮对话崩
            raise ProviderError(f"tts_failed: {exc}") from exc
        return TTSResult(audio=bytes(buffer), format="mp3")
