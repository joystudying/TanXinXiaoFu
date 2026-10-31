# -*- coding: utf-8 -*-
"""验证 /ws/voice 代理（本服务 → 火山实时语音）。

做三件事：
  1. 连上本服务的 /ws/voice，看是否回 ready（说明上游已建会话）
  2. 连续发 1 秒静音音频帧，看上游是否报错
  3. 打印期间收到的任何事件

用法：python scripts/probe_voice_ws.py
（服务需先启动在 127.0.0.1:8000）
"""
import asyncio
import json
import sys

URL = "ws://127.0.0.1:8000/ws/voice"
FRAME = b"\x00" * 640      # 20ms 静音


async def main() -> int:
    import websockets

    try:
        conn = websockets.connect(URL, open_timeout=10, ping_interval=None)
    except TypeError:
        conn = websockets.connect(URL, open_timeout=10)

    received = []
    async with conn as ws:
        print(f"已连接 {URL}")

        # 等 ready
        try:
            first = await asyncio.wait_for(ws.recv(), timeout=20)
        except asyncio.TimeoutError:
            print("[FAIL] 20 秒没有收到 ready")
            return 1

        if isinstance(first, str):
            data = json.loads(first)
        else:
            print(f"[FAIL] 第一帧不是 JSON：{first[:60]!r}")
            return 1

        if data.get("type") != "ready":
            print(f"[FAIL] {data}")
            return 1

        print(f"  [OK] ready  session={data.get('session_id', '')[:8]}…  "
              f"dialog={str(data.get('dialog_id'))[:8]}…  rate={data.get('sample_rate')}")

        # 发 1 秒静音
        print("  发送 1 秒静音（50 帧）…")
        for _ in range(50):
            await ws.send(FRAME)
            await asyncio.sleep(0.02)

        # 收 5 秒内的事件
        print("  监听 5 秒下行…")
        deadline = asyncio.get_event_loop().time() + 5
        audio_bytes = 0
        while asyncio.get_event_loop().time() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
            except asyncio.TimeoutError:
                continue
            if isinstance(msg, bytes):
                audio_bytes += len(msg)
                continue
            data = json.loads(msg)
            if data.get("type") == "error":
                print(f"  [ERR] {data.get('code')}: {data.get('message')}")
            else:
                received.append(data)
                print(f"  ← event {data.get('event')}: "
                      f"{json.dumps(data.get('payload', {}), ensure_ascii=False)[:160]}")

        await ws.send(json.dumps({"type": "finish"}))

    print(f"\n收到音频 {audio_bytes} 字节，事件 {len(received)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
