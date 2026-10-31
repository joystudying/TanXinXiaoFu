"""WebSocket /ws/chat（合并自合作仓库）。

和 REST 的区别只有三点：
  1. 一条长连接走完整个会话，省掉每轮的握手；
  2. 音频直接在连接上传输（ASR 在服务端做），浏览器不需要自带识别；
  3. 一次往返把「学生文字 + 语音」一起带回去。

业务逻辑复用 services/turn_engine.py，与 /api/chat 完全同一套：
幂等、私设注入、泄漏检查、失败回滚、落库。

协议（JSON）：
  客户端 → 服务端
    {"type":"text","text":"..."}
    {"type":"audio","audio_b64":"...","audio_format":"pcm16"}
    {"type":"reset"}
  服务端 → 客户端
    {"type":"ready","session_id":"...","student_name":"...","scenario":"..."}
    {"type":"reply","text":"...","turn_no":N,"audio_b64":"...","audio_format":"mp3","degraded":false}
    {"type":"error","code":"...","message":"...","retryable":true}
"""
import base64
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import errors
from ..config import settings
from ..db import repo
from ..providers import get_asr, get_tts
from ..services import turn_engine

router = APIRouter()

DEFAULT_CASE_ID = "c_academic_01"
MAX_AUDIO_BYTES = 4 * 1024 * 1024   # 单次上传上限，防误传大文件撑爆内存


def _public_case(case) -> dict:
    import json
    return json.loads(case["public_json"])


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()

    db = repo.connect()
    try:
        case = repo.get_case(db, DEFAULT_CASE_ID)
        if case is None:
            await ws.send_json({"type": "error", "code": "case_not_found",
                                "message": "示例案例不存在", "retryable": False})
            await ws.close()
            return

        session = repo.create_session(
            db, case_id=case["id"], case_version=case["version"], prep_note=None
        )
        session_id = session["id"]
        public = _public_case(case)

        await ws.send_json({
            "type": "ready",
            "session_id": session_id,
            "student_name": public.get("alias", "小陈"),
            "scenario": public.get("concern", ""),
            "asr": settings.asr_provider,
            "tts": settings.tts_provider,
        })

        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")

            if mtype == "reset":
                session = repo.create_session(
                    db, case_id=case["id"], case_version=case["version"],
                    prep_note=None, prev_session_id=session_id,
                )
                session_id = session["id"]
                await ws.send_json({"type": "reset", "session_id": session_id})
                continue

            if mtype not in ("text", "audio"):
                await ws.send_json({"type": "error", "code": "bad_request",
                                    "message": f"未知消息类型：{mtype}", "retryable": False})
                continue

            text = (msg.get("text") or "").strip()

            if mtype == "audio":
                try:
                    audio = base64.b64decode(msg.get("audio_b64") or "")
                except Exception:  # noqa: BLE001
                    audio = b""
                if not audio:
                    await ws.send_json({"type": "error", "code": "bad_request",
                                        "message": "音频为空", "retryable": True})
                    continue
                if len(audio) > MAX_AUDIO_BYTES:
                    await ws.send_json({"type": "error", "code": "bad_request",
                                        "message": "音频太大", "retryable": False})
                    continue
                try:
                    text = (await get_asr().transcribe(
                        audio, msg.get("audio_format", "pcm16"))).strip()
                except Exception as exc:  # noqa: BLE001
                    await ws.send_json({"type": "error", "code": "asr_unavailable",
                                        "message": f"识别服务不可用：{exc}", "retryable": True})
                    continue
                if not text:
                    await ws.send_json({"type": "error", "code": "asr_no_speech",
                                        "message": "没听清，再说一次", "retryable": True})
                    continue

            try:
                result = await turn_engine.run_turn(
                    db,
                    session_id=session_id,
                    text=text,
                    idempotency_key=uuid.uuid4().hex,
                    source="voice" if mtype == "audio" else "text",
                )
            except errors.ApiError as exc:
                await ws.send_json({"type": "error", "code": exc.code,
                                    "message": exc.message, "retryable": exc.retryable})
                continue
            except Exception as exc:  # noqa: BLE001
                await ws.send_json({"type": "error", "code": "internal_error",
                                    "message": f"服务内部错误：{exc}", "retryable": True})
                continue

            audio_b64 = None
            audio_format = None
            try:
                tts = await get_tts().synthesize(result["reply_text"])
                if tts.audio:
                    audio_b64 = base64.b64encode(tts.audio).decode()
                    audio_format = tts.format
            except Exception:  # noqa: BLE001 —— 合成失败也要把文字送回去
                audio_b64 = None

            await ws.send_json({
                "type": "reply",
                "text": result["reply_text"],
                "turn_no": result["turn_no"],
                "degraded": result.get("degraded", False),
                "audio_b64": audio_b64,
                "audio_format": audio_format,
            })

    except WebSocketDisconnect:
        pass
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass
