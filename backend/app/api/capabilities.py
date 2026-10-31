"""能力探测接口：告诉前端"这台服务器现在能提供什么"。

前端据此选择降级档位，避免在弱网/弱机上硬上重功能。
设计文档 8.6 / 19.3 的"分级降级"落地点。
"""
from fastapi import APIRouter

from ..config import settings
from .health import VERSION

router = APIRouter()


@router.get("/api/capabilities")
async def capabilities() -> dict:
    llm_ready = settings.model_configured
    asr_server = settings.asr_provider not in ("stub", "")
    tts_server = settings.tts_provider not in ("stub", "")
    realtime = settings.realtime_configured

    # 档位从高到低，前端按顺序挑第一个可用的
    tiers = []
    if realtime:
        tiers.append({
            "id": "realtime",
            "label": "真双工实时语音",
            "detail": "端到端语音模型，边说边听、可随时打断；音频只在服务端与云端之间流动",
        })
    if llm_ready and asr_server and tts_server:
        tiers.append({
            "id": "full",
            "label": "全服务端语音",
            "detail": "服务端识别 + 模型 + 合成，客户端只收音放音，弱机也能跑",
        })
    if llm_ready and tts_server:
        tiers.append({
            "id": "hybrid",
            "label": "浏览器识别 + 服务端合成",
            "detail": "识别用浏览器自带，合成走服务端，需要联网",
        })
    if llm_ready:
        tiers.append({
            "id": "lite",
            "label": "文字为主",
            "detail": "识别和朗读都用浏览器自带能力，不依赖服务端语音",
        })
    tiers.append({
        "id": "text",
        "label": "纯文字",
        "detail": "只做文字对练，任何环境都能用",
    })

    return {
        "version": VERSION,
        "llm": {"provider": settings.llm_provider, "ready": llm_ready},
        "asr": {"provider": settings.asr_provider, "server_side": asr_server},
        "tts": {"provider": settings.tts_provider, "server_side": tts_server},
        "realtime": {"ready": realtime, "provider": "volcengine" if realtime else None},
        "transport": {"ws": True, "rest": True, "voice_ws": realtime},
        "tiers": tiers,
    }
