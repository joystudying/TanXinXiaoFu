# -*- coding: utf-8 -*-
"""探测：有没有开关能关掉模型的自主回应，让 500 指定台词真正生效。

方法：每种配置下推一段短问句，紧接着用 500 推一段**明显更长的台词**当探针。
  - 若音频长度≈2 秒 → 模型自主应答（我们的台词没生效）
  - 若音频长度≈8 秒 → 我们的台词被念出来了（覆盖成功）

逐个试 dialog 配置项，看哪个（如果有）能让模型闭嘴。

用法：python scripts/probe_output_mod.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.config import settings                              # noqa: E402
from app.providers.realtime_volc import RealtimeVolcSession  # noqa: E402
from experiment_emotion import CHUNK, SYSTEM_ROLE, Collector, load_pcm  # noqa: E402

DATA = ROOT / "data"

# 探针台词：约 30 字，正常语速念出来 7~9 秒，足够和 2 秒的自主应答区分
PROBE_LINE = "这是一段专门用来测试的台词，如果它被完整念出来，就说明指定文本覆盖成功了。"

BASE_TTS = {"speaker": "zh_male_m191_uranus_bigtts", "speech_rate": -8,
            "audio_config": {"channel": 1, "format": "pcm", "sample_rate": 24000}}

VARIANTS = {
    "V7 只发台词（单片）": "__line_only__",
    "V8 只发台词（start/content/end 分三片）": "__line_split__",
    "V9 只发台词（两片：start+content / end）": "__line_two__",
}


def build_dialog(extra: dict) -> dict:
    d = {"bot_name": "小陈", "system_role": SYSTEM_ROLE,
         "speaking_style": "低落、疲惫、语速慢，句尾不上扬。",
         "extra": {"strict_audit": False}}
    d.update(extra)
    return d


async def push_audio(sess, pcm: bytes) -> float:
    t_end = 0.0
    for i in range(0, len(pcm), CHUNK):
        await sess.send_audio(pcm[i:i + CHUNK])
        t_end = time.monotonic()
        await asyncio.sleep(0.02)
    for _ in range(60):
        await sess.send_audio(b"\x00" * CHUNK)
        await asyncio.sleep(0.02)
    return t_end


async def try_variant(name: str, extra, q: bytes) -> dict:
    sess = RealtimeVolcSession()
    res = {"variant": name, "config": str(extra)}

    cfg = {"tts": BASE_TTS}
    if extra != "__tts_only__":
        cfg["dialog"] = build_dialog(extra if isinstance(extra, dict) else {})

    try:
        await sess.open(cfg)
    except Exception as exc:  # noqa: BLE001
        res["open_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        await sess.close()
        return res

    c = Collector()
    chats: list[str] = []

    async def pump():
        async for f in sess.messages():
            c.feed(f)
            p = f.payload or {}
            if f.event == 550:
                t = p.get("text") or p.get("content")
                if isinstance(t, str) and t.strip():
                    chats.append(t.strip())

    task = asyncio.create_task(pump())
    try:
        if extra == "__line_split__":
            t_sent_500 = time.monotonic()
            await sess.send_tts_text("", start=True)          # 1) 开始
            await asyncio.sleep(0.2)
            await sess.send_tts_text(PROBE_LINE)              # 2) 内容
            await asyncio.sleep(0.2)
            await sess.send_tts_text("", end=True)            # 3) 结束
            await asyncio.sleep(8.0)
            t_end = t_sent_500
        elif extra == "__line_two__":
            t_sent_500 = time.monotonic()
            await sess.send_tts_text(PROBE_LINE, start=True)  # start + 内容
            await asyncio.sleep(0.2)
            await sess.send_tts_text("", end=True)            # 结束
            await asyncio.sleep(8.0)
            t_end = t_sent_500
        elif extra in ("__line_only__", "__line_first__"):
            t_sent_500 = time.monotonic()
            await sess.send_tts_text(PROBE_LINE, start=True, end=True)
            await asyncio.sleep(1.0)

        if extra == "__line_only__":
            await asyncio.sleep(8.0)
            t_end = t_sent_500
        else:
            t_end = await push_audio(sess, q)
            if extra != "__line_first__":
                t_sent_500 = time.monotonic()
                await sess.send_tts_text(PROBE_LINE, start=True, end=True)
            await asyncio.sleep(8.0)
    finally:
        task.cancel()
        await sess.close()

    res["audio_sec"] = round(len(c.audio) / 4 / 24000, 1)
    res["model_text"] = "".join(dict.fromkeys(chats))[:60]
    res["sent_500_after_ms"] = round((t_sent_500 - t_end) * 1000)
    res["verdict"] = (
        "我们的台词被念了" if res["audio_sec"] > 6
        else "模型自主应答（未覆盖）" if res["audio_sec"] > 0
        else "没有音频"
    )
    return res


async def main() -> int:
    if not settings.realtime_configured:
        print("未配置实时语音")
        return 1
    q = load_pcm("_teacher_short.wav")
    print(f"探针台词 {len(PROBE_LINE)} 字，正常念出来约 8 秒\n")

    results = []
    for name, extra in VARIANTS.items():
        r = await try_variant(name, extra, q)
        results.append(r)
        if r.get("open_error"):
            print(f"[{name}] 建会话失败：{r['open_error']}", flush=True)
        else:
            print(f"[{name}] 音频 {r['audio_sec']} 秒 → {r['verdict']}"
                  f"   模型原话「{r['model_text'][:28]}」", flush=True)

    (DATA / "_probe_output_mod.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n明细：data/_probe_output_mod.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
