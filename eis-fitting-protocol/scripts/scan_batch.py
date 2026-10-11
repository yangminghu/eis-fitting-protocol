"""scan_batch.py — 多份数据批量核查（直接支撑 SKILL.md 的 E18）。

    python scan_batch.py <文件或目录> [更多...] [--starts=200] [--csv=spread.csv]

对每个文件：
  1) 体检（E1/E2/E4）：编码/分隔符/表头/点数/频率范围/|Z| 范围/Z'' 过零/弧数提示/噪声 σ
  2) 拟合（E8/E9）：eis_core.global_fit，报 best/valid 的 SSE 与最大残差、贴界与退化标记
  3) 汇总（E18）：各文件同一参数的组间离散度 + 谱内噪声对比，并打印结论级 JSON

纯 numpy/scipy 即可运行（不需要 pyimpspec）。数据文件只在本地读取，不写回。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from eis_core import (PARAM_NAMES, check_data, global_fit, quality)  # noqa: E402


def read_any(p: Path):
    """E1：编码探测 + 分隔符显式判定 + 表头判定。"""
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "gbk", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("无法解码")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("空文件")
    sep = max(("\t", ",", ";", "|"), key=lambda c: lines[0].count(c))
    if lines[0].count(sep) == 0:
        sep = "\t"
    rows = [ln.split(sep) for ln in lines]
    header = None

    def isnum(s):
        try:
            float(s)
            return True
        except ValueError:
            return False

    if not all(isnum(c) for c in rows[0][:3]):
        header = [c.strip() for c in rows[0]]
        rows = rows[1:]
    if len(rows[0]) < 3:
        raise ValueError(f"列数不足 3（探测到的分隔符 {sep!r}）")
    a = np.array([[float(x) for x in r[:3]] for r in rows])
    order = np.argsort(a[:, 0])[::-1]
    return ({"encoding": enc, "separator": {"\t": "\\t"}.get(sep, sep),
             "header": header, "headerless": header is None},
            a[order, 0], a[order, 1] + 1j * a[order, 2])


def extrema_hint(y, w=5):
    """弧数提示（**只是描述**，不是判据）：原始计数 + 滑动平均后的计数。"""
    raw = [i for i in range(1, len(y) - 1) if (y[i] - y[i - 1]) * (y[i + 1] - y[i]) < 0]
    if len(y) > w:
        ys = np.convolve(y, np.ones(w) / w, mode="same")
        sm = [i for i in range(1, len(ys) - 1)
              if (ys[i] - ys[i - 1]) * (ys[i + 1] - ys[i]) < 0]
    else:
        sm = raw
    return {"raw": len(raw), "smooth_w%d" % w: len(sm),
            "note": "仅作描述；弧数由 AICc + 分频段残差结构决定（SKILL E2/E12）"}


def one(p: Path, starts: int, seed: int = 0) -> dict:
    info, f, z = read_any(p)
    check_data(f, z)
    d = z.imag[1:-1] - 0.5 * (z.imag[:-2] + z.imag[2:])
    sig = float(np.std(d, ddof=1) / np.sqrt(1.5))
    cross = []
    for i in range(len(f) - 1):
        if z.imag[i] * z.imag[i + 1] < 0:
            t = z.imag[i] / (z.imag[i] - z.imag[i + 1])
            cross.append(float(10 ** (np.log10(f[i]) + t * (np.log10(f[i + 1]) - np.log10(f[i])))))
    out = {**info, "file": p.name, "n_points": int(f.size),
           "f_min_Hz": float(f.min()), "f_max_Hz": float(f.max()),
           "z_abs_min_ohm": float(np.abs(z).min()), "z_abs_max_ohm": float(np.abs(z).max()),
           "z_im_zero_cross_Hz": cross, "noise_sigma_im_ohm": sig,
           "arc_hint": extrema_hint(z.imag)}
    r = global_fit(f, z, n_starts=starts, seed=seed)
    out.update({"best_sse": r["best_sse"], "max_pct": r["quality"]["max_pct"],
                "rms_pct": r["quality"]["rms_pct"],
                "best_valid_max_pct": (r["best_valid_quality"] or {}).get("max_pct"),
                "on_hard_bound": r["params_on_hard_bound"],
                "outside_plausible_range": r["params_outside_plausible_range"],
                "n_distinct_spectrum": r["n_distinct_spectrum"],
                "params": dict(zip(PARAM_NAMES, map(float, r["best_params"])))})
    # 合格性（E16）：最大残差与噪声量级比较
    noise_pct = 100.0 * sig / float(np.abs(z).mean())
    out["noise_pct_of_mean_z"] = noise_pct
    out["adequate"] = bool(r["quality"]["max_pct"] <= max(10 * noise_pct, 0.5))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="多份 EIS 数据批量核查（E1/E2/E4/E8/E9/E16/E18）")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--starts", type=int, default=200)
    ap.add_argument("--csv", default=None, help="把逐文件参数写成 csv")
    a = ap.parse_args()

    files = []
    for q in a.paths:
        p = Path(q)
        files.extend(sorted(p.iterdir()) if p.is_dir() else [p])
    files = [p for p in files if p.is_file()]

    rows = []
    for p in files:
        try:
            rows.append(one(p, a.starts))
        except Exception as exc:
            rows.append({"file": p.name, "error": f"{type(exc).__name__}: {exc}"})
        print(json.dumps(rows[-1], ensure_ascii=False, default=str), flush=True)

    ok = [r for r in rows if "params" in r]
    if len(ok) >= 2:
        print("\n=== 组间离散度（E18）===")
        print(f"{'param':10} {'min':>12} {'median':>12} {'max':>12} {'极差/中位':>10}")
        for k in PARAM_NAMES:
            v = np.array([r["params"][k] for r in ok], float)
            med = float(np.median(v))
            rng = float(v.max() - v.min())
            print(f"{k:10} {v.min():12.5g} {med:12.5g} {v.max():12.5g} "
                  f"{(rng / med if med else float('nan')):10.2%}")
        npc = [r["noise_pct_of_mean_z"] for r in ok]
        print(f"\n谱内噪声（相对 |Z| 均值）：{min(npc):.3f}% – {max(npc):.3f}%")
        print(f"合格性（E16）：{sum(r['adequate'] for r in ok)}/{len(ok)} 份"
              f"最大残差 ≤ max(10×噪声, 0.5%)")
        print("提醒：组间差异才是主导不确定度；若各份给出的参数差异远大于谱内噪声，"
              "跨样品/跨状态的比较必须超过该离散度才有意义。")

    if a.csv:
        with Path(a.csv).open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["file"] + PARAM_NAMES + ["best_sse", "max_pct", "rms_pct", "adequate"])
            for r in ok:
                w.writerow([r["file"]] + [f"{r['params'][k]:.8g}" for k in PARAM_NAMES]
                           + [f"{r['best_sse']:.8g}", f"{r['max_pct']:.6g}",
                              f"{r['rms_pct']:.6g}", r["adequate"]])
        print("已写出:", a.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
