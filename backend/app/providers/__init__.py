"""Provider 工厂：根据配置装配 ASR / LLM / TTS 实现。"""
from ..config import get_settings
from .asr_funasr import FunASRProvider
from .asr_stub import StubASRProvider
from .base import ASRProvider, LLMProvider, TTSProvider
from .llm_deepseek import DeepSeekProvider
from .tts_edge import EdgeTTSProvider
from .tts_stub import StubTTSProvider


def build_providers() -> tuple[LLMProvider, ASRProvider, TTSProvider]:
    s = get_settings()

    if s.llm_provider == "deepseek":
        if not s.deepseek_api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在 backend/.env 中配置")
        llm: LLMProvider = DeepSeekProvider(
            s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model
        )
    else:
        raise RuntimeError(f"未知 LLM_PROVIDER: {s.llm_provider}")

    if s.asr_provider == "funasr":
        asr: ASRProvider = FunASRProvider(s.funasr_service_url)
    else:
        asr = StubASRProvider()

    if s.tts_provider == "edge":
        tts: TTSProvider = EdgeTTSProvider(s.tts_voice, s.tts_rate, s.tts_pitch)
    else:
        tts = StubTTSProvider()

    return llm, asr, tts
