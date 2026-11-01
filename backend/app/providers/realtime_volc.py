"""火山引擎「豆包实时语音模型 3.0」（Seeduplex）全双工端到端协议实现。

新版控制台鉴权：单一 API Key（X-Api-Key header）。与旧版二进制协议不同：
  - 旧版 /api/v3/realtime/dialogue：二进制帧 + 数字事件（旧鉴权，已下线）
  - 新版 /api/v3/duplex/realtime/dialogue：WebSocket 文本 JSON + 字符串事件

协议要点：
  - 一切走 JSON 文本帧，用 type 字段区分事件
  - session.create 建会话（session.model 固定 "1.2.6.0"）
  - 上行音频：input_audio_buffer.append（base64，PCM16 / 16kHz / 单声道）
  - 上行文本 / 开场：speech_text_buffer.commit
  - 下行音频：response.output_audio.delta（base64，pcm_s16le / 24kHz / 单声道）
  - 下行老师侧转写：conversation.item.input_audio_transcription.*
  - 下行学生侧文本：response.output_text.*

本模块只做协议，不碰数据库、不碰 HTTP（分层边界）。
"""
import base64
import json
import uuid

import websockets

from ..config import get_settings

settings = get_settings()

# 上行事件
EVT_SESSION_CREATE = "session.create"
EVT_SESSION_CLOSE = "session.close"
EVT_AUDIO_APPEND = "input_audio_buffer.append"
EVT_AUDIO_COMMIT = "input_audio_buffer.commit"
EVT_SPEECH_TEXT_COMMIT = "speech_text_buffer.commit"

# 下行事件
EVT_SESSION_CREATED = "session.created"
EVT_SESSION_CLOSED = "session.closed"
EVT_ASR_STARTED = "conversation.item.input_audio_transcription.started"
EVT_ASR_DELTA = "conversation.item.input_audio_transcription.delta"
EVT_ASR_COMPLETED = "conversation.item.input_audio_transcription.completed"
EVT_TEXT_DELTA = "response.output_text.delta"
EVT_TEXT_DONE = "response.output_text.done"
EVT_AUDIO_DELTA = "response.output_audio.delta"
EVT_AUDIO_DONE = "response.output_audio.done"
EVT_RESPONSE_DONE = "response.done"
EVT_ERROR = "error"


class RealtimeVolcSession:
    """一条到火山豆包实时语音模型 3.0 的连接。用法：

        sess = RealtimeVolcSession()
        await sess.open(session_config)      # session_config 是 session 对象（不含 type 包装）
        await sess.send_audio(pcm16_bytes)
        await sess.say_hello("你好")          # 让模型主动说一句（开场/测试用）
        async for frame in sess.messages(): ...  # frame 是解析后的 JSON dict
        await sess.close()
    """

    def __init__(self, *, app_id: str | None = None, api_key: str | None = None,
                 url: str | None = None, model: str | None = None):
        self.app_id = app_id or settings.volc_app_id
        self.api_key = api_key or settings.volc_api_key
        self.url = url or settings.volc_ws_url
        self.model = model or settings.volc_model
        self.session_id = str(uuid.uuid4())
        self._ws = None
        self.log_id: str | None = None

    def _headers(self) -> dict:
        # 新版鉴权：X-Api-Key 是凭证；App-Id 只是应用配置，不影响鉴权。
        return {
            "X-Api-App-Id": self.app_id,
            "X-Api-Key": self.api_key,
        }

    async def open(self, session_config: dict) -> dict:
        # proxy=None：websockets 14+ 默认读系统代理，本机有残留死代理（127.0.0.1:10090），
        # 不关掉会走死代理连不上；与 httpx trust_env=False 同一个坑。
        kwargs = {"open_timeout": 15, "ping_interval": None, "proxy": None}
        try:
            conn = websockets.connect(self.url, additional_headers=self._headers(), **kwargs)
        except TypeError:  # websockets < 14
            conn = websockets.connect(self.url, extra_headers=self._headers(), **kwargs)

        self._ws = await conn.__aenter__()
        resp = getattr(self._ws, "response", None)
        if resp is not None and getattr(resp, "headers", None):
            self.log_id = resp.headers.get("X-Tt-Logid")

        await self._send({"type": EVT_SESSION_CREATE, "session": session_config})
        created = await self._recv()
        if created.get("type") != EVT_SESSION_CREATED:
            raise RuntimeError(f"session.create 失败：{created}")

        sid = (created.get("session") or {}).get("id") or self.session_id
        return {"session_id": sid, "dialog_id": sid}

    async def _send(self, payload: dict) -> None:
        if not self._ws:
            raise RuntimeError("连接未建立")
        await self._ws.send(json.dumps(payload, ensure_ascii=False))

    async def _recv(self) -> dict:
        raw = await self._ws.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "ignore")
        return json.loads(raw)

    async def send_audio(self, pcm16: bytes) -> None:
        await self._send({
            "type": EVT_AUDIO_APPEND,
            "audio": base64.b64encode(pcm16).decode("ascii"),
        })

    async def commit_audio(self) -> None:
        """强制提交输入音频缓冲，触发端点检测（文件输入 / 需要立即结束时用）。"""
        await self._send({"type": EVT_AUDIO_COMMIT})

    async def say_hello(self, text: str) -> None:
        """让模型直接念出指定文本（开场 / 测试）。"""
        await self._send({"type": EVT_SPEECH_TEXT_COMMIT, "text": text})

    async def send_silence(self) -> None:
        """20ms 静音（16k 单声道 → 640 字节）。断麦时保活。"""
        await self.send_audio(b"\x00" * 640)

    async def messages(self):
        """持续产出下行 JSON 事件 dict。音频 delta 已解出为 _audio 字节。"""
        if not self._ws:
            return
        async for raw in self._ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "ignore")
            try:
                frame = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            if frame.get("type") == EVT_AUDIO_DELTA and frame.get("delta"):
                try:
                    frame["_audio"] = base64.b64decode(frame["delta"])
                except Exception:  # noqa: BLE001
                    pass
            yield frame

    async def close(self) -> None:
        if not self._ws:
            return
        try:
            await self._send({"type": EVT_SESSION_CLOSE})
        except Exception:  # noqa: BLE001
            pass
        try:
            await self._ws.close()
        except Exception:  # noqa: BLE001
            pass
        self._ws = None
