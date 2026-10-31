# -*- coding: utf-8 -*-
"""检查真双工验证拿到的事件与音频（把证据摊开）。

读 data/_voice_events.json 与 data/_student_reply.pcm，输出：
  - 老师那句话被识别成了什么
  - 学生回复的文本
  - 学生音频的能量（判断是真人语音还是静音）
"""
import json
import struct
import wave
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    events = json.loads((ROOT / "_voice_events.json").read_text(encoding="utf-8"))

    asr, replies = [], []
    for e in events:
        payload = e.get("payload") or {}
        extra = payload.get("extra") or {}
        event = e.get("event")
        if event == 451:
            t = payload.get("text") or extra.get("origin_text")
            if isinstance(t, str) and t.strip():
                asr.append(t.strip())
        for key in ("text", "content", "reply"):
            v = payload.get(key)
            if isinstance(v, str) and v.strip():
                replies.append(v.strip())
                break

    print("=== 老师这句话被识别成 ===")
    if asr:
        # 逐帧结果会重复，去重保序后拼起来
        uniq = []
        for t in asr:
            if not uniq or uniq[-1] != t:
                uniq.append(t)
        print("  " + uniq[-1][:220])
    else:
        print("  (没有解析到 ASR 文本)")

    print("\n=== 学生回复文本 ===")
    seen = []
    for r in replies:
        if r not in seen:
            seen.append(r)
    for r in seen[:5]:
        print("  " + r[:200])
    if not seen:
        print("  (事件里没有单独的文字字段，回复已直接在音频里)")

    pcm_path = ROOT / "_student_reply.pcm"
    pcm = pcm_path.read_bytes()
    n = len(pcm) // 2
    vals = struct.unpack("<%dh" % n, pcm[: n * 2])
    rms = (sum(v * v for v in vals) / n) ** 0.5
    peak = max(abs(v) for v in vals)

    print("\n=== 学生音频检查 ===")
    print(f"  样本 {n} 个 ≈ {n / 24000:.1f} 秒 @24kHz")
    print(f"  RMS={rms:.0f}  峰值={peak}   （静音≈0；真人语音常见 RMS 1000~6000）")

    wav = ROOT / "_student_reply.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    print(f"  已转存 {wav.name}，可双击试听")

    print("\n=== 事件分布（前 8）===")
    c = Counter(e.get("event") for e in events if e.get("type") == "event")
    for k, v in sorted(c.items(), key=lambda x: -x[1])[:8]:
        print(f"  event {k}: {v} 次")


if __name__ == "__main__":
    main()
