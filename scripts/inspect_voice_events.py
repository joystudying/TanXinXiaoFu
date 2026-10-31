# -*- coding: utf-8 -*-
"""检查真双工验证拿到的事件与音频（把证据摊开）。

读 data/_voice_events.json 与 data/_student_reply.pcm，输出：
  - 老师那句话被识别成了什么
  - 学生回复的文本
  - 学生音频的能量（判断是真人语音还是静音）

注意：火山实时语音的**下行音频是 32 位浮点 PCM（float32，24kHz，单声道）**，
上行才是 16 位整数。按 int16 解读会变成噪音——这个坑踩过一次。
"""
import json
import math
import struct
import wave
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data"


def float32_to_int16(pcm: bytes, target_peak_dbfs: float = -3.0) -> bytes:
    """float32 PCM → int16 PCM，并做响度归一化。

    火山实时语音的输出电平偏低（实测 RMS 约 −39 dBFS），直接播会显得声音小。
    这里把峰值拉到 −3 dBFS；前端播放时同样要加增益，否则听感不一致。
    """
    n = len(pcm) // 4
    vals = struct.unpack("<%df" % n, pcm[: n * 4])
    peak = max((abs(v) for v in vals), default=0.0)
    gain = 1.0
    if peak > 0:
        target = 10 ** (target_peak_dbfs / 20)
        gain = min(target / peak, 8.0)      # 最多放大 8 倍，避免把噪声抬起来
    out = bytearray()
    for v in vals:
        out.extend(struct.pack("<h", int(max(-1.0, min(1.0, v * gain)) * 32767)))
    return bytes(out)


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
        print("  (文字直接在音频里)")

    raw = (ROOT / "_student_reply.pcm").read_bytes()
    n = len(raw) // 4
    vals = struct.unpack("<%df" % n, raw[: n * 4])
    rms = math.sqrt(sum(v * v for v in vals) / n)
    peak = max(abs(v) for v in vals)

    print("\n=== 学生音频检查（按 float32 解读）===")
    print(f"  样本 {n} 个 ≈ {n / 24000:.1f} 秒 @24kHz")
    print(f"  峰值={peak:.4f}  RMS={rms:.4f}")
    print(f"  折算 dBFS：峰值 {20 * math.log10(peak + 1e-9):.1f} dB，"
          f"RMS {20 * math.log10(rms + 1e-9):.1f} dB")
    print("  火山文档要求人声 RMS 约 −31.7 ~ −23.9 dBFS")

    wav = ROOT / "_student_reply.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(float32_to_int16(raw))
    print(f"\n  已转存 {wav.name}（float32→int16，峰值归一化到 −3 dBFS），可双击试听")

    print("\n=== 事件分布（前 8）===")
    c = Counter(e.get("event") for e in events if e.get("type") == "event")
    for k, v in sorted(c.items(), key=lambda x: -x[1])[:8]:
        print(f"  event {k}: {v} 次")


if __name__ == "__main__":
    main()
