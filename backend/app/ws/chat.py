"""WebSocket 端点：文字 / 语音对练。

协议（JSON）：
  客户端 -> 服务端：
    {"type":"text","text":"..."}
    {"type":"audio","audio_b64":"...","audio_format":"pcm16"}
    {"type":"reset"}
  服务端 -> 客户端：
    {"type":"ready","session_id":"...","student_name":"...","scenario":"..."}
    {"type":"reply","text":"...","emotion":null,"audio_b64":"...","audio_format":"mp3","note":null}
"""
import base64
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.orchestrator import Orchestrator
from ..core.role import DEFAULT_ROLE
from ..providers import build_providers
from ..repo import save_turn

router = APIRouter()

llm, asr, tts = build_providers()
orchestrator = Orchestrator(llm, asr, tts)

@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()
    session_id = uuid.uuid4().hex
    state = orchestrator.new_session(session_id, DEFAULT_ROLE)
    await ws.send_json(
        {
            "type": "ready",
            "session_id": session_id,
            "student_name": DEFAULT_ROLE.name,
            "scenario": DEFAULT_ROLE.scenario,
        }
    )

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "text":
                text = msg.get("text", "")
                out = await orchestrator.handle_turn(state, text=text)
                if text.strip():
                    await save_turn(session_id, state.role.scenario, "teacher", text)

            elif mtype == "audio":
                audio = base64.b64decode(msg.get("audio_b64", ""))
                fmt = msg.get("audio_format", "pcm16")
                out = await orchestrator.handle_turn(state, audio=audio, audio_format=fmt)
                teacher_text = out.get("input_text", "")
                if teacher_text.strip():
                    await save_turn(session_id, state.role.scenario, "teacher", teacher_text)

            elif mtype == "reset":
                session_id = uuid.uuid4().hex
                state = orchestrator.new_session(session_id, DEFAULT_ROLE)
                out = {
                    "text": "",
                    "emotion": None,
                    "audio_b64": None,
                    "audio_format": None,
                    "note": "已重置会话",
                }
                await ws.send_json({"type": "reset", "session_id": session_id})
                continue

            else:
                out = {
                    "text": "",
                    "emotion": None,
                    "audio_b64": None,
                    "audio_format": None,
                    "note": f"未知消息类型：{mtype}",
                }

            if out.get("text"):
                await save_turn(
                    session_id, state.role.scenario, "student", out["text"], out.get("emotion")
                )

            await ws.send_json({"type": "reply", **out})

    except WebSocketDisconnect:
        pass
