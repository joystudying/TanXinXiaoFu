"""火山引擎「豆包端到端实时语音」协议实现（真双工）。

协议要点（已实测，见 docs/实时语音验证记录.md）：
  - WebSocket 二进制帧，纯 JSON 文本会被拒
  - 头部 4 字节：version|header_size / type|flags / serialization|compression / 保留
  - flags 必须 0b0100（带 event），payload 必须 gzip
  - StartConnection(event=1) → 回 event 50
  - StartSession(event=100, 带 session_id) → 回 event 150
  - 音频：event=200，message_type=0b0010，gzip 后的原始 PCM

本模块只做协议，不碰数据库、不碰 HTTP（分层边界）。
"""
import gzip
import json
import uuid
from dataclasses import dataclass, field

import websockets

from ..config import settings

PROTOCOL_VERSION = 0b0001
HEADER_SIZE = 0b0001

CLIENT_FULL_REQUEST = 0b0001
CLIENT_AUDIO_ONLY = 0b0010
SERVER_FULL_RESPONSE = 0b1001
SERVER_ACK = 0b1011
SERVER_ERROR = 0b1111

MSG_WITH_EVENT = 0b0100
JSON_SER = 0b0001
NO_SERIALIZATION = 0b0000
GZIP = 0b0001

EVENT_START_CONNECTION = 1
EVENT_FINISH_CONNECTION = 2
EVENT_START_SESSION = 100
EVENT_FINISH_SESSION = 102
EVENT_TASK_REQUEST = 200
EVENT_SAY_HELLO = 300
EVENT_CHAT_TTS_TEXT = 500
EVENT_CHAT_RAG_TEXT = 502

EVENT_CONNECTION_STARTED = 50
EVENT_SESSION_STARTED = 150


@dataclass
class ServerFrame:
    message_type: int
    event: int | None
    session_id: str | None
    payload: dict | None = None
    audio: bytes | None = None
    error: str | None = None


def build_header(message_type: int = CLIENT_FULL_REQUEST,
                 serial: int = JSON_SER,
                 compression: int = GZIP) -> bytes:
    return bytes([
        (PROTOCOL_VERSION << 4) | HEADER_SIZE,
        (message_type << 4) | MSG_WITH_EVENT,
        (serial << 4) | compression,
        0x00,
    ])


def build_frame(event: int, payload: dict | bytes, *,
                session_id: str | None = None,
                message_type: int = CLIENT_FULL_REQUEST,
                serial: int = JSON_SER) -> bytes:
    """组一个上行帧。音频走 serial=NO_SERIALIZATION，payload 直接是 PCM。"""
    raw = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
    body = gzip.compress(raw)

    out = bytearray(build_header(message_type=message_type, serial=serial))
    out.extend(int(event).to_bytes(4, "big"))
    if session_id is not None:
        sid = session_id.encode()
        out.extend(len(sid).to_bytes(4, "big"))
        out.extend(sid)
    out.extend(len(body).to_bytes(4, "big"))
    out.extend(body)
    return bytes(out)


def parse_frame(data) -> ServerFrame | None:
    """解析服务端下行帧。解析不出来返回 None（由调用方决定忽略）。"""
    if isinstance(data, str) or len(data) < 4:
        return None

    b0, b1, b2 = data[0], data[1], data[2]
    header_bytes = (b0 & 0x0F) * 4
    message_type = b1 >> 4
    flags = b1 & 0x0F
    serialization = b2 >> 4
    compression = b2 & 0x0F

    off = header_bytes
    event = None
    if flags & MSG_WITH_EVENT and len(data) >= off + 4:
        event = int.from_bytes(data[off:off + 4], "big")
        off += 4

    session_id = None
    if message_type in (SERVER_FULL_RESPONSE, SERVER_ACK) and len(data) >= off + 4:
        slen = int.from_bytes(data[off:off + 4], "big")
        off += 4
        if 0 < slen < 256 and len(data) >= off + slen:
            session_id = data[off:off + slen].decode("utf-8", "ignore")
            off += slen

    payload = b""
    if len(data) >= off + 4:
        plen = int.from_bytes(data[off:off + 4], "big")
        off += 4
        payload = data[off:off + plen]

    if compression == GZIP and payload:
        try:
            payload = gzip.decompress(payload)
        except Exception:  # noqa: BLE001
            pass

    frame = ServerFrame(message_type=message_type, event=event, session_id=session_id)

    if message_type == SERVER_ERROR:
        frame.error = payload.decode("utf-8", "ignore")[:300] or "unknown_error"
        return frame

    if serialization == JSON_SER:
        try:
            frame.payload = json.loads(payload.decode("utf-8", "ignore")) if payload else {}
        except Exception:  # noqa: BLE001
            frame.payload = {"_raw": payload[:200].decode("utf-8", "ignore")}
    elif payload:
        frame.audio = payload
    return frame


class RealtimeVolcSession:
    """一条到火山实时语音的连接。用法：

        sess = RealtimeVolcSession()
        await sess.open(session_config)
        await sess.send_audio(pcm16_bytes)
        async for frame in sess.messages(): ...
        await sess.close()
    """

    def __init__(self, *, app_id: str | None = None, access_key: str | None = None,
                 resource_id: str | None = None, url: str | None = None):
        self.app_id = app_id or settings.volc_app_id
        self.access_key = access_key or settings.volc_access_token
        self.resource_id = resource_id or settings.volc_resource_id
        self.url = url or settings.volc_ws_url
        self.session_id = str(uuid.uuid4())
        self._ws = None
        self.log_id: str | None = None

    def _headers(self) -> dict:
        return {
            "X-Api-App-ID": self.app_id,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-App-Key": settings.volc_app_key,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }

    async def open(self, session_config: dict) -> dict:
        kwargs = {"open_timeout": 15, "ping_interval": None, "max_queue": 64}
        try:
            conn = websockets.connect(self.url, additional_headers=self._headers(), **kwargs)
        except TypeError:  # websockets < 14
            conn = websockets.connect(self.url, extra_headers=self._headers(), **kwargs)

        self._ws = await conn.__aenter__()
        resp = getattr(self._ws, "response", None)
        if resp is not None and getattr(resp, "headers", None):
            self.log_id = resp.headers.get("X-Tt-Logid")

        # 1) StartConnection
        await self._ws.send(build_frame(EVENT_START_CONNECTION, {}))
        first = parse_frame(await self._ws.recv())
        if first is None or first.event != EVENT_CONNECTION_STARTED:
            raise RuntimeError(f"StartConnection 失败：{first}")

        # 2) StartSession
        await self._ws.send(build_frame(EVENT_START_SESSION, session_config,
                                        session_id=self.session_id))
        second = parse_frame(await self._ws.recv())
        if second is None or second.event != EVENT_SESSION_STARTED:
            raise RuntimeError(f"StartSession 失败：{second}")

        return {"session_id": self.session_id, "dialog_id": (second.payload or {}).get("dialog_id")}

    async def send_audio(self, pcm16: bytes) -> None:
        if not self._ws:
            raise RuntimeError("连接未建立")
        await self._ws.send(build_frame(EVENT_TASK_REQUEST, pcm16,
                                        session_id=self.session_id,
                                        message_type=CLIENT_AUDIO_ONLY,
                                        serial=NO_SERIALIZATION))

    async def say_hello(self, content: str) -> None:
        """让模型主动说一句指定的话（开场用）。"""
        await self._ws.send(build_frame(EVENT_SAY_HELLO, {"content": content},
                                        session_id=self.session_id))

    async def send_rag_text(self, content: str) -> None:
        """会话中注入背景/指令文字，影响模型后续的回应与语气。

        这是「DSH 情绪联动」的落地通道：情绪评估结果通过这里喂给语音模型。
        """
        await self._ws.send(build_frame(EVENT_CHAT_RAG_TEXT, {"content": content},
                                        session_id=self.session_id))

    async def send_tts_text(self, content: str, *, start: bool = False, end: bool = False) -> None:
        """指定 TTS 直接念出的文字（完全接管台词时用）。"""
        await self._ws.send(build_frame(
            EVENT_CHAT_TTS_TEXT,
            {"start": start, "content": content, "end": end},
            session_id=self.session_id,
        ))

    async def send_silence(self) -> None:
        """20ms 静音（16k 单声道 → 640 字节）。断麦时保活用。"""
        await self.send_audio(b"\x00" * 640)

    async def messages(self):
        """持续产出 ServerFrame。连接断开时结束。"""
        if not self._ws:
            return
        async for raw in self._ws:
            frame = parse_frame(raw)
            if frame is not None:
                yield frame

    async def close(self) -> None:
        if not self._ws:
            return
        try:
            await self._ws.send(build_frame(EVENT_FINISH_SESSION, {}, session_id=self.session_id))
        except Exception:  # noqa: BLE001
            pass
        try:
            await self._ws.send(build_frame(EVENT_FINISH_CONNECTION, {}))
        except Exception:  # noqa: BLE001
            pass
        try:
            await self._ws.close()
        except Exception:  # noqa: BLE001
            pass
        self._ws = None
