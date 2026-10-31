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
from ..core.role import RoleConfig
from ..providers import build_providers
from ..repo import save_turn

router = APIRouter()

llm, asr, tts = build_providers()
orchestrator = Orchestrator(llm, asr, tts)

# 默认学生角色（演示用）：隐藏背景只在此处、只在服务端
DEFAULT_ROLE = RoleConfig(
    name="小悦",
    age=16,
    scenario="情绪困扰",
    hidden_background=(
        "最近一次月考成绩下滑明显；父母近期经常争吵；"
        "不想让老师知道自己昨晚偷偷哭过。"
    ),
    speech_style=(
        "说话简短，常先否认自己有事（比如「没事」「我挺好的」），"
        "被温和追问几次后才会慢慢透露真实感受，偶尔沉默。"
    ),
    notes="该生近期上课走神、作业完成质量下降、与同学互动减少。",
    branches=["被问到成绩时情绪激动", "提到父母时沉默回避"],
)


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
