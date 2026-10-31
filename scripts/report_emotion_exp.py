# -*- coding: utf-8 -*-
"""把 emotion 实验结果摊开：逐次明细 + 分布重叠判断。"""
import json
import statistics as st
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    rows = json.loads((DATA / "_exp_results.json").read_text(encoding="utf-8"))

    print(f"{'条件':<4}{'次':<4}{'字数':>6}{'时长':>8}{'语速':>7}{'能量':>9}{'基频':>8}")
    for r in rows:
        m = r["r2"]
        print(f"{r['condition']:<4}{r['run']:<4}{m['chars']:>6}{m['sec']:>8.1f}"
              f"{m['cps']:>7.2f}{m['rms']:>9.4f}{m['f0']:>8.1f}")

    print("\n=== 分布与重叠 ===")
    for key, label, unit in (("chars", "字数", ""), ("cps", "语速", ""),
                             ("rms", "能量", ""), ("f0", "基频", "Hz")):
        c0 = [r["r2"][key] for r in rows if r["condition"] == "C0"]
        c1 = [r["r2"][key] for r in rows if r["condition"] == "C1"]
        med0, med1 = st.median(c0), st.median(c1)
        overlap = not (max(c1) < min(c0) or max(c0) < min(c1))
        delta = (med1 - med0) / med0 * 100 if med0 else 0
        print(f"  {label:<4} C0 {min(c0):.4g}~{max(c0):.4g} (中位 {med0:.4g})   "
              f"C1 {min(c1):.4g}~{max(c1):.4g} (中位 {med1:.4g})   "
              f"变化 {delta:+.0f}%   {'区间重叠' if overlap else '区间不重叠'}")

    print("\n=== 每轮原文 ===")
    for r in rows:
        print(f"[{r['condition']}{r['run']}] 轮1：{r['r1_text'][:50]}")
        print(f"      轮2：{r['r2_text'][:50]}")


if __name__ == "__main__":
    main()
