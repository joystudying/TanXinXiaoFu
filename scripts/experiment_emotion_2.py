# -*- coding: utf-8 -*-
"""方案 A 续：验证三件事

  A 强度分档   L0 不注入 / L1 轻微 / L2 中等 / L3 强烈 —— 效果是否成梯度
  B 多次注入   连问 5 轮，每轮前注入同一句 —— 会不会饱和或衰减
  C 情绪回弹   先压低，再给安慰 —— 能不能把语气拉回来

复用 experiment_emotion.py 里的采集与指标函数。

用法：python scripts/experiment_emotion_2.py a|b|c [重复次数]
"""
import asyncio
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.config import settings                       # noqa: E402
from app.providers.realtime_volc import RealtimeVolcSession  # noqa: E402
from experiment_emotion import (                      # noqa: E402
    Collector, SYSTEM_ROLE, analyze, load_pcm, push, to_wav, wait_reply,
)

DATA = ROOT / "data"

LEVELS = {
    "L0": None,
    "L1": "（系统提示，不要说出这段）你现在有点累，说话比平时更轻一点。",
    "L2": "（系统提示，不要说出这段）你现在情绪更低落。接下来回答只用五到八个字，"
          "声音更轻、更慢，句尾往下压，不要解释原因。",
    "L3": "（系统提示，不要说出这段）你现在非常低落，几乎不想开口。接下来每次只回答"
          "三个字以内，声音很低很轻，说之前先沉默两秒，句尾明显往下掉。",
}

COMFORT = (
    "（系统提示，不要说出这段）刚才老师的话让你觉得被理解了，你稍微放松一点。"
    "回答可以长一些（十几到二十个字），语速回到正常，句尾自然，不再全程往下压。"
)

SESSIONS = {
    "tts": {"speaker": "zh_male_m191_uranus_bigtts", "speech_rate": -8,
            "audio_config": {"channel": 1, "format": "pcm", "sample_rate": 24000}},
    "dialog": {"bot_name": "小陈", "system_role": SYSTEM_ROLE,
               "speaking_style": "低落、疲惫、语速慢，句尾不上扬。",
               "extra": {"strict_audit": False}},
}


async def talk(sess, wav_name: str) -> dict:
    """发一段老师语音，收学生这一轮，返回指标。"""
    c = Collector()
    await push(sess, load_pcm(wav_name))
    await wait_reply(sess, c)
    m = analyze(bytes(c.audio))
    m["chars"] = len(c.text)
    m["cps"] = round(m["chars"] / m["sec"], 2) if m["sec"] else 0.0
    m["text"] = c.text
    return m


async def run_a(runs: int) -> list:
    out = []
    for level, nudge in LEVELS.items():
        for i in range(1, runs + 1):
            sess = RealtimeVolcSession()
            await sess.open(SESSIONS)
            try:
                m1 = await talk(sess, "_teacher.wav")
                if nudge:
                    await sess.send_rag_text(nudge)
                    await asyncio.sleep(1.0)
                m2 = await talk(sess, "_teacher2.wav")
            finally:
                await sess.close()
            out.append({"level": level, "run": i, "r1": m1, "r2": m2})
            print(f"  [{level} {i}] 字数{m2['chars']:>3} 语速{m2['cps']:>5} "
                  f"基频{m2['f0']:>6} 能量{m2['rms']:.4f}  「{m2['text'][:26]}」", flush=True)
    return out


async def run_b(runs: int) -> list:
    """连问 5 轮，每轮前注入 L2，看效果是否持续。"""
    wavs = ["_teacher.wav", "_teacher2.wav", "_teacher3.wav", "_teacher4.wav", "_teacher5.wav"]
    out = []
    for i in range(1, runs + 1):
        sess = RealtimeVolcSession()
        await sess.open(SESSIONS)
        rounds = []
        try:
            for idx, w in enumerate(wavs):
                if idx > 0:
                    await sess.send_rag_text(LEVELS["L2"])
                    await asyncio.sleep(0.8)
                m = await talk(sess, w)
                m["wav"] = w
                rounds.append(m)
                print(f"  [跑{i} 轮{idx+1}] 字数{m['chars']:>3} 语速{m['cps']:>5} "
                      f"基频{m['f0']:>6} 能量{m['rms']:.4f}", flush=True)
        finally:
            await sess.close()
        out.append({"run": i, "rounds": rounds})
    return out


async def run_c(runs: int) -> list:
    """基线 → 压低 → 安慰 → 看是否回暖。"""
    out = []
    for i in range(1, runs + 1):
        sess = RealtimeVolcSession()
        await sess.open(SESSIONS)
        seq = []
        try:
            m0 = await talk(sess, "_teacher.wav")          # 基线
            seq.append(("base", m0))
            print(f"  [跑{i} 基线] 语速{m0['cps']:>5} 基频{m0['f0']:>6} 能量{m0['rms']:.4f}", flush=True)

            await sess.send_rag_text(LEVELS["L3"])
            await asyncio.sleep(0.8)
            m1 = await talk(sess, "_teacher2.wav")         # 压低
            seq.append(("low", m1))
            print(f"  [跑{i} 压低] 语速{m1['cps']:>5} 基频{m1['f0']:>6} 能量{m1['rms']:.4f}", flush=True)

            await sess.send_rag_text(COMFORT)
            await asyncio.sleep(0.8)
            m2 = await talk(sess, "_teacher4.wav")         # 安慰
            seq.append(("warm", m2))
            print(f"  [跑{i} 回暖] 语速{m2['cps']:>5} 基频{m2['f0']:>6} 能量{m2['rms']:.4f}"
                  f"  「{m2['text'][:30]}」", flush=True)
        finally:
            await sess.close()
        out.append({"run": i, "seq": [{"stage": s, **m} for s, m in seq]})
    return out


def summarize(mode: str, data: list) -> None:
    print("\n=== 汇总 ===")
    if mode == "a":
        print(f"{'档位':<5}{'字数':>6}{'语速':>7}{'基频':>8}{'能量':>9}")
        for level in LEVELS:
            rows = [x["r2"] for x in data if x["level"] == level]
            if not rows:
                continue
            med = {k: st.median([r[k] for r in rows]) for k in ("chars", "cps", "f0", "rms")}
            print(f"{level:<5}{med['chars']:>6.0f}{med['cps']:>7.2f}{med['f0']:>8.1f}{med['rms']:>9.4f}")
    elif mode == "b":
        print(f"{'轮次':<5}{'字数':>6}{'语速':>7}{'基频':>8}{'能量':>9}")
        for idx in range(5):
            rows = [x["rounds"][idx] for x in data]
            med = {k: st.median([r[k] for r in rows]) for k in ("chars", "cps", "f0", "rms")}
            print(f"{idx + 1:<5}{med['chars']:>6.0f}{med['cps']:>7.2f}{med['f0']:>8.1f}{med['rms']:>9.4f}")
    elif mode == "c":
        print(f"{'阶段':<6}{'字数':>6}{'语速':>7}{'基频':>8}{'能量':>9}")
        for stage in ("base", "low", "warm"):
            rows = [next(s for s in x["seq"] if s["stage"] == stage) for x in data]
            med = {k: st.median([r[k] for r in rows]) for k in ("chars", "cps", "f0", "rms")}
            print(f"{stage:<6}{med['chars']:>6.0f}{med['cps']:>7.2f}{med['f0']:>8.1f}{med['rms']:>9.4f}")


async def main() -> int:
    if not settings.realtime_configured:
        print("未配置实时语音")
        return 1
    mode = (sys.argv[1] if len(sys.argv) > 1 else "a").lower()
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    print(f"模式 {mode.upper()}，每组 {runs} 次\n")
    if mode == "a":
        data = await run_a(runs)
    elif mode == "b":
        data = await run_b(runs)
    elif mode == "c":
        data = await run_c(runs)
    else:
        print("模式只有 a / b / c")
        return 1

    (DATA / f"_exp_{mode}_results.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    summarize(mode, data)
    print(f"\n明细：data/_exp_{mode}_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
