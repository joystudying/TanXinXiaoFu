"""Provider 工厂：根据配置装配 ASR / LLM / TTS / Evaluator 实现。"""
from ..config import get_settings
from .asr_funasr import FunASRProvider
from .asr_stub import StubASRProvider
from .base import ASRProvider, EvaluatorProvider, LLMProvider, TTSProvider
from .evaluator_deepseek import EvaluatorDeepSeek
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


def build_asr() -> ASRProvider | None:
    """只构建 ASR（供实时链路旁听转写用，不依赖 LLM/TTS 的密钥）。

    funasr 未启用时返回 None，调用方自行回退（如火山自带转写）。
    """
    s = get_settings()
    if s.asr_provider == "funasr":
        return FunASRProvider(s.funasr_service_url)
    return None


def build_evaluator() -> EvaluatorProvider:
    s = get_settings()

    if s.evaluator_provider == "deepseek":
        if not s.deepseek_api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY，无法构建评价模型")
        return EvaluatorDeepSeek(
            s.deepseek_api_key, s.deepseek_base_url, s.evaluator_model
        )
    raise RuntimeError(f"未知 EVALUATOR_PROVIDER: {s.evaluator_provider}")
