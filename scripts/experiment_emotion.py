# -*- coding: utf-8 -*-
"""方案 A：对照实验 —— ChatRAGText(502) 注入情绪，到底有没有用。

设计：
  条件 C0（对照）：问第 1 句 → 问第 2 句，全程不注入
  条件 C1（实验）：问第 1 句 → 注入行为化指令 → 问第 2 句
  每个条件重复 N 次，取中位数，抵消模型随机性。

指标（都在第 2 轮上比较）：
  chars   回复字数
  sec     音频时长
  cps     每秒字数（语速）
  rms     平均能量（音量）
  f0      基频中位数（音高：越高越"积极"，越低越"低沉"）
  zcr     过零率

判断逻辑：
  C1 相对 C0，若 f0 下降、cps 下降、chars 减少 → 注入有效（更低沉更慢更少话）
  若差异小于噪声（同条件内多次运行的波动） → 判定无效

用法：python scripts/experiment_emotion.py [重复次数]
"""
import asyncio
import json
import math
import statistics
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings                      # noqa: E402
from app.providers.realtime_volc import RealtimeVolcSession  # noqa: E402

DATA = ROOT / "data"
CHUNK = 640
SILENCE_AFTER = 60          # 说完补 1.2 秒静音

NUDGE = (
    "（系统提示，不要说出这段）你现在情绪更低落。接下来回答只用五到八个字，"
    "声音更轻、更慢，句尾往下压，不要解释原因。"
)

SYSTEM_ROLE = (
    "你是一名大二男生，叫小陈。最近连续两周缺课，作业也没交。"
    "真实原因是家里出了事、自己在打零工，但你不想让老师知道。"
    "你说话很短，语气低落、疲惫，常先否认，被温和追问才慢慢松一点。"
)


def load_pcm(name: str) -> bytes:
    with wave.open(str(DATA / name), "rb") as w:
        return w.readframes(w.getnframes())


def analyze(pcm: bytes) -> dict:
    n = len(pcm) // 4
    if n == 0:
        return {"chars": 0, "sec": 0.0, "cps": 0.0, "rms": 0.0, "f0": 0.0, "zcr": 0.0}
    vals = struct.unpack("<%df" % n, pcm[: n * 4])

    rms = math.sqrt(sum(v * v for v in vals) / n)
    zcr = sum(1 for i in range(1, n) if (vals[i - 1] < 0) != (vals[i] < 0)) / (n - 1)

    # 基频估计：每 20ms 一帧，只在能量足够的帧上做自相关
    frame = 480          # 20ms @24k
    lag_min, lag_max = 40, 240   # 100Hz ~ 600Hz
    f0s = []
    for start in range(0, n - frame, frame):
        seg = vals[start:start + frame]
        energy = sum(v * v for v in seg) / frame
        if energy < rms * rms * 0.5:      # 太轻的帧不算音高
            continue
        best_lag, best_corr = 0, 0.0
        for lag in range(lag_min, lag_max):
            corr = 0.0
            for i in range(frame - lag):
                corr += seg[i] * seg[i + lag]
            if corr > best_corr:
                best_corr, best_lag = corr, lag
        if best_lag:
            f0s.append(24000 / best_lag)

    return {
        "sec": round(n / 24000, 2),
        "rms": round(rms, 5),
        "zcr": round(zcr, 4),
        "f0": round(statistics.median(f0s), 1) if f0s else 0.0,
        "voiced_frames": len(f0s),
    }


def to_wav(pcm: bytes, name: str) -> None:
    n = len(pcm) // 4
    vals = struct.unpack("<%df" % n, pcm[: n * 4])
    peak = max((abs(v) for v in vals), default=0.0)
    gain = min((10 ** (-3 / 20)) / peak, 8.0) if peak > 0 else 1.0
    out = bytearray()
    for v in vals:
        out.extend(struct.pack("<h", int(max(-1.0, min(1.0, v * gain)) * 32767)))
    with wave.open(str(DATA / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(bytes(out))


class Collector:
    def __init__(self):
        self.audio = bytearray()
        self.parts = []

    def feed(self, frame) -> None:
        if frame.audio:
            self.audio.extend(frame.audio)
        p = frame.payload or {}
        if frame.event == 550:
            t = p.get("text") or p.get("content")
            if isinstance(t, str) and t.strip():
                self.parts.append(t.strip())

    @property
    def text(self) -> str:
        return "".join(dict.fromkeys(self.parts))


async def wait_reply(sess, c: Collector, timeout=25.0, quiet=2.2) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last, last_change = 0, loop.time()

    async def pump():
        async for f in sess.messages():
            c.feed(f)

    task = asyncio.create_task(pump())
    try:
        while loop.time() < deadline:
            await asyncio.sleep(0.4)
            if len(c.audio) != last:
                last, last_change = len(c.audio), loop.time()
            if c.audio and loop.time() - last_change > quiet:
                break
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def push(sess, pcm: bytes) -> None:
    for i in range(0, len(pcm), CHUNK):
        await sess.send_audio(pcm[i:i + CHUNK])
        await asyncio.sleep(0.02)
    for _ in range(SILENCE_AFTER):
        await sess.send_audio(b"\x00" * CHUNK)
        await asyncio.sleep(0.02)


async def one_run(condition: str, idx: int, q1: bytes, q2: bytes) -> dict:
    sess = RealtimeVolcSession()
    await sess.open({
        "tts": {"speaker": "zh_male_m191_uranus_bigtts", "speech_rate": -8,
                "audio_config": {"channel": 1, "format": "pcm", "sample_rate": 24000}},
        "dialog": {"bot_name": "小陈", "system_role": SYSTEM_ROLE,
                   "speaking_style": "低落、疲惫、语速慢，句尾不上扬。",
                   "extra": {"strict_audit": False}},
    })
    try:
        c1 = Collector()
        await push(sess, q1)
        await wait_reply(sess, c1)

        if condition == "C1":
            await sess.send_rag_text(NUDGE)
            await asyncio.sleep(1.0)

        c2 = Collector()
        await push(sess, q2)
        await wait_reply(sess, c2)
    finally:
        await sess.close()

    a1, a2 = analyze(bytes(c1.audio)), analyze(bytes(c2.audio))
    a1["chars"], a2["chars"] = len(c1.text), len(c2.text)
    for a in (a1, a2):
        a["cps"] = round(a["chars"] / a["sec"], 2) if a["sec"] else 0.0

    tag = f"{condition}_{idx}"
    if c1.audio:
        to_wav(bytes(c1.audio), f"_exp_{tag}_r1.wav")
    if c2.audio:
        to_wav(bytes(c2.audio), f"_exp_{tag}_r2.wav")

    return {"condition": condition, "run": idx,
            "r1_text": c1.text, "r2_text": c2.text, "r1": a1, "r2": a2}


async def main() -> int:
    if not settings.realtime_configured:
        print("未配置实时语音")
        return 1
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    q1, q2 = load_pcm("_teacher.wav"), load_pcm("_teacher2.wav")
    print(f"对照组/实验组各 {runs} 次，共 {runs * 2} 次会话\n")

    results = []
    for condition in ("C0", "C1"):
        for i in range(1, runs + 1):
            print(f"[{condition} 第 {i} 次] …", flush=True)
            r = await one_run(condition, i, q1, q2)
            results.append(r)
            print(f"  轮1「{r['r1_text'][:24]}」 → 轮2「{r['r2_text'][:24]}」"
                  f"  字{r['r2']['chars']} 时{r['r2']['sec']}s f0={r['r2']['f0']}Hz", flush=True)

    (DATA / "_exp_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n=== 汇总（第 2 轮）===")
    print(f"{'条件':<4}{'字数':>6}{'时长':>7}{'语速':>7}{'能量':>9}{'基频':>8}")
    summary = {}
    for cond in ("C0", "C1"):
        rows = [r["r2"] for r in results if r["condition"] == cond]
        med = {k: round(statistics.median([x[k] for x in rows]), 4) for k in ("chars", "sec", "cps", "rms", "f0")}
        summary[cond] = med
        print(f"{cond:<4}{med['chars']:>6.0f}{med['sec']:>7.1f}{med['cps']:>7.2f}"
              f"{med['rms']:>9.4f}{med['f0']:>8.1f}")

    print("\n=== C1 相对 C0 的变化 ===")
    for k, label, good in (("chars", "字数", "down"), ("cps", "语速", "down"),
                           ("rms", "能量", "down"), ("f0", "基频", "down")):
        a, b = summary["C0"][k], summary["C1"][k]
        if not a:
            continue
        delta = (b - a) / a
        verdict = "符合预期" if (delta < -0.03 and good == "down") else (
            "无明显变化" if abs(delta) <= 0.03 else "与预期相反")
        print(f"  {label}: {a} → {b}  ({delta:+.0%})  {verdict}")

    print("\n明细见 data/_exp_results.json，音频见 data/_exp_C*_r*.wav")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
