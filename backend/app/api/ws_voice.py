"""WebSocket /ws/voice：真双工语音代理。

浏览器 ↔ 本服务 ↔ 火山实时语音。
密钥只在服务端；浏览器只收发音频。

协议（浏览器侧，JSON 控制 + 二进制音频）：
  浏览器 → 服务端
    二进制帧          PCM16 / 16kHz / 单声道，20ms 一片（640 字节）
    {"type":"mute"}   暂停发音频（服务端自动补静音保活）
    {"type":"unmute"} 恢复
    {"type":"finish"} 结束本次通话
  服务端 → 浏览器
    {"type":"ready","session_id":…,"dialog_id":…,"sample_rate":24000}
    {"type":"event","event":N,"payload":{…}}   识別/文本/状态等事件
    {"type":"error","code":…,"message":…}
    二进制帧          学生语音 float32 / 24kHz / 单声道（Web Audio 原生格式）
"""
import asyncio
import contextlib
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..db import repo
from ..providers.realtime_volc import RealtimeVolcSession
from ..services import persona

router = APIRouter()

DEFAULT_CASE_ID = "c_academic_01"
SILENCE_FRAME = b"\x00" * 640      # 20ms @ 16k/16bit
FRAME_MS = 20
KEEPALIVE_GAP = 0.08               # 超过这个时间没收到真实音频，就补静音


def _session_config(case) -> dict:
    import json

    public = json.loads(case["public_json"])

    # 情绪基调：这个学生处在低落、疲惫、不想多说的状态。
    # 之前用默认音色 + 中性指令，模型会读得偏积极，所以要显式压下去。
    mood = (
        "你的语气是低落、疲惫、没什么力气的。语速偏慢，句尾不要上扬，"
        "不要用轻快或活泼的语调。回答很短，经常停顿，偶尔叹气，"
        "不太想谈，但被温和地追问时会一点点松动。"
    )

    return {
        "tts": {
            # 云舟 2.0：S2S 主打男声，支持指令遵循
            "speaker": "zh_male_m191_uranus_bigtts",
            "speech_rate": -8,
            "audio_config": {"channel": 1, "format": "pcm", "sample_rate": 24000},
        },
        "dialog": {
            "bot_name": public.get("alias", "小陈"),
            "system_role": persona.build_system(case) + "\n\n【情绪与语气】" + mood,
            "speaking_style": mood,
            "extra": {"strict_audit": False},
        },
    }


@router.websocket("/ws/voice")
async def ws_voice(ws: WebSocket) -> None:
    await ws.accept()

    if not settings.realtime_configured:
        await ws.send_json({
            "type": "error", "code": "realtime_not_configured",
            "message": "未配置火山实时语音（VOLC_APP_ID / VOLC_ACCESS_TOKEN）",
        })
        await ws.close()
        return

    db = repo.connect()
    session = RealtimeVolcSession()
    try:
        case = repo.get_case(db, DEFAULT_CASE_ID)
        if case is None:
            await ws.send_json({"type": "error", "code": "case_not_found", "message": "案例不存在"})
            await ws.close()
            return

        try:
            info = await session.open(_session_config(case))
        except Exception as exc:  # noqa: BLE001
            await ws.send_json({
                "type": "error", "code": "realtime_unavailable",
                "message": f"实时语音连接失败：{type(exc).__name__}",
            })
            await ws.close()
            return

        await ws.send_json({
            "type": "ready",
            "session_id": info["session_id"],
            "dialog_id": info.get("dialog_id"),
            "sample_rate": 24000,
            # 下行音频是 32 位浮点，浏览器可直接喂给 AudioBuffer，不要当 int16 读
            "sample_format": "float32",
            "log_id": session.log_id,
        })

        muted = False
        last_audio = 0.0
        stop = asyncio.Event()

        async def pump_upstream() -> None:
            """浏览器 → 火山"""
            nonlocal muted, last_audio
            while not stop.is_set():
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    stop.set()
                    return
                data = msg.get("bytes")
                if data:
                    if not muted:
                        last_audio = time.monotonic()
                        await session.send_audio(data)
                    continue
                text = msg.get("text")
                if not text:
                    continue
                import json as _json
                try:
                    ctl = _json.loads(text)
                except Exception:  # noqa: BLE001
                    continue
                if ctl.get("type") == "mute":
                    muted = True
                elif ctl.get("type") == "unmute":
                    muted = False
                elif ctl.get("type") == "finish":
                    stop.set()
                    return

        async def pump_downstream() -> None:
            """火山 → 浏览器"""
            async for frame in session.messages():
                if stop.is_set():
                    return
                if frame.audio:
                    await ws.send_bytes(frame.audio)
                elif frame.error:
                    await ws.send_json({"type": "error", "code": "upstream_error",
                                        "message": frame.error})
                else:
                    await ws.send_json({"type": "event", "event": frame.event,
                                        "payload": frame.payload or {}})

        async def keepalive() -> None:
            """按 20ms 节奏补静音，避免服务端因收不到音频而超时。"""
            while not stop.is_set():
                await asyncio.sleep(FRAME_MS / 1000)
                if muted or time.monotonic() - last_audio > KEEPALIVE_GAP:
                    try:
                        await session.send_audio(SILENCE_FRAME)
                    except Exception:  # noqa: BLE001
                        return

        tasks = [
            asyncio.create_task(pump_upstream()),
            asyncio.create_task(pump_downstream()),
            asyncio.create_task(keepalive()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        stop.set()
        for t in pending:
            t.cancel()
        for t in pending:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        for t in done:
            with contextlib.suppress(WebSocketDisconnect, Exception):
                t.result()

    finally:
        await session.close()
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass
        with contextlib.suppress(Exception):
            await ws.close()
