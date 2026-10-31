# -*- coding: utf-8 -*-
"""火山引擎「豆包端到端实时语音」单条通路验证（第三步，按官方协议）。

前两步结论：
  1. WebSocket 握手 101 → App ID + Access Token 有效；
  2. 纯 JSON 文本帧被拒（服务端回 "unsupported protocol version 7"）→ 必须用二进制帧。

本步按官方示例的帧结构重试：
  头部 4 字节：version(4) + header_size(4) | message_type(4) + flags(4) | serialization(4) + compression(4) | 保留(8)
  flags = 0b0100 表示带 event 号；payload 必须 gzip 压缩
  StartConnection: event=1
  StartSession   : event=100，帧里多了 session_id

用法：python scripts/probe_volc.py
不打印任何密钥。
"""
import asyncio
import gzip
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
APP_KEY = "PlgvMymc7f3tQnJ6"      # 官方示例里的固定应用级 key（公开常量，非密钥）

V1 = 0b0001
HEADER_SIZE = 0b0001              # 单位 4 字节
CLIENT_FULL = 0b0001
CLIENT_AUDIO = 0b0010
SERVER_FULL = 0b1001
SERVER_ACK = 0b1011
SERVER_ERROR = 0b1111
MSG_WITH_EVENT = 0b0100
JSON_SER = 0b0001
NO_SER = 0b0000
GZIP = 0b0001


def load_env() -> dict:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


ENV = load_env()
APP_ID = ENV.get("VOLC_APP_ID", "")
TOKEN = ENV.get("VOLC_ACCESS_TOKEN", "")
RESOURCE_ID = ENV.get("VOLC_RESOURCE_ID", "volc.speech.dialog")


def headers() -> dict:
    return {
        "X-Api-App-ID": APP_ID,
        "X-Api-Access-Key": TOKEN,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-App-Key": APP_KEY,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }


def header(message_type: int = CLIENT_FULL, serial: int = JSON_SER, compression: int = GZIP) -> bytes:
    return bytes([
        (V1 << 4) | HEADER_SIZE,
        (message_type << 4) | MSG_WITH_EVENT,
        (serial << 4) | compression,
        0x00,
    ])


def frame(event: int, payload: dict | bytes, session_id: str | None = None,
          message_type: int = CLIENT_FULL, serial: int = JSON_SER) -> bytes:
    raw = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
    body = gzip.compress(raw)
    out = bytearray(header(message_type=message_type, serial=serial))
    out.extend(int(event).to_bytes(4, "big"))
    if session_id is not None:
        sid = session_id.encode()
        out.extend(len(sid).to_bytes(4, "big"))
        out.extend(sid)
    out.extend(len(body).to_bytes(4, "big"))
    out.extend(body)
    return bytes(out)


def parse(data) -> dict:
    if isinstance(data, str):
        return {"raw_text": data[:200]}
    if len(data) < 4:
        return {"raw_hex": data.hex()[:80]}
    b0, b1, b2 = data[0], data[1], data[2]
    info = {
        "version": b0 >> 4,
        "header_bytes": (b0 & 0x0F) * 4,
        "message_type": b1 >> 4,
        "flags": b1 & 0x0F,
        "serialization": b2 >> 4,
        "compression": b2 & 0x0F,
    }
    off = info["header_bytes"]
    if info["flags"] & 0b0100 and len(data) >= off + 4:
        info["event"] = int.from_bytes(data[off:off + 4], "big")
        off += 4
    if info["message_type"] in (SERVER_FULL, SERVER_ACK):
        if len(data) >= off + 4:
            slen = int.from_bytes(data[off:off + 4], "big")
            off += 4
            if 0 < slen < 200 and len(data) >= off + slen:
                info["session_id"] = data[off:off + slen].decode("utf-8", "ignore")
                off += slen
    if len(data) >= off + 4:
        plen = int.from_bytes(data[off:off + 4], "big")
        off += 4
        payload = data[off:off + plen]
        if info["compression"] == GZIP:
            try:
                payload = gzip.decompress(payload)
            except Exception:  # noqa: BLE001
                pass
        try:
            info["payload"] = json.loads(payload.decode("utf-8", "ignore"))
        except Exception:  # noqa: BLE001
            info["payload_text"] = payload[:200].decode("utf-8", "ignore")
            info["payload_hex"] = payload[:32].hex()
    return info


async def main() -> int:
    if not APP_ID or not TOKEN:
        print("缺少 VOLC_APP_ID / VOLC_ACCESS_TOKEN")
        return 1
    import websockets

    session_id = str(uuid.uuid4())
    print(f"APP ID {APP_ID} / Resource {RESOURCE_ID} / session {session_id[:8]}…\n")

    kwargs = {"open_timeout": 15, "ping_interval": None}
    try:
        conn = websockets.connect(URL, additional_headers=headers(), **kwargs)
    except TypeError:
        conn = websockets.connect(URL, extra_headers=headers(), **kwargs)

    async with conn as ws:
        logid = None
        resp = getattr(ws, "response", None)
        if resp is not None and getattr(resp, "headers", None):
            logid = resp.headers.get("X-Tt-Logid")
        print(f"握手 101  OK   logid={logid}\n")

        # 1) StartConnection
        await ws.send(frame(1, {}))
        r1 = parse(await asyncio.wait_for(ws.recv(), timeout=12))
        print("StartConnection →")
        print("  " + json.dumps(r1, ensure_ascii=False)[:500] + "\n")

        # 2) StartSession
        session_cfg = {
            "tts": {"audio_config": {"channel": 1, "format": "pcm", "sample_rate": 24000}},
            "dialog": {
                "bot_name": "小陈",
                "system_role": "你是一名大二学生，男生，最近因为跟不上课程而不想上课。",
                "speaking_style": "说话简短，语气犹豫，常先否认有事。",
                "extra": {"strict_audit": False},
            },
        }
        await ws.send(frame(100, session_cfg, session_id=session_id))
        try:
            r2 = parse(await asyncio.wait_for(ws.recv(), timeout=15))
            print("StartSession →")
            print("  " + json.dumps(r2, ensure_ascii=False)[:800])
        except asyncio.TimeoutError:
            print("StartSession → 15 秒无回包")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
