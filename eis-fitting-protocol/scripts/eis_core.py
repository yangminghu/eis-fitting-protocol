"""eis_core.py — EIS 等效电路拟合核心（主电路 [RL(RQ)(RQ)Wo]）

不要重写：元素公式与参数变换都做过回归验证。
  * 元素阻抗与 pyimpspec 5.2.0 官方实现一致（max 相对偏差 2.1e-16，见 --selftest）
  * 硬边界真的传给 least_squares（不是 np.clip）；撒点范围 ≠ 硬边界
  * 剖面似然把目标分量**从优化向量里删除**；profile 的 grid 是 θ 空间（用 to_theta）

用法
----
    from eis_core import global_fit, profile, to_theta, z_model, sse_rel
    out = global_fit(f, z, n_starts=300)            # f: Hz, z: Ω（复数，Z=Z'+jZ''）
    print(out["best_sse"], out["params_named"], out["params_on_hard_bound"])
    profile(f, z, 4, to_theta(4, [0.7, 0.85, 0.95]))   # 固定 n2 做剖面
    python eis_core.py --selftest                   # 自检（装了 pyimpspec 会做官方对照）

约定
----
p = [R1, L1, R2, Y2, n2, R3, Y3, n3, Yw, Bw]（+ nw，若 free_nwo=True）
残差 = (Z_fit − Z)/|Z|，实虚拼成向量；SSE_rel = Σ|ΔZ|²/|Z|²（L2，自写口径）
本模块只内置这一个电路；多模型比较（含多孔/传输线）走 pyimpspec 的 CDC 解析（z_cdc）。
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

PARAM_NAMES = ["R_1.R", "L_1.L", "R_2.R", "Q_1.Y", "Q_1.n",
               "R_3.R", "Q_2.Y", "Q_2.n", "Wo_1.Y", "Wo_1.B"]
PARAM_NAMES_FREE_NWO = PARAM_NAMES + ["Wo_1.n"]
EXP_IDX = (4, 7, 10)          # logit 变换（指数）的分量下标

# 起点云范围（只用来撒点；**不要**当硬边界）
START_LO = np.array([-4, -9, -1, -10, 0, -1, -10, 0, -4, -3], float)
START_HI = np.array([3, -4, 2.5, -1, 1, 2.5, -1, 1, 1, 6], float)
# 硬边界：正量 log10 ∈ [−12, 9]；指数 logit ∈ [−6, 6] ⇒ n ∈ 0.0025–0.9975
BOUND_LO = np.array([-12, -15, -12, -15, -6, -12, -15, -6, -12, -12], float)
BOUND_HI = np.array([9, 3, 9, 3, 6, 9, 3, 6, 6, 9], float)


# --------------------------------------------------------------------------- 元素
def z_rq(R, Y, n, w):
    """(RQ) 并联：1/(1/R + Y·(iω)^n)"""
    return 1.0 / (1.0 / R + Y * (1j * w) ** n)


def z_wo(Y, B, n, w):
    """有限长 Warburg（反射边界）。B 是**时间常数（s）**，拐点 f_cross ≈ 1/(2πB)。

    高频极限 = 1/[Y^n·(iω)^n]；要与 W = 1/[Y_W·(iω)^n] 对上须 Y_W = Y^n（不是 Y）。
    tanh 的实部裁到 ±40：|Re|>40 时 tanh 已是机器精度的 ±1，不裁会溢出告警。
    """
    x = (B * 1j * w) ** n
    return 1.0 / (np.tanh(np.clip(x.real, -40.0, 40.0) + 1j * x.imag)
                  * (Y * 1j * w) ** n)


def z_w(Y, n, w):
    """半无限 Warburg：1/(Y·(iω)^n)"""
    return 1.0 / (Y * (1j * w) ** n)


def z_g(Y, k, n, w):
    """Gerischer：1/(Y·(k + iω)^n)"""
    return 1.0 / (Y * (k + 1j * w) ** n)


def z_la(L, n, w):
    """非理想电感：L·(iω)^n"""
    return L * (1j * w) ** n


def z_model(p, f, free_nwo=False):
    """[RL(RQ)(RQ)Wo] 的阻抗。p 见模块 docstring。"""
    R1, L1, R2, Y2, n2, R3, Y3, n3, Yw, Bw = p[:10]
    nw = p[10] if free_nwo else 0.5
    w = 2 * np.pi * f
    return (R1 + 1j * w * L1 + z_rq(R2, Y2, n2, w) + z_rq(R3, Y3, n3, w)
            + z_wo(Yw, Bw, nw, w))


def element_index(circ):
    """建立 CDC 元素的**别名表**：`get_name()` 原名 + pyimpspec 拟合结果的 `<符号>_<k>` 名。

    ⚠️ 这是 v6 修掉的一个静默陷阱：`parse_cdc('[RL(RQ)(RQ)Wo]')` 的 `get_name()` 返回
    `'R','L','R','Q','R','Q','Wo'`（**有重名、且没有序号**），而 `fit_circuit` 的参数名是
    `'R_1','L_1','R_2','Q_1','R_3','Q_2','Wo_1'`（与 `PARAM_NAMES` 一致）。
    只按 `get_name()` 查表会让 `PARAM_NAMES` 全部对不上、**逐个跳过且不报错** ——
    参数注入变成空转（曾使 `compare_official` 的"官方对照 2.1e-16"成为无意义的恒等）。
    """
    seen, out = {}, {}
    for el in circ.get_elements(recursive=True):
        nm = el.get_name()
        out.setdefault(nm, el)
        sym = nm.split("_")[0]
        seen[sym] = seen.get(sym, 0) + 1
        out.setdefault(f"{sym}_{seen[sym]}", el)
    return out


def z_cdc(cdc, f, values=None):
    """任意 CDC 的阻抗（走 pyimpspec 解析；E12 多模型比较 / E13 多孔用这条路）。

    values: {"R_1.R": 20.0, "Q_1.n": 0.85, ...} —— 元素名用 `<符号>_<出现序号>`
            （与 `PARAM_NAMES` / `fit_circuit` 一致），也可用 CDC 里的自定义标签。
    **名字对不上会抛 KeyError**（不是静默跳过）：静默跳过会拿默认参数算出一条
    看似正常的谱，把"对照不上"误读成"两种实现不一致"。

    ⚠️ CDC 写法陷阱：元素标签必须写在花括号**里面**（`R{R=20:sol}` → 元素名 `R_sol`）；
    写成 `R_1{R=20}` 会抛 `InvalidElementSymbol`，`{R=20:1}` 会抛 `UnexpectedToken`。
    所以**推荐 CDC 不写标签**（`[RL(RQ)(RQ)Wo]`），用 `<符号>_<序号>` 注入即可。
    """
    from pyimpspec.circuit import parse_cdc

    circ = parse_cdc(cdc)
    if values:
        els = element_index(circ)
        missing = []
        for key, val in values.items():
            name, sym = key.rsplit(".", 1)
            el = els.get(name)
            if el is None:
                missing.append(key)
                continue
            el.set_values(**{sym: float(val)})
        if missing:
            raise KeyError(
                f"CDC {cdc!r} 里找不到这些元素：{missing}；可用别名 {sorted(els)}。"
                " 注意 CDC 标签要写进花括号内（R{R=20:sol} → 名 R_sol），"
                "`R_1{R=20}` 不是合法元素符号")
    return np.asarray(circ.get_impedances(np.asarray(f, float)))


# ------------------------------------------------------------------- 参数变换
def sig(x):
    """logistic；用 tanh 写法以免 exp 溢出（x→−∞ 时 exp(−x) 会溢出告警）。"""
    return 0.5 * (1.0 + np.tanh(0.5 * np.asarray(x, float)))


def unpack(th, free_nwo=False):
    """θ → 物理参数。边界由 least_squares(bounds=...) 施加；这里**不做 clip**
    （clip 会让越界区变成平坦目标面、Jacobian 该列为 0，比不加边界更糟）。"""
    th = np.asarray(th, float)
    p = [10 ** th[0], 10 ** th[1], 10 ** th[2], 10 ** th[3], sig(th[4]),
         10 ** th[5], 10 ** th[6], sig(th[7]), 10 ** th[8], 10 ** th[9]]
    if free_nwo:
        p.append(sig(th[10]))
    return np.array(p)


def _logit(x):
    x = np.clip(x, 1e-12, 1 - 1e-12)
    return np.log(x / (1 - x))


def pack(p, free_nwo=False):
    """物理参数 → θ（把已知解作为种子时用）。"""
    p = np.asarray(p, float)
    th = [np.log10(max(p[0], 1e-300)), np.log10(max(p[1], 1e-300)),
          np.log10(max(p[2], 1e-300)), np.log10(max(p[3], 1e-300)), _logit(p[4]),
          np.log10(max(p[5], 1e-300)), np.log10(max(p[6], 1e-300)), _logit(p[7]),
          np.log10(max(p[8], 1e-300)), np.log10(max(p[9], 1e-300))]
    if free_nwo:
        th.append(_logit(p[10]))
    return np.array(th)


def to_theta(idx, values, free_nwo=False):
    """**物理值**网格 → profile() 需要的 **θ 空间**网格（极易踩的坑）。

    指数分量（idx ∈ {4,7,10}）走 logit，正量走 log10：
        profile(f, z, 4, to_theta(4, [0.7, 0.85, 0.95]))
    直接把 0.85 当 grid 传进去，实际固定的是 sig(0.85)=0.70 —— 不报错、只是结果错。
    """
    return [float(_logit(v)) if idx in EXP_IDX else float(np.log10(v))
            for v in np.atleast_1d(values)]


def from_theta(idx, thetas, free_nwo=False):
    """θ 空间网格 → 物理值（报告剖面横轴时用，to_theta 的逆）。"""
    return [float(sig(v)) if idx in EXP_IDX else float(10 ** v)
            for v in np.atleast_1d(thetas)]


def sse_rel(p, f, z, free_nwo=False):
    """Σ|Z_fit − Z|²/|Z|²（modulus 口径的 L2 目标；报告时与拟合目标分开写）。"""
    zf = z_model(p, f, free_nwo)
    if not (np.isfinite(zf.real).all() and np.isfinite(zf.imag).all()):
        return np.inf
    return float(np.sum(np.abs(zf - z) ** 2 / np.abs(z) ** 2))


def quality(p, f, z, free_nwo=False):
    zf = z_model(p, f, free_nwo)
    rel = np.abs(zf - z) / np.abs(z)
    return {"sse_rel": float(np.sum(rel ** 2)),
            "rms_pct": float(np.sqrt(np.mean(rel ** 2)) * 100),
            "max_pct": float(rel.max() * 100)}


# --------------------------------------------------------------- 多起点全局拟合
def _bound_report(th, b_lo, b_hi, names, start_lo=None, start_hi=None,
                  hard_tol=1e-3, warn_tol=1.0):
    """贴界与退化情况。判定口径全部写进 JSON，避免"12 个数量级贴底却没被报出来"。

    * hard      —— 真的压在**硬边界**上（θ 距离 ≤ hard_tol）
    * warn      —— 距硬边界 ≤ warn_tol（1 个 log10 / 1 个 logit 单位）
    * dist      —— 各分量到最近硬边界的 θ 距离
    * outside   —— **正量**分量的 θ 跑出"物理合理撒点窗口"（START_LO/HI）之外 ⇒ 事实退化
                   （例：某串联电阻被推到比合理窗口低 8 个数量级、距硬下界却还差 0.65 个 log10，
                   硬边界判据抓不到，但它跑出了撒点窗口 ⇒ 被这里抓到）
    """
    hard, warn, dist, outside = [], [], {}, []
    for i, name in enumerate(names):
        d = float(min(abs(th[i] - b_lo[i]), abs(th[i] - b_hi[i])))
        dist[name] = d
        if d <= hard_tol:
            hard.append(name)
        elif d <= warn_tol:
            warn.append(name)
        if (start_lo is not None and i not in EXP_IDX
                and (th[i] < start_lo[i] or th[i] > start_hi[i])):
            outside.append(name)
    return hard, warn, dist, outside


def _is_on_bound(p, free_nwo, b_lo, b_hi, hard_tol=1e-3):
    th = pack(p, free_nwo)
    return any(min(abs(th[i] - b_lo[i]), abs(th[i] - b_hi[i])) <= hard_tol
               for i in range(th.size))


def check_data(f, z, n_param=None, strict=True):
    """输入体检（E1 的可执行版）。全部是**真错误**，不是可调的宽容项。

    报出：长度不一致 / 空 / 非一维 / 非有限值 / 频率非正 / 频率重复 /
    |Z| 含 0 / 自由度不足（2N ≤ 参数个数）；`strict=False` 时只返回问题清单不抛。

    为什么要在这里拦：这些情况在旧版会以 `ValueError: zero-size array to reduction...`、
    `best_sse=inf`、或"10 个参数拟合 1 个点得到 SSE=1e-23"这类**看似成功**的方式出现，
    属于"静默错误"，比直接报错危险得多。
    """
    f = np.asarray(f, float)
    z = np.asarray(z, complex)
    bad = []
    if f.ndim != 1 or z.ndim != 1:
        bad.append("f 与 z 必须是一维数组")
    elif f.shape != z.shape:
        bad.append(f"f 与 z 长度不一致（{f.shape} vs {z.shape}）")
    else:
        if f.size == 0:
            bad.append("数据为空")
        if not (np.isfinite(f).all() and np.isfinite(z.real).all()
                and np.isfinite(z.imag).all()):
            bad.append("含 NaN/Inf")
        if f.size and not (f > 0).all():
            bad.append("含非正频率（需 f > 0，单位 Hz）")
        if f.size and len(np.unique(f)) != f.size:
            bad.append("存在重复频率（同一频点出现多次会破坏拟合与 K-K 前提）")
        if f.size and not (np.abs(z) > 0).all():
            bad.append("含 |Z| = 0 的点（相对残差会除零）")
        if n_param is not None and f.size and 2 * f.size <= n_param:
            bad.append(f"自由度不足：2N={2 * f.size} 不大于参数个数 {n_param}"
                       "（欠定拟合会给出无意义的结果）")
    if bad and strict:
        raise ValueError("输入数据不满足拟合前提：" + "；".join(bad)
                         + "。请先按 SKILL E1/E2 做数据体检。")
    return bad


def _jac_analytic(th, w, free_nwo=False):
    """解析 Jacobian dZ/dθ（[n_freq, n_param]）；`--selftest` 会对它做数值校验。

    RQ：Z=1/(1/R+Y·s)、s=(jω)^n ⇒ ∂Z/∂R=Z²/R²、∂Z/∂Y=−Z²s、∂Z/∂n=−Z²·Y·s·ln(jω)
    Wo：Z=1/(tanh(x)·Y^n·u)、x=(Bjω)^n、u=(jω)^n
        ∂Z/∂Y=−nZ/Y、∂Z/∂B=−Z²·Y^n·u²·n·B^(n−1)·sech²x
        ∂Z/∂n=Z·[−x·sech²x/tanh(x)·ln(Bjω) − ln(Yjω)]
    链式因子：正量 dp/dθ=p·ln10，指数 dn/dθ=n(1−n)。
    """
    ln10 = np.log(10.0)
    R1, L1, R2, Y2, n2 = 10 ** th[0], 10 ** th[1], 10 ** th[2], 10 ** th[3], sig(th[4])
    R3, Y3, n3 = 10 ** th[5], 10 ** th[6], sig(th[7])
    Yw, Bw = 10 ** th[8], 10 ** th[9]
    nw = sig(th[10]) if free_nwo else 0.5
    jw = 1j * w
    J = np.zeros((w.size, 11 if free_nwo else 10), complex)

    J[:, 0] = ln10 * R1
    J[:, 1] = ln10 * L1 * jw
    for Rk, Yk, nk, ir, iy, iN in ((R2, Y2, n2, 2, 3, 4), (R3, Y3, n3, 5, 6, 7)):
        s = jw ** nk
        Zq = 1.0 / (1.0 / Rk + Yk * s)
        J[:, ir] += ln10 * Rk * Zq ** 2 / Rk ** 2
        J[:, iy] += ln10 * Yk * (-(Zq ** 2) * s)
        J[:, iN] += nk * (1 - nk) * (-(Zq ** 2) * Yk * s * np.log(jw))
    u = jw ** nw
    x = (Bw * jw) ** nw
    t = np.tanh(np.clip(x.real, -40.0, 40.0) + 1j * x.imag)
    Zw = 1.0 / (t * (Yw ** nw) * u)
    sech2 = 1.0 - t ** 2
    J[:, 8] += ln10 * Yw * (-nw * Zw / Yw)
    J[:, 9] += ln10 * Bw * (-(Zw ** 2) * (Yw ** nw) * (u ** 2) * nw
                            * (Bw ** (nw - 1)) * sech2)
    if free_nwo:
        J[:, 10] = nw * (1 - nw) * Zw * (-x * sech2 / t * np.log(Bw * jw)
                                         - np.log(Yw * jw))
    return J


def global_fit(f, z, n_starts=300, free_nwo=False, r1_bounds=None, seed=0,
               known=None, dedup_rtol=0.05, dedup_spec_rtol=1e-6,
               two_stage=True, refine_top=20, screen_nfev=1000, screen_tol=1e-4,
               max_nfev=5000, tol=1e-12, jac="2-point"):
    """多起点拟合。返回 dict。

    只能写"**已发现的最低 SSE**"+去重后的解族，不要写"确认全局最优"（有限次局部优化证明不了）。

    known: 已知解（物理参数向量）→ 作为 starts[0]，逐分量裁剪到硬边界内（不整条丢弃）。

    **速度**（实测）：默认走**两阶段**——① 全部起点用**松容差**粗筛
    （`screen_tol=1e-4`、`screen_nfev=1000`）；② 把粗筛解按阻抗口径粗去重后，
    只对最好的 `refine_top` 个**盆地代表**用紧容差精修（`tol=1e-12`、`max_nfev=5000`）。
    既保留全起点覆盖，又不再为"从第 1 步就没希望"的起点跑满 20000 次评估。
    实测：同一 `seed` 下 `best_sse` 与单阶段完全一致
    （差 ~1e-14），耗时降到约 1/2–1/6。`jac="analytic"` 用解析 Jacobian
    （省掉每轮 n_param+1 次差分评估），**在病态起点多的问题上反而可能更慢**
    （精确 Jacobian 会让 TRF 走更多小步），故默认仍为 `"2-point"`；
    `--selftest` 对解析 Jacobian 做数值校验（列归一化误差 < 1e-9）。
    ⚠️ **不做多进程**：Windows 是 spawn，从脚本/REPL 直接调用会因缺
    `if __name__ == "__main__":` 抛 `RuntimeError`（实测）；要并行请自行在脚本里包主模块。

    去重报两个口径：
      * n_distinct          —— 参数口径（np.allclose, rtol=dedup_rtol）
      * n_distinct_spectrum —— 阻抗口径（max|ΔZ|/|Z| < dedup_spec_rtol）：不可辨识方向上的
        参数漂移不算新解。**报"解族"要看后者**。

    **最低 SSE 可能来自退化解**：必须同时看 `best_valid_*`（无贴界解）与
    `params_outside_plausible_range`（跑出物理合理窗口，如 R1→0），别只报 best_sse。
    """
    f = np.asarray(f, float)
    z = np.asarray(z, complex)
    check_data(f, z, 11 if free_nwo else 10)
    lo, hi = START_LO.copy(), START_HI.copy()
    b_lo, b_hi = BOUND_LO.copy(), BOUND_HI.copy()
    if free_nwo:
        lo, hi = np.append(lo, -1), np.append(hi, 1)
        b_lo, b_hi = np.append(b_lo, -6), np.append(b_hi, 6)
    if r1_bounds:                      # R1 的物理约束：同时作用于撒点范围与硬边界
        lo[0], hi[0] = np.log10(r1_bounds[0]), np.log10(r1_bounds[1])
        b_lo[0], b_hi[0] = lo[0], hi[0]

    rng = np.random.default_rng(seed)
    starts = [rng.uniform(lo, hi) for _ in range(n_starts)]
    if known is not None:
        th_known = pack(np.asarray(known, float), free_nwo)
        th_clipped = np.clip(th_known, b_lo + 1e-12, b_hi - 1e-12)
        starts[0] = th_clipped
        n_clip = int(np.sum(np.abs(th_clipped - th_known) > 1e-6))
        print(f"    seeded start 0 with the known solution"
              f"{f' ({n_clip} component(s) clipped to bounds)' if n_clip else ''}")

    def resid(th):
        zf = z_model(unpack(th, free_nwo), f, free_nwo)
        if not (np.isfinite(zf.real).all() and np.isfinite(zf.imag).all()):
            return np.full(2 * len(f), 1e6)
        d = (zf - z) / np.abs(z)
        return np.concatenate([d.real, d.imag])

    def solve(th0, tol_, maxn, use_jac):
        r = least_squares(resid, th0,
                          jac=(lambda x: _jac_analytic(x, w, free_nwo)) if use_jac else "2-point",
                          method="trf", x_scale="jac", bounds=(b_lo, b_hi),
                          ftol=tol_, xtol=tol_, gtol=tol_, max_nfev=maxn)
        p = unpack(r.x, free_nwo)
        return sse_rel(p, f, z, free_nwo), p

    sols = []
    if two_stage:
        rough = []
        for th0 in starts:
            try:
                rough.append(solve(th0, screen_tol, screen_nfev, False))
            except Exception:
                continue
        rough.sort(key=lambda t: t[0])
        # 粗筛解去重后再精修：保证精修的是**不同的盆地**，而不是同一盆地的 20 个副本
        reps = []
        for s, p in rough:
            if not any(np.max(np.abs(z_model(p, f, free_nwo)
                                    - z_model(q, f, free_nwo)) / np.abs(z)) < 1e-2
                       for _sq, q in reps):
                reps.append((s, p))
        n_screen = len(rough)
        chosen = reps[:max(1, refine_top)]
        # 保证至少精修一个"粗解不贴硬边界"的代表，否则 best_valid_* 可能全为 None
        if chosen and all(_is_on_bound(p, free_nwo, b_lo, b_hi) for _s, p in chosen):
            extra = next((r for r in reps[len(chosen):]
                          if not _is_on_bound(r[1], free_nwo, b_lo, b_hi)), None)
            if extra is not None:
                chosen = chosen + [extra]
        for _s, p in chosen:
            try:
                sols.append(solve(pack(p, free_nwo), tol, max_nfev, jac == "analytic"))
            except Exception:
                continue
    else:
        n_screen = 0
        for th0 in starts:
            try:
                sols.append(solve(th0, tol, max_nfev, jac == "analytic"))
            except Exception:
                continue

    sols.sort(key=lambda t: t[0])
    uniq = []
    for s, p in sols:
        if not any(np.allclose(p, q, rtol=dedup_rtol, atol=1e-12) for _, q in uniq):
            uniq.append((s, p))
    zp = [z_model(p, f, free_nwo) for _, p in sols]
    uniq_spec = []
    for i, (s, p) in enumerate(sols):
        if not any(np.max(np.abs(zp[i] - zp[j]) / np.abs(z)) < dedup_spec_rtol
                   for j in uniq_spec):
            uniq_spec.append(i)

    names = PARAM_NAMES_FREE_NWO if free_nwo else PARAM_NAMES
    valid = [(s, p) for s, p in sols if not _is_on_bound(p, free_nwo, b_lo, b_hi)]
    best_sse, best_p = (sols[0] if sols else (np.inf, None))
    v_sse, v_p = (valid[0] if valid else (np.inf, None))
    hard, warn, dist, outside = ([], [], {}, [])
    v_hard, v_warn, v_dist, v_outside = ([], [], {}, [])
    if sols:
        hard, warn, dist, outside = _bound_report(
            pack(sols[0][1], free_nwo), b_lo, b_hi, names, lo, hi)
    if v_p is not None:
        v_hard, v_warn, v_dist, v_outside = _bound_report(
            pack(v_p, free_nwo), b_lo, b_hi, names, lo, hi)
    return {
        "n_starts": n_starts, "n_converged": len(sols),
        "n_screened_converged": n_screen, "n_refined": len(sols),
        "two_stage": bool(two_stage), "refine_top": int(refine_top),
        "n_distinct": len(uniq), "n_distinct_spectrum": len(uniq_spec),
        "best_sse": float(best_sse), "best_params": best_p,
        "params_named": (dict(zip(names, map(float, best_p)))
                         if best_p is not None else None),
        "quality": (quality(best_p, f, z, free_nwo) if best_p is not None else None),
        "best_valid_sse": float(v_sse), "best_valid_params": v_p,
        "best_valid_quality": (quality(v_p, f, z, free_nwo) if v_p is not None else None),
        "n_on_bound_solutions": int(sum(1 for s, p in sols
                                        if _is_on_bound(p, free_nwo, b_lo, b_hi))),
        "distinct": [(float(s), p) for s, p in uniq[:10]],
        "distinct_spectrum": [(float(sols[j][0]), sols[j][1]) for j in uniq_spec[:10]],
        "top_solutions": [{"sse": float(sols[j][0]),
                           "quality": quality(sols[j][1], f, z, free_nwo),
                           "on_hard_bound": _bound_report(pack(sols[j][1], free_nwo),
                                                          b_lo, b_hi, names, lo, hi)[0],
                           "outside_plausible_range": _bound_report(
                               pack(sols[j][1], free_nwo), b_lo, b_hi, names, lo, hi)[3],
                           "params": [float(x) for x in sols[j][1]]}
                          for j in uniq_spec[:5]],
        # 下列四个字段描述 **best_params（最低 SSE 解）**；带 valid_ 前缀的描述无贴界解
        "params_on_hard_bound": hard,
        "params_within_1_of_bound": warn,
        "bound_distance_theta": dist,
        "params_outside_plausible_range": outside,
        "best_valid_params_on_hard_bound": v_hard,
        "best_valid_params_within_1_of_bound": v_warn,
        "best_valid_bound_distance_theta": v_dist,
        "best_valid_params_outside_plausible_range": v_outside,
        "reporting_convention": ("硬边界 = 正量 log10∈[−12,9] / 指数 logit∈[−6,6]；"
                                 "平凡退化 = 正量跑出撒点窗口 START_LO/HI 之外；"
                                 "无前缀字段描述 best_params，valid_ 前缀描述 best_valid_params；"
                                 "two_stage=True 时 n_converged/n_distinct 只统计**精修后**的解"
                                 "（先按阻抗口径 1e-2 粗去重再精修，保证覆盖不同盆地），"
                                 "n_screened_converged 是粗筛阶段收敛的起点数"),
        "claim": "lowest-found-only",   # 只能这样写；不要写"全局最优"
    }


# ------------------------------------------------------------------ 剖面似然
def profile(f, z, target_idx, grid, free_nwo=False, n_starts=16, r1_bounds=None,
            seed=0, known=None, two_stage=True, refine_top=6,
            screen_nfev=300, screen_tol=1e-6, max_nfev=5000, tol=1e-12):
    """真剖面：把 target_idx **从优化向量里删除**（不是只把初值钉住）。

    ⚠️ `grid` 是 **θ 空间**的值，不是物理值，用 `to_theta(idx, [物理值...])` 生成；
       报告横轴用 `from_theta(idx, grid)` 换回物理值。

    known: 已知解 → 作为每个网格点的首个起点（其余随机），否则全靠随机起点。
    速度：与 `global_fit` 同口径的两阶段（粗筛 `n_starts` 个 → 精修最好的 `refine_top` 个）。
    """
    f = np.asarray(f, float)
    z = np.asarray(z, complex)
    check_data(f, z, (11 if free_nwo else 10) - 1)   # 剖面容掉一个参数
    npar = 11 if free_nwo else 10
    if not (-npar <= target_idx < npar):
        raise ValueError(f"target_idx 越界：{target_idx}（参数个数 {npar}）")
    lo, hi = START_LO.copy(), START_HI.copy()
    b_lo, b_hi = BOUND_LO.copy(), BOUND_HI.copy()
    if free_nwo:
        lo, hi = np.append(lo, -1), np.append(hi, 1)
        b_lo, b_hi = np.append(b_lo, -6), np.append(b_hi, 6)
    if r1_bounds:
        lo[0], hi[0] = np.log10(r1_bounds[0]), np.log10(r1_bounds[1])
        b_lo[0], b_hi[0] = lo[0], hi[0]
    keep = [i for i in range(lo.size) if i != target_idx]
    th_seed = pack(np.asarray(known, float), free_nwo) if known is not None else None
    out = []
    for v in grid:
        rng = np.random.default_rng(seed)
        cand = []
        for k in range(n_starts):
            th0 = (th_seed.copy() if (k == 0 and th_seed is not None)
                   else rng.uniform(lo, hi))
            th0[target_idx] = v
            cand.append(th0)

        def make_resid(th0):
            def resid_free(th_free, th0=th0, v=v, keep=keep, target_idx=target_idx):
                th = th0.copy()
                th[keep] = th_free
                th[target_idx] = v
                zf = z_model(unpack(th, free_nwo), f, free_nwo)
                if not (np.isfinite(zf.real).all() and np.isfinite(zf.imag).all()):
                    return np.full(2 * len(f), 1e6)
                d = (zf - z) / np.abs(z)
                return np.concatenate([d.real, d.imag])
            return resid_free

        def run_free(th0, tol_, maxn):
            r = least_squares(make_resid(th0), th0[keep], method="trf", x_scale="jac",
                              bounds=(b_lo[keep], b_hi[keep]),
                              ftol=tol_, xtol=tol_, gtol=tol_, max_nfev=maxn)
            th_full = th0.copy()
            th_full[keep] = r.x
            return sse_rel(unpack(th_full, free_nwo), f, z, free_nwo)

        # 两阶段：先粗筛全部起点，再精修最好的 refine_top 个（同 global_fit 的口径）
        rough = []
        for th0 in cand:
            try:
                rough.append((run_free(th0, screen_tol, screen_nfev), th0))
            except Exception:
                continue
        rough.sort(key=lambda t: t[0])
        best = None
        for _s, th0 in rough[:max(1, refine_top)]:
            try:
                s = run_free(th0, tol, max_nfev)
            except Exception:
                continue
            th_full = th0.copy()
            th_full[target_idx] = v
            full = unpack(th_full, free_nwo)
            if best is None or s < best[0]:
                best = (s, full, v)
        out.append((v, best))
    return out


# ---------------------------------------------------------------- 官方实现对照
def compare_official(cdc, p, f, free_nwo=False):
    """本模块的 Z 与 pyimpspec 官方元素的 Z 逐点比较（独立性校验，E10）。

    `p` 用 `PARAM_NAMES` 顺序；CDC 建议写不带标签的 `[RL(RQ)(RQ)Wo]`（元素名由
    `element_index` 提供 `<符号>_<序号>` 别名）。返回 max 相对偏差；未安装 pyimpspec
    时返回 None。**参数名对不上会抛 KeyError**（不静默降级）——静默跳过会退化成
    "拿 CDC 内联初值算一遍再和自身比"，得到无意义的 1e-16。
    `--selftest` 里配了"注入敏感性"对照来证明这个比较不是空转。
    """
    try:
        import pyimpspec  # noqa: F401
    except Exception:
        return None
    names = PARAM_NAMES_FREE_NWO if free_nwo else PARAM_NAMES
    values = dict(zip(names, map(float, p)))
    zoff = z_cdc(cdc, f, values)
    return float(np.max(np.abs(z_model(p, f, free_nwo) - zoff) / np.abs(zoff)))


# ---------------------------------------------------------------------- 自检
def _selftest():
    print("=" * 78)
    print("eis_core selftest")
    f = np.logspace(6, -1, 61)
    TRUE = np.array([20.0, 8.8e-7, 12.0, 7.1e-6, 0.85, 5.6, 4.0e-8, 0.95, 1.37e-3, 2.92])
    z = z_model(TRUE, f)
    print(f"[1] 合成数据 |Z| = {abs(z).min():.3f} .. {abs(z).max():.3f} Ω，{len(f)} 点")

    out = global_fit(f, z, n_starts=40, seed=1)
    p, q = out["best_params"], out["quality"]
    print(f"[2] 多起点：收敛 {out['n_converged']}/{out['n_starts']}，去重 "
          f"参数口径 {out['n_distinct']} / 阻抗口径 {out['n_distinct_spectrum']}；"
          f"SSE={out['best_sse']:.3e}，max={q['max_pct']:.4f}%")
    vq = out["best_valid_quality"]
    print(f"    无贴界解：{'SSE=%.3e，max=%.4f%%' % (out['best_valid_sse'], vq['max_pct']) if vq else '（本组起点里没有无贴界解，须增大 refine_top 或改模型）'}"
          f"；贴界解 {out['n_on_bound_solutions']}/{out['n_converged']}")
    print(f"    参数：R1={p[0]:.4f} L1={p[1]:.3e} R2={p[2]:.4f} Y2={p[3]:.3e} n2={p[4]:.4f} | "
          f"R3={p[5]:.4f} Y3={p[6]:.3e} n3={p[7]:.4f} | Yw={p[8]:.3e} Bw={p[9]:.4f}")
    # 串联 RQ 块可互换 → 按集合比较
    got = sorted([(round(p[2], 4), round(p[3], 12), round(p[4], 4)),
                  (round(p[5], 4), round(p[6], 12), round(p[7], 4))])
    want = sorted([(12.0, 7.1e-6, 0.85), (5.6, 4.0e-8, 0.95)])
    ok_rec = (abs(p[0] - 20) < 1e-2 and q["max_pct"] < 1e-3
              and all(abs(a[0] - b[0]) < 1e-2 and abs(a[1] - b[1]) / b[1] < 1e-3
                      and abs(a[2] - b[2]) < 2e-3 for a, b in zip(got, want)))
    print(f"[3] 参数回收（含 RQ 置换对称）：{'PASS' if ok_rec else 'FAIL'}"
          f"；贴硬边界（应为空）：{out['params_on_hard_bound']}"
          f"；距边界 ≤1：{out['params_within_1_of_bound']}"
          f"；跑出合理窗口（应为空）：{out['params_outside_plausible_range']}"
          f"；valid 解贴界：{out['best_valid_params_on_hard_bound']}")

    # [3b] 解析 Jacobian：与中心差分逐列对比（列归一化误差），比的是 dZ/dθ
    th = pack(TRUE)
    w = 2 * np.pi * f
    Jan = _jac_analytic(th, w)

    def _Z(x):
        return z_model(unpack(x), f)
    jerr = 0.0
    for i in range(th.size):
        h = 1e-6 * max(1.0, abs(th[i]))
        dp = np.zeros(th.size)
        dp[i] = h
        fd = (_Z(th + dp) - _Z(th - dp)) / (2 * dp[i])
        jerr = max(jerr, float(np.max(np.abs(Jan[:, i] - fd)))
                   / max(float(np.max(np.abs(Jan[:, i]))), 1e-30))
    print(f"[3b] 解析 Jacobian vs 中心差分：列归一化误差 {jerr:.2e} "
          f"{'PASS' if jerr < 1e-6 else 'FAIL'}")
    ok_jac = jerr < 1e-6

    grid = to_theta(4, [0.7, 0.85, 0.95])
    prof = profile(f, z, 4, grid, n_starts=24, seed=2)
    shown = [(from_theta(4, [v])[0], b[0] if b else float("nan")) for v, b in prof]
    best_sse = min(s for _, s in shown)
    ok_prof = best_sse < 1e-25
    print(f"[4] 剖面似然（固定 n2=0.7/0.85/0.95，24 起点）："
          + ", ".join(f"{n:.2f}→SSE {s:.3e}" for n, s in shown))
    print(f"    {'PASS' if ok_prof else 'FAIL'}（固定到真值 0.85 应回到 ~1e-30；"
          f"实测最小 {best_sse:.3e}）——grid 是 θ 空间，报告横轴要 from_theta 换回物理值")

    # [5] 官方实现对照：CDC **不带内联初值**，参数只能靠注入 ⇒ 注入失效会立刻暴露
    bad = TRUE.copy()
    bad[0] = 9999.0                      # 一个差别极大的参数集
    try:
        vals_t = dict(zip(PARAM_NAMES, map(float, TRUE)))
        vals_b = dict(zip(PARAM_NAMES, map(float, bad)))
        z_t, z_b = z_cdc("[RL(RQ)(RQ)Wo]", f, vals_t), z_cdc("[RL(RQ)(RQ)Wo]", f, vals_b)
        move = float(np.max(np.abs(z_b - z_t) / np.abs(z_t)))
        diff = compare_official("[RL(RQ)(RQ)Wo]", TRUE, f)
        diff_bad = compare_official("[RL(RQ)(RQ)Wo]", bad, f)
    except KeyError as exc:
        move = diff = diff_bad = None
        print(f"[5] 官方实现对照：FAIL（参数名对不上：{exc}）")
    if diff is None:
        print("[5] 官方实现对照：SKIP（未安装 pyimpspec）")
    else:
        ok_move = move > 1e2             # 注入确实改变谱 ⇒ 对照不是空转
        ok_off = diff < 1e-12 and diff_bad < 1e-12
        print(f"[5] 官方实现对照：max 相对偏差 {diff:.2e}（换到 R1=9999 Ω 仍是 "
              f"{diff_bad:.2e}）{'PASS' if ok_off else 'CHECK'}；"
              f"注入敏感性 {move:.2e} {'PASS' if ok_move else 'FAIL（注入没生效＝对照空转）'}")
    ok = ok_rec and ok_prof and ok_jac and (diff is None or (diff < 1e-12 and diff_bad < 1e-12
                                                             and move > 1e2))
    print("=" * 78)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv or len(sys.argv) == 1:
        raise SystemExit(_selftest())
    print(__doc__)
