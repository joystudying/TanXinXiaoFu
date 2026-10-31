"""语音合成接口（M3.3）：把朗读托管给微软在线神经音色。

为什么加这个依赖：浏览器自带 speechSynthesis 只有传统合成音色，听感机械，
且不同机器音色差异极大（有的机器一个中文音色都没有）。edge-tts 走的是
Edge 浏览器"大声朗读"那条在线神经音色通道，音质接近真人，且不需要密钥。

注意：edge-tts 属于非官方封装，通道变化可能失效。失效时前端会自动回退到
浏览器 speechSynthesis，不会让对话卡死。
"""
from collections import OrderedDict

import edge_tts
from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import errors

router = APIRouter()

# 学生角色用年轻男声；预留女声给后续女角色案例
VOICE_MAP = {
    "student_male": "zh-CN-YunxiNeural",     # 云希：年轻男声，适合大学生
    "student_female": "zh-CN-XiaoyiNeural",  # 晓伊：年轻女声
    "student_teen": "zh-CN-YunxiaNeural",    # 云夏：少年音
}
DEFAULT_VOICE = "student_male"

MAX_TEXT_LEN = 500
CACHE_LIMIT = 200
_cache: OrderedDict[tuple[str, str, str], bytes] = OrderedDict()


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LEN)
    voice: str = DEFAULT_VOICE
    rate: str = "+4%"


def _voice_name(key: str) -> str:
    return VOICE_MAP.get(key, VOICE_MAP[DEFAULT_VOICE])


def _cache_put(k: tuple[str, str, str], data: bytes) -> None:
    _cache[k] = data
    _cache.move_to_end(k)
    while len(_cache) > CACHE_LIMIT:
        _cache.popitem(last=False)


@router.post("/api/tts")
async def synthesize(payload: TtsIn):
    text = payload.text.strip()
    if not text:
        raise errors.ApiError(422, "bad_request", "文本不能为空", False)

    voice = _voice_name(payload.voice)
    key = (text, voice, payload.rate)

    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return Response(
            content=cached,
            media_type="audio/mpeg",
            headers={"X-Tts-Cache": "hit", "Cache-Control": "no-store"},
        )

    async def gen():
        buf = bytearray()
        try:
            communicate = edge_tts.Communicate(text, voice, rate=payload.rate)
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    buf.extend(chunk["data"])
                    yield chunk["data"]
        except Exception:  # noqa: BLE001 —— 断流时结束即可，前端会回退
            return
        if buf:
            _cache_put(key, bytes(buf))

    return StreamingResponse(
        gen(),
        media_type="audio/mpeg",
        headers={"X-Tts-Cache": "miss", "Cache-Control": "no-store"},
    )


@router.get("/api/tts/voices")
async def voices():
    """给设置页/调试用：当前可用的角色音色映射。"""
    return {"voices": VOICE_MAP, "default": DEFAULT_VOICE}
