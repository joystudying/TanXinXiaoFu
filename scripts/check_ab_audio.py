# -*- coding: utf-8 -*-
"""检查 A/B 音频时长，判断 B 模式是不是"两句话都说了"。"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    rows = json.loads((DATA / "_ab_latency.json").read_text(encoding="utf-8"))
    print(f"{'次':<3}{'模式':<4}{'我们给的字数':>10}{'音频秒':>8}{'字/秒':>8}")
    for i, r in enumerate(rows, start=1):
        for mode in ("A", "B"):
            m = r[mode]
            sec = m.get("sec") or 0
            cps = m["chars"] / sec if sec else 0
            print(f"{i:<3}{mode:<4}{m['chars']:>10}{sec:>8.1f}{cps:>8.1f}")

    print("\n=== 判断 ===")
    a_sec = [r["A"]["sec"] for r in rows if r["A"]["sec"]]
    b_sec = [r["B"]["sec"] for r in rows if r["B"]["sec"]]
    if a_sec and b_sec:
        import statistics as st
        print(f"  A 中位时长 {st.median(a_sec):.1f} 秒，B 中位时长 {st.median(b_sec):.1f} 秒")
        print(f"  B/A = {st.median(b_sec) / st.median(a_sec):.2f}")
        print("  接近 1 说明 B 只说了模型自己的话（我们的台词没生效或被忽略）")
        print("  接近 2 说明模型的话和我们的话都念了（双重发声）")


if __name__ == "__main__":
    main()
