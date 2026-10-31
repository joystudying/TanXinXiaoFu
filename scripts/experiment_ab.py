# -*- coding: utf-8 -*-
"""A/B 量化：端到端自由对话 vs 500 指定台词。

三个指标：
  1. 首响延迟：老师说完 → 学生第一个音频字节
  2. 打断停止延迟：老师插话 → 学生语音停下（插话只发 1 秒，避免触发新一轮）
  3. 语气词密度：嗯/呃/那个/其实/就是/…… 每 100 字的出现次数

用法：
  python scripts/experiment_ab.py latency 5
  python scripts/experiment_ab.py interrupt 3
"""
import asyncio
import json
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.config import settings                              # noqa: E402
from app.providers.realtime_volc import RealtimeVolcSession  # noqa: E402
from app.services.model import call_model                    # noqa: E402
from experiment_emotion import (                             # noqa: E402
    CHUNK, SYSTEM_ROLE, Collector, analyze, load_pcm, to_wav,
)

SILENCE_AFTER = 60      # 说完补 1.2 秒静音


async def push_timed(sess, pcm: bytes) -> float:
    """推老师音频，返回「最后一个真实说话帧」发出的时刻。

    测首响必须以这个时间为基准：模型是全双工的，会在我们还在补尾静音时就开口，
    用「推流结束」当基准会算出负延迟。
    """
    t_speech_end = 0.0
    for i in range(0, len(pcm), CHUNK):
        await sess.send_audio(pcm[i:i + CHUNK])
        t_speech_end = time.monotonic()
        await asyncio.sleep(0.02)
    for _ in range(SILENCE_AFTER):
        await sess.send_audio(b"\x00" * CHUNK)
        await asyncio.sleep(0.02)
    return t_speech_end

DATA = ROOT / "data"

SESSIONS = {
    "tts": {"speaker": "zh_male_m191_uranus_bigtts", "speech_rate": -8,
            "audio_config": {"channel": 1, "format": "pcm", "sample_rate": 24000}},
    "dialog": {"bot_name": "小陈", "system_role": SYSTEM_ROLE,
               "speaking_style": "低落、疲惫、语速慢，句尾不上扬。",
               "extra": {"strict_audit": False}},
}

TEACHER_TEXT = "小陈，最近上课感觉怎么样？我看你这几次都没来，是不是遇到什么事了？"
FILLERS = ["嗯", "呃", "那个", "其实", "就是", "反正", "……"]

SCRIPT_PROMPT = (
    "你是一名叫小陈的大二男生，最近连续两周缺课、作业没交。真实原因是家里出事、"
    "自己在打零工，但不想让老师知道。你说话很短、语气低落疲惫、常先否认，"
    "会带「……」「其实」这类犹豫的词。\n"
    "现在请只输出你要说的一句话：口语、20 字以内、不要引号、不要旁白、不要解释。"
)


def filler_density(text: str) -> float:
    if not text:
        return 0.0
    return round(sum(text.count(f) for f in FILLERS) / len(text) * 100, 1)


class Timed(Collector):
    """额外记录两个时刻：识别结束（event 459）和每帧音频到达时间。"""

    def __init__(self):
        super().__init__()
        self.chunks: list[tuple[float, int]] = []
        self.asr_end_at: float | None = None

    def feed(self, frame) -> None:
        now = time.monotonic()
        if frame.event == 459:
            self.asr_end_at = now
        if frame.audio:
            self.chunks.append((now, len(frame.audio)))
        super().feed(frame)

    def first_audio_after(self, t: float | None) -> float | None:
        if t is None:
            return None
        for ts, _ in self.chunks:
            if ts > t:
                return ts
        return None


async def pump_into(sess, c: Timed) -> asyncio.Task:
    async def run():
        try:
            async for f in sess.messages():
                c.feed(f)
        except Exception:  # noqa: BLE001
            pass

    return asyncio.create_task(run())


async def wait_quiet(c: Timed, *, timeout=25.0, quiet=2.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last_len, last_change = 0, loop.time()
    while loop.time() < deadline:
        await asyncio.sleep(0.2)
        if len(c.audio) != last_len:
            last_len, last_change = len(c.audio), loop.time()
        if c.audio and loop.time() - last_change > quiet:
            return


async def dsh_line() -> tuple[str, float]:
    t0 = time.monotonic()
    out = await call_model([
        {"role": "system", "content": SCRIPT_PROMPT},
        {"role": "user", "content": f"老师说：{TEACHER_TEXT}"},
    ])
    ms = (time.monotonic() - t0) * 1000
    return (out.get("text") or "").strip().strip("“”\"'"), ms


async def run_latency(mode: str, q1: str) -> dict:
    sess = RealtimeVolcSession()
    await sess.open(SESSIONS)
    c = Timed()
    task = await pump_into(sess, c)
    try:
        t_speech_end = await push_timed(sess, q1)

        llm_ms = 0.0
        line = ""
        if mode == "B":
            line, llm_ms = await dsh_line()
            await sess.send_tts_text(line, start=True, end=True)

        await wait_quiet(c)
    finally:
        task.cancel()
        await sess.close()

    # 基准：识别结束事件（459），不是最后一帧——模型会在老师还没说完时就应答
    base = c.asr_end_at or t_speech_end
    first = c.first_audio_after(base)
    lat = round((first - base) * 1000) if first else None

    # 第二个口径：老师最后一个说话帧 → 学生第一帧（更贴近"听起来多快")
    first_end = next((ts for ts, _ in c.chunks if ts > t_speech_end), None)
    lat_end = round((first_end - t_speech_end) * 1000) if first_end else None
    m = analyze(bytes(c.audio))
    text = line if mode == "B" else c.text
    m.update({"mode": mode, "latency_ms": lat, "llm_ms": round(llm_ms),
              "text": text, "chars": len(text), "fillers": filler_density(text),
              "asr_end_found": c.asr_end_at is not None, "lat_from_end_ms": lat_end})
    if c.audio:
        to_wav(bytes(c.audio), f"_ab_{mode}.wav")
    return m


async def run_interrupt(mode: str, q1: str, q2: str) -> dict:
    """等学生开口约 1.5 秒后插一句 1 秒的短话，量多久停。"""
    sess = RealtimeVolcSession()
    await sess.open(SESSIONS)
    c = Timed()
    task = await pump_into(sess, c)
    res = {"mode": mode}
    try:
        t_speech_end = await push_timed(sess, q1)

        if mode == "B":
            line, _ = await dsh_line()
            res["script"] = line
            await sess.send_tts_text(line, start=True, end=True)

        # 以识别结束事件为基准等学生开口
        base = c.asr_end_at or t_speech_end
        t_first = None
        for _ in range(400):
            await asyncio.sleep(0.05)
            t_first = c.first_audio_after(base)
            if t_first:
                break
        res["first_audio_ms"] = round(((t_first or time.monotonic()) - base) * 1000)

        await asyncio.sleep(1.0)                 # 让它说 1 秒就插话
        t_cut = time.monotonic()
        res["spoken_before_cut_ms"] = round((t_cut - (t_first or t_cut)) * 1000)

        # 插话只发 1 秒（50 帧），不触发新一轮
        short = q2[: CHUNK * 50]
        for i in range(0, len(short), CHUNK):
            await sess.send_audio(short[i:i + CHUNK])
            await asyncio.sleep(0.02)

        await asyncio.sleep(3.0)
        after = [ts for ts, _ in c.chunks if ts > t_cut]
        res["frames_after_cut"] = len(after)
        res["audio_after_cut_ms"] = round((after[-1] - t_cut) * 1000) if after else 0
    finally:
        task.cancel()
        await sess.close()
    return res


async def main() -> int:
    if not settings.realtime_configured:
        print("未配置实时语音")
        return 1
    kind = (sys.argv[1] if len(sys.argv) > 1 else "latency").lower()
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    q1, q2 = load_pcm("_teacher_short.wav"), load_pcm("_teacher2.wav")

    if kind == "latency":
        rows = []
        for i in range(1, runs + 1):
            a = await run_latency("A", q1)
            print(f"  A{i} 说停→开口 {a['lat_from_end_ms']}ms  汉字 {a['chars']}"
                  f"  语气词 {a['fillers']}  「{a['text'][:26]}」", flush=True)
            b = await run_latency("B", q1)
            print(f"  B{i} 说停→开口 {b['lat_from_end_ms']}ms（其中写词 {b['llm_ms']}ms）"
                  f"  汉字 {b['chars']}  语气词 {b['fillers']}  「{b['text'][:26]}」", flush=True)
            rows.append({"A": a, "B": b})
        (DATA / "_ab_latency.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

        print("\n=== 汇总（中位数）===")
        for key, label in (("lat_from_end_ms", "说停→开口(ms)"), ("chars", "回复字数"),
                           ("fillers", "语气词密度(/100字)")):
            av = [r["A"][key] for r in rows if r["A"][key] is not None]
            bv = [r["B"][key] for r in rows if r["B"][key] is not None]
            if av and bv:
                print(f"  {label}: A {st.median(av):.0f}  B {st.median(bv):.0f}"
                      f"  差 {st.median(bv) - st.median(av):+.0f}")

    elif kind == "interrupt":
        rows = []
        for i in range(1, runs + 1):
            for mode in ("A", "B"):
                r = await run_interrupt(mode, q1, q2)
                print(f"  {mode}{i} 插话前已说 {r['spoken_before_cut_ms']}ms → "
                      f"插话后又收到 {r['frames_after_cut']} 帧 / {r['audio_after_cut_ms']}ms",
                      flush=True)
                rows.append(r)
        (DATA / "_ab_interrupt.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n=== 汇总（插话后学生还说了多久）===")
        for mode in ("A", "B"):
            v = [r["audio_after_cut_ms"] for r in rows if r["mode"] == mode]
            if v:
                print(f"  {mode}: 中位 {st.median(v):.0f}ms  范围 {min(v)}~{max(v)}ms")
    else:
        print("参数只有 latency / interrupt")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
