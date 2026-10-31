# -*- coding: utf-8 -*-
"""真双工端到端验证：把一段「老师」的语音喂进 /ws/voice，看学生是否出声。

流程：
  1. 读 data/_teacher.wav（16k / 16bit / 单声道，由系统语音合成生成）
  2. 连上 /ws/voice，按 20ms 一片推流
  3. 推完补 1.2 秒静音，让服务端判定老师说完了
  4. 监听 20 秒，收集事件与音频；收到的音频存成 data/_student_reply.pcm

用法：python scripts/probe_voice_turn.py
"""
import asyncio
import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAV = ROOT / "data" / "_teacher.wav"
OUT = ROOT / "data" / "_student_reply.pcm"
EVENTS_OUT = ROOT / "data" / "_voice_events.json"
URL = "ws://127.0.0.1:8000/ws/voice"
CHUNK = 640          # 20ms @ 16k/16bit


def load_pcm() -> bytes:
    with wave.open(str(WAV), "rb") as w:
        assert w.getnchannels() == 1, "需要单声道"
        assert w.getsampwidth() == 2, "需要 16bit"
        assert w.getframerate() == 16000, f"需要 16k，实际 {w.getframerate()}"
        return w.readframes(w.getnframes())


async def main() -> int:
    if not WAV.exists():
        print("缺少 data/_teacher.wav")
        return 1
    pcm = load_pcm()
    print(f"老师语音：{len(pcm) / 32000:.1f} 秒\n")

    import websockets

    kwargs = {"open_timeout": 15, "ping_interval": None, "max_size": 8 * 1024 * 1024}
    try:
        conn = websockets.connect(URL, **kwargs)
    except TypeError:
        conn = websockets.connect(URL, **kwargs)

    events = []
    audio = bytearray()

    async with conn as ws:
        first = json.loads(await asyncio.wait_for(ws.recv(), timeout=25))
        if first.get("type") != "ready":
            print(f"[FAIL] {first}")
            return 1
        print(f"[OK] ready dialog={str(first.get('dialog_id'))[:8]}…")

        async def receiver() -> None:
            while True:
                msg = await ws.recv()
                if isinstance(msg, bytes):
                    audio.extend(msg)
                    continue
                data = json.loads(msg)
                events.append(data)

        recv_task = asyncio.create_task(receiver())

        # 推老师语音
        for i in range(0, len(pcm), CHUNK):
            await ws.send(pcm[i:i + CHUNK])
            await asyncio.sleep(0.02)
        print("  老师说话推送完毕，补 1.2 秒静音…")

        for _ in range(60):                      # 1.2 秒
            await ws.send(b"\x00" * CHUNK)
            await asyncio.sleep(0.02)

        # 等学生回应（最多 20 秒，收到音频后 3 秒无新增即收工）
        deadline = asyncio.get_event_loop().time() + 20
        last_audio_len = 0
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.5)
            if len(audio) > last_audio_len:
                last_audio_len = len(audio)
                deadline = asyncio.get_event_loop().time() + 3

        recv_task.cancel()
        try:
            await ws.send(json.dumps({"type": "finish"}))
        except Exception:  # noqa: BLE001
            pass

    print(f"\n收到音频：{len(audio)} 字节 ≈ {len(audio) / 4 / 24000:.1f} 秒（24k / float32 / 单声道）")
    if audio:
        OUT.write_bytes(bytes(audio))
        print(f"已保存：{OUT}")

    EVENTS_OUT.write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"收到事件：{len(events)} 条 → {EVENTS_OUT}")
    for e in events[:20]:
        if e.get("type") == "event":
            payload = json.dumps(e.get("payload", {}), ensure_ascii=False)
            print(f"  event {e.get('event')}: {payload[:180]}")
        else:
            print(f"  {json.dumps(e, ensure_ascii=False)[:180]}")

    return 0 if audio else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
