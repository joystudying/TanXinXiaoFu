"""edge-tts：免费、无需 GPU、无需注册，作为 TTS 的过渡实现。

等有 GPU 后再换成 IndexTTS2 / CosyVoice（新增一个实现类即可，接口不变）。
"""
import edge_tts

from .base import TTSProvider, TTSResult


class EdgeTTSProvider(TTSProvider):
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural", rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        communicate = edge_tts.Communicate(
            text, self.voice, rate=self.rate, pitch=self.pitch
        )
        buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.extend(chunk["data"])
        return TTSResult(audio=bytes(buffer), format="mp3")
