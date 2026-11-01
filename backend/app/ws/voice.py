"""WebSocket `/ws/voice`：真双工语音代理（火山豆包实时语音模型 3.0，Seeduplex）。

浏览器 ↔ 本服务 ↔ 火山实时语音。密钥只在服务端，浏览器只收发音频。

浏览器 → 服务端：
  二进制帧            PCM16 / 16kHz / 单声道，20ms 一片（640 字节）
  {"type":"cancel"}   打断（丢弃后续 2 秒残留下行音频）
  {"type":"mute"}     暂停上行
  {"type":"unmute"}   恢复
  {"type":"finish"}   结束

服务端 → 浏览器：
  {"type":"ready","session_id":…,"sample_rate":24000,"sample_format":"s16le"}
  {"type":"event","event":…,"payload":{…}}
  {"type":"error","code":…,"message":…}
  二进制帧            学生语音 pcm_s16le / 24kHz / 单声道

转写落库：
  学生侧取 response.output_text.done（text 字段）。
  老师侧不依赖火山——Seeduplex 端到端模型在双工下不吐可靠老师文字（实测只出
  单字/回声）。改为本地 FunASR 独立旁听同一路麦克风上行音频，按本地 VAD 切句
  转写落库（治本）。火山链路完全不变，FunASR 对火山零影响。
  仅在未配置 FunASR 时，才回退用火山的 input_audio_transcription.completed。
"""
import asyncio
import contextlib
import json
import struct
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..core.cases import case_to_role
from ..core.role import DEFAULT_ROLE, build_system_prompt
from ..providers import build_asr
from ..providers.realtime_volc import (
    EVT_ASR_COMPLETED,
    EVT_ERROR,
    EVT_TEXT_DONE,
    RealtimeVolcSession,
)
from ..repo import case_to_dict, get_case, save_turn

router = APIRouter()
settings = get_settings()

SILENCE_FRAME = b"\x00" * 640   # 20ms @ 16k/16bit
FRAME_MS = 20
KEEPALIVE_GAP = 0.08            # 静音 80ms 以上就补静音帧，防止断麦判停

# —— 老师侧本地转写（治本）——
# 浏览器上行麦克风音频照常发给火山（学生回应全靠它），这里只是「旁听」同一路
# 音频、按本地 VAD 切句后丢给 FunASR，落库为 teacher turn。对火山链路零影响。
SPEECH_RMS = 0.02          # 16k/16bit 帧能量阈值，超过即认为在说话
SILENCE_COMMIT_S = 0.6     # 老师停嘴 0.6s 认为一句说完，切段送 FunASR
STUDENT_TAIL_S = 0.4       # 学生音频停 0.4s 后认为学生说完，恢复采集老师侧
MIN_SEG_BYTES = 8000       # 少于 0.25s 的片段不送 FunASR（过滤杂音/按键声）
BARGE_IN_CAPTURE_S = 3.0   # 打断后最多连续采集老师侧 3 秒（防误触发回声被一直采）


def _frame_rms(data: bytes) -> float:
    """16kHz/16bit 单声道 PCM 帧的均方根能量（0~1），用于本地 VAD。"""
    n = len(data) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", data)
    total = 0.0
    for v in samples:
        f = v / 32768.0
        total += f * f
    return (total / n) ** 0.5


def _session_config(role=DEFAULT_ROLE) -> dict:
    # 情绪基调：低落、疲惫、不想多说，压住端到端模型默认偏积极的朗读腔
    mood = (
        "你的语气是低落、疲惫、没什么力气的。语速偏慢，句尾不要上扬，"
        "不要用轻快或活泼的语调。回答很短，经常停顿，偶尔叹气，"
        "不太想谈，但被温和地追问时会一点点松动。"
    )
    return {
        "model": settings.volc_model,
        "instructions": build_system_prompt(role) + "\n\n【情绪与语气】" + mood,
        "audio": {
            "input": {"format": {"type": "pcm", "rate": 16000}},
            "output": {
                "format": {"type": "pcm_s16le", "rate": 24000},
                "voice": settings.volc_speaker,
                "speed": -8,
            },
        },
    }


@router.websocket("/ws/voice")
async def ws_voice(ws: WebSocket) -> None:
    await ws.accept()

    if not settings.realtime_configured:
        await ws.send_json({
            "type": "error",
            "code": "realtime_not_configured",
            "message": "未配置火山实时语音（VOLC_APP_ID / VOLC_API_KEY）",
        })
        await ws.close()
        return

    asr = build_asr()  # funasr 未启用时为 None，老师侧回退火山自带转写

    role = DEFAULT_ROLE
    case_id = ws.query_params.get("case_id")
    if case_id:
        case = await get_case(case_id)
        if case:
            role = case_to_role(case_to_dict(case))
    scenario = role.scenario

    session = RealtimeVolcSession()
    try:
        try:
            info = await session.open(_session_config(role))
        except Exception as exc:  # noqa: BLE001
            await ws.send_json({
                "type": "error",
                "code": "realtime_unavailable",
                "message": f"实时语音连接失败：{type(exc).__name__}",
            })
            await ws.close()
            return

        await ws.send_json({
            "type": "ready",
            "session_id": info["session_id"],
            "sample_rate": 24000,
            "sample_format": "s16le",
            "log_id": session.log_id,
        })

        muted = False
        last_audio = 0.0
        cancelled_until = 0.0
        barge_in_until = 0.0     # 打断后老师侧采集窗口截止时间（0=未激活）

        # 老师侧本地转写状态（与火山链路完全解耦）
        student_playing = False
        last_downstream_audio = 0.0
        teacher_buf = bytearray()
        teacher_speaking = False
        teacher_silence_since = None

        stop = asyncio.Event()

        async def flush_teacher(seg: bytes) -> None:
            """把一段老师音频送 FunASR 转写落库；失败不影响主链路。"""
            if asr is None or len(seg) < MIN_SEG_BYTES:
                return
            try:
                text = (await asr.transcribe(seg, "pcm16")).strip()
            except Exception:  # noqa: BLE001
                return
            if text:
                await save_turn(info["session_id"], scenario, "teacher", text, mode="realtime")
                print(f"[teacher-turn] saved ({len(seg)}B): {text}", flush=True)

        async def pump_upstream() -> None:
            nonlocal muted, last_audio, cancelled_until, barge_in_until
            nonlocal teacher_buf, teacher_speaking, teacher_silence_since
            while not stop.is_set():
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    stop.set()
                    return
                data = msg.get("bytes")
                if data:
                    if not muted:
                        last_audio = time.monotonic()
                        await session.send_audio(data)  # 火山主链路，保持不变

                    # 旁听老师侧：学生播报期间上行是喇叭回声，跳过不采集；
                    # 但打断后（cancel）进入采集窗口，老师插话那半句也收进来
                    if asr is not None and not muted and (
                        not student_playing or time.monotonic() < barge_in_until
                    ):
                        now = time.monotonic()
                        if _frame_rms(data) > SPEECH_RMS:
                            teacher_speaking = True
                            teacher_silence_since = None
                            teacher_buf += data
                        elif teacher_speaking:
                            teacher_buf += data  # 保留句尾静音，供 FunASR 判定结束
                            if teacher_silence_since is None:
                                teacher_silence_since = now
                            elif now - teacher_silence_since >= SILENCE_COMMIT_S:
                                seg = bytes(teacher_buf)
                                teacher_buf.clear()
                                teacher_speaking = False
                                teacher_silence_since = None
                                barge_in_until = 0.0
                                asyncio.create_task(flush_teacher(seg))
                    continue
                text = msg.get("text")
                if not text:
                    continue
                try:
                    ctl = json.loads(text)
                except Exception:  # noqa: BLE001
                    continue
                if ctl.get("type") == "cancel":
                    cancelled_until = time.monotonic() + 2.0
                    barge_in_until = time.monotonic() + BARGE_IN_CAPTURE_S
                    print("[barge-in] detected: capture window open", flush=True)
                elif ctl.get("type") == "mute":
                    muted = True
                elif ctl.get("type") == "unmute":
                    muted = False
                elif ctl.get("type") == "finish":
                    stop.set()
                    return

        async def pump_downstream() -> None:
            nonlocal student_playing, last_downstream_audio
            nonlocal teacher_buf, teacher_speaking, teacher_silence_since, barge_in_until
            async for frame in session.messages():
                if stop.is_set():
                    return
                if frame.get("_audio"):
                    if time.monotonic() < cancelled_until:
                        continue
                    await ws.send_bytes(frame["_audio"])
                    # 学生一开口，老师这句就算说完了 → 立即切段落库，避免乱序
                    if teacher_speaking:
                        seg = bytes(teacher_buf)
                        teacher_buf.clear()
                        teacher_speaking = False
                        teacher_silence_since = None
                        barge_in_until = 0.0
                        asyncio.create_task(flush_teacher(seg))
                    student_playing = True
                    last_downstream_audio = time.monotonic()
                    continue

                etype = frame.get("type")
                if etype == EVT_ERROR:
                    await ws.send_json({
                        "type": "error",
                        "code": "upstream_error",
                        "message": json.dumps(frame.get("error"), ensure_ascii=False),
                    })
                    continue

                # 转写落库：与 /ws/chat 共用 turns 表
                if etype == EVT_ASR_COMPLETED:
                    # 仅在没配 FunASR 时才用火山自带转写兜底（断句碎、常为空）
                    if asr is None:
                        text = (frame.get("transcript") or "").strip()
                        if text:
                            await save_turn(info["session_id"], scenario, "teacher", text, mode="realtime")
                elif etype == EVT_TEXT_DONE:
                    text = (frame.get("text") or "").strip()
                    if text:
                        await save_turn(info["session_id"], scenario, "student", text, mode="realtime")

                await ws.send_json({"type": "event", "event": etype, "payload": frame})

        async def keepalive() -> None:
            nonlocal student_playing
            while not stop.is_set():
                await asyncio.sleep(FRAME_MS / 1000)
                if muted or time.monotonic() - last_audio > KEEPALIVE_GAP:
                    try:
                        await session.send_audio(SILENCE_FRAME)
                    except Exception:  # noqa: BLE001
                        return
                # 学生播报结束后（尾音过了 0.4s），恢复采集老师侧
                if student_playing and time.monotonic() - last_downstream_audio > STUDENT_TAIL_S:
                    student_playing = False

        tasks = [
            asyncio.create_task(pump_upstream()),
            asyncio.create_task(pump_downstream()),
            asyncio.create_task(keepalive()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        stop.set()

        # 收尾：把还没切段的老师侧残片落库（直接 await，确保写完再关连接）
        if teacher_buf and teacher_speaking:
            await flush_teacher(bytes(teacher_buf))
            teacher_buf.clear()
            teacher_speaking = False

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
        with contextlib.suppress(Exception):
            await ws.close()
