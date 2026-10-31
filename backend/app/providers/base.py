"""可插拔 Provider 接口（合并自合作仓库 joystudying/TanXinXiaoFu）。

每个环节（ASR / LLM / TTS）只面向接口编程，具体厂商在实现类里切换，
换厂商只改 .env，不动业务代码。

异常也用同一套，避免上层同时处理多套错误类型。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ProviderError(Exception):
    """调用失败（可重试）。"""


class ProviderTimeout(ProviderError):
    """超时。"""


class ProviderRejected(ProviderError):
    """4xx（密钥失效、参数错）——重试没有意义。"""


class ProviderBadJson(ProviderError):
    """要求 JSON 输出但解析失败。"""


@dataclass
class LLMResult:
    text: str
    usage: dict = field(default_factory=dict)
    # 学生情绪标签，后续给 IndexTTS2 的情感音色用；当前留空
    emotion: str | None = None


@dataclass
class TTSResult:
    audio: bytes
    format: str = "mp3"


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], *, json_mode: bool = False) -> LLMResult:
        """带上下文的对话 → 学生回复。"""


class ASRProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, audio_format: str = "pcm16") -> str:
        """音频 → 文字。"""


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> TTSResult:
        """文字 → 语音。"""
