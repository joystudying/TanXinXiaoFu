"""Provider 工厂：按 .env 装配 ASR / LLM / TTS（合并自合作仓库）。

换厂商只改配置：
  LLM_PROVIDER=deepseek
  ASR_PROVIDER=stub | funasr
  TTS_PROVIDER=edge | stub
"""
from ..config import settings
from .asr_funasr import FunASRProvider
from .asr_stub import StubASRProvider
from .base import ASRProvider, LLMProvider, TTSProvider
from .llm_deepseek import DeepSeekProvider
from .tts_edge import EdgeTTSProvider
from .tts_stub import StubTTSProvider

_llm: LLMProvider | None = None
_asr: ASRProvider | None = None
_tts: TTSProvider | None = None


def get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        if settings.llm_provider != "deepseek":
            raise RuntimeError(f"未知 LLM_PROVIDER: {settings.llm_provider}")
        _llm = DeepSeekProvider()
    return _llm


def get_asr() -> ASRProvider:
    global _asr
    if _asr is None:
        if settings.asr_provider == "funasr":
            _asr = FunASRProvider()
        else:
            _asr = StubASRProvider()
    return _asr


def get_tts() -> TTSProvider:
    global _tts
    if _tts is None:
        if settings.tts_provider == "edge":
            _tts = EdgeTTSProvider()
        else:
            _tts = StubTTSProvider()
    return _tts


def reset_providers() -> None:
    """单测用：清掉缓存，便于换配置重装。"""
    global _llm, _asr, _tts
    _llm = _asr = _tts = None
