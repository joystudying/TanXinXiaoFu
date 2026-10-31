# -*- coding: utf-8 -*-
"""可行性验证：会话中途注入情绪指令，学生语气会不会跟着变。

做法：
  第 1 轮  正常问一句 → 记下学生的回复文字与音频（基线）
  注入     通过 ChatRAGText(502) 告诉模型「现在更防备、更低落」
  第 2 轮  同样的话再问一句 → 对比回复长度、音频时长、能量、语速

判断依据（不靠耳朵也能看出差异）：
  - 文字：是否更短、更多停顿标记
  - 音频时长 / 每秒字数：语速是否变慢
  - 能量：是否更小（低落通常更轻）

输出：data/_emo_turn1.wav / data/_emo_turn2.wav，可直接试听对比
"""
import asyncio
import json
import math
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.providers.realtime_volc import RealtimeVolcSession  # noqa: E402
from app.config import settings  # noqa: E402

WAV_IN = ROOT / "data" / "_teacher.wav"
CHUNK = 640

EMOTION_NUDGE = (
    "【当前情绪状态：更低落，也更防备】你刚刚被问到不想提的事，现在更不想说，"
    "声音更小、更慢，句子更短，回答前会先沉默一会儿。不要解释原因。"
)


def load_pcm() -> bytes:
    with wave.open(str(WAV_IN), "rb") as w:
        return w.readframes(w.getnframes())


def float32_to_int16(pcm: bytes) -> bytes:
    n = len(pcm) // 4
    vals = struct.unpack("<%df" % n, pcm[: n * 4])
    peak = max((abs(v) for v in vals), default=0.0)
    gain = min((10 ** (-3 / 20)) / peak, 8.0) if peak > 0 else 1.0
    out = bytearray()
    for v in vals:
        out.extend(struct.pack("<h", int(max(-1.0, min(1.0, v * gain)) * 32767)))
    return bytes(out)


def stats(pcm: bytes) -> dict:
    n = len(pcm) // 4
    if n == 0:
        return {"sec": 0.0, "rms": 0.0}
    vals = struct.unpack("<%df" % n, pcm[: n * 4])
    rms = math.sqrt(sum(v * v for v in vals) / n)
    return {"sec": round(n / 24000, 1), "rms": round(rms, 4)}


class Collector:
    def __init__(self):
        self.audio = bytearray()
        self.text_parts = []

    def feed(self, frame) -> None:
        if frame.audio:
            self.audio.extend(frame.audio)
        payload = frame.payload or {}
        if frame.event == 550:
            t = payload.get("text") or payload.get("content")
            if isinstance(t, str) and t.strip():
                self.text_parts.append(t.strip())

    @property
    def text(self) -> str:
        return "".join(dict.fromkeys(self.text_parts))


async def wait_reply(sess, collector: Collector, *, timeout: float = 25.0, quiet: float = 2.5) -> None:
    """等一轮回复结束：收到音频后持续 quiet 秒无新增就算完。"""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last_len = 0
    last_change = loop.time()

    async def pump():
        async for frame in sess.messages():
            collector.feed(frame)

    task = asyncio.create_task(pump())
    try:
        while loop.time() < deadline:
            await asyncio.sleep(0.4)
            if len(collector.audio) != last_len:
                last_len = len(collector.audio)
                last_change = loop.time()
            if len(collector.audio) > 0 and loop.time() - last_change > quiet:
                break
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def push_audio(sess, pcm: bytes, silence_frames: int = 60) -> None:
    for i in range(0, len(pcm), CHUNK):
        await sess.send_audio(pcm[i:i + CHUNK])
        await asyncio.sleep(0.02)
    for _ in range(silence_frames):
        await sess.send_audio(b"\x00" * CHUNK)
        await asyncio.sleep(0.02)


async def main() -> int:
    if not settings.realtime_configured:
        print("未配置实时语音")
        return 1
    pcm = load_pcm()
    print(f"老师语音 {len(pcm) / 32000:.1f} 秒\n")

    sess = RealtimeVolcSession()
    info = await sess.open({
        "tts": {"speaker": "zh_male_m191_uranus_bigtts", "speech_rate": -8,
                "audio_config": {"channel": 1, "format": "pcm", "sample_rate": 24000}},
        "dialog": {
            "bot_name": "小陈",
            "system_role": (
                "你是一名大二男生，叫小陈。最近连续两周缺课，作业也没交。"
                "真实原因是家里出了事、自己在打零工，但你不想让老师知道。"
                "你说话很短，语气低落、疲惫，常先否认，被温和追问才慢慢松一点。"
            ),
            "speaking_style": "低落、疲惫、语速慢，句尾不上扬。",
            "extra": {"strict_audit": False},
        },
    })
    print(f"会话已建 dialog={str(info.get('dialog_id'))[:8]}…\n")

    # 第 1 轮（基线）
    c1 = Collector()
    print("第 1 轮：正常提问…")
    await push_audio(sess, pcm)
    await wait_reply(sess, c1)
    s1 = stats(bytes(c1.audio))
    print(f"  回复文字：{c1.text[:80]}")
    print(f"  音频 {s1['sec']} 秒  RMS {s1['rms']}\n")

    # 注入情绪
    print("注入情绪指令（ChatRAGText 502）…")
    await sess.send_rag_text(EMOTION_NUDGE)
    await asyncio.sleep(1.5)

    # 第 2 轮（同一个问题）
    c2 = Collector()
    print("第 2 轮：同一句话再问一次…")
    await push_audio(sess, pcm)
    await wait_reply(sess, c2)
    s2 = stats(bytes(c2.audio))
    print(f"  回复文字：{c2.text[:80]}")
    print(f"  音频 {s2['sec']} 秒  RMS {s2['rms']}\n")

    await sess.close()

    # 存成可试听的 wav
    for name, coll in (("_emo_turn1.wav", c1), ("_emo_turn2.wav", c2)):
        if not coll.audio:
            continue
        with wave.open(str(ROOT / "data" / name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(float32_to_int16(bytes(coll.audio)))
        print(f"已保存 data/{name}")

    print("\n=== 对比 ===")
    print(f"  轮1  {s1['sec']} 秒  RMS {s1['rms']}  字数 {len(c1.text)}")
    print(f"  轮2  {s2['sec']} 秒  RMS {s2['rms']}  字数 {len(c2.text)}")
    if s1["sec"] and s2["sec"]:
        print(f"  时长变化 {s2['sec'] / s1['sec'] - 1:+.0%}，"
              f"能量变化 {s2['rms'] / s1['rms'] - 1:+.0%}" if s1["rms"] else "")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
