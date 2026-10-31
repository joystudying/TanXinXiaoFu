"""可插拔 Provider 接口。

每个环节（ASR / LLM / TTS）都只面向接口编程，具体厂商在实现类里切换，
对应文档「不依赖某一家模型或特定框架」的 Harness 约束。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    # 学生情绪标签，后续传给 IndexTTS2 的 8 维情绪向量；当前先留空
    emotion: str | None = None


@dataclass
class TTSResult:
    audio: bytes
    format: str = "mp3"


class ASRProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, audio_format: str = "pcm16") -> str:
        """音频 -> 文字。"""


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> LLMResult:
        """带上下文的对话 -> 学生回复。"""


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        """文字 -> 语音。"""
