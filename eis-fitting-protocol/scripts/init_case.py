"""init_case.py — 一键生成符合 SKILL.md §4 命名规范的案例目录骨架。

    python init_case.py <case_dir> [--case-name NAME]

生成（校验器应为 0 违规）：
    <case_dir>/
      data/          原始数据（自己拷进来，别改名）
      results/       s1_data_clean.csv（只有表头）/ s1_data_health.json / s2_kk_summary.json
                     s3_fit_rl-rq-rq-wo_modulus.json + _spectrum.csv / s4_ident_summary.json
                     s8_report_main.md / s9_env_versions.json / s9_manifest.json（含 sha256）
      work/          中间产物与校验报告
      scripts/       eis_core.py（拟合核心）+ run_fit.py（起步脚本）

下一步：python <技能包>/scripts/validate_eis_outputs.py <case_dir>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_KEYS = ["pyimpspec", "deareis", "lmfit", "numpy", "matplotlib", "scipy"]
STAGE_SCRIPT = {"s1": "scripts/s1_prepare.py", "s2": "scripts/s2_kk.py",
                "s3": "scripts/run_fit.py", "s4": "scripts/s4_identify.py",
                "s8": "(人工撰写)", "s9": "scripts/init_case.py"}
STAGE_CATEGORY = {"s1": "input", "s2": "data-validity", "s3": "fit", "s4": "uncertainty",
                  "s5": "model-comparison", "s6": "special", "s7": "cross-check",
                  "s8": "report", "s9": "environment"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def env_snapshot() -> dict:
    import importlib.metadata as md
    out = {"python": sys.version.split()[0]}
    for k in ENV_KEYS:
        try:
            out[k] = md.version(k)
        except Exception:
            out[k] = None
    return out


def envelope(stage, payload, script, case):
    return {"schema": "eis-fit-result/1", "stage": stage, "case": case,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {}, "code": {"script": script},
            "env": env_snapshot(), "status": "placeholder", "payload": payload}


RUN_FIT = '''"""起步脚本：读 results/s1_data_clean.csv，跑多起点拟合并打印结论级摘要。

    python scripts/run_fit.py [results/s1_data_clean.csv]
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eis_core import global_fit                     # noqa: E402

src = Path(sys.argv[1] if len(sys.argv) > 1 else "results/s1_data_clean.csv")
rows = list(csv.DictReader(src.open(encoding="utf-8-sig")))
f = np.array([float(r["f_Hz"]) for r in rows])
z = np.array([complex(float(r["Z_re_ohm"]), float(r["Z_im_ohm"])) for r in rows])
print(f"data: {len(f)} points, {f.min():.4g}-{f.max():.4g} Hz")

out = global_fit(f, z, n_starts=300)          # 9–12 个参数 ⇒ ≥300 起点
q = out["quality"]
print(json.dumps({"stage": "s3", "sse": out["best_sse"], "max_pct": q["max_pct"],
                  "rms_pct": q["rms_pct"],
                  "best_valid_sse": out["best_valid_sse"],
                  "best_valid_max_pct": (out["best_valid_quality"] or {}).get("max_pct"),
                  "n_on_bound_solutions": out["n_on_bound_solutions"],
                  "n_distinct": out["n_distinct"],
                  "n_distinct_spectrum": out["n_distinct_spectrum"],
                  "on_hard_bound": out["params_on_hard_bound"],
                  "within_1_of_bound": out["params_within_1_of_bound"],
                  "outside_plausible_range": out["params_outside_plausible_range"],
                  "valid_on_hard_bound": out["best_valid_params_on_hard_bound"],
                  "valid_outside_plausible_range":
                      out["best_valid_params_outside_plausible_range"]},
                 ensure_ascii=False))
# 若 best_sse 解贴硬边界或跑出物理合理窗口，结论必须改用 best_valid_* 并说明（SKILL.md E9/E16）
# TODO: 写入 results/s3_fit_<model>_<weight>.json（带信封）+ _spectrum.csv + _multistart.json，
#       并更新 s9_manifest.json 的 sha256（见 SKILL.md §4）
'''


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def build(case: Path, case_name: str) -> None:
    for sub in ("data", "results", "work", "scripts"):
        (case / sub).mkdir(parents=True, exist_ok=True)
    res = case / "results"

    with (res / "s1_data_clean.csv").open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(["f_Hz", "Z_re_ohm", "Z_im_ohm"])
    write_json(res / "s1_data_health.json", envelope("s1", {
        "note": "placeholder：填编码/分隔符/列头/是否取反及依据，点数、频率范围、"
                "|Z| 范围、Z'' 过零频率、Z'' 局部极值个数、噪声 σ(Re/Im)",
        "n_points": None, "f_min_Hz": None, "f_max_Hz": None, "log_equidistant": None,
        "z_im_zero_cross_Hz": None, "z_im_local_extrema": None,
        "encoding": None, "separator": None, "header": None, "sign_flipped": None,
        "noise_sigma_re_ohm": None, "noise_sigma_im_ohm": None},
        "scripts/s1_prepare.py", case_name))
    write_json(res / "s2_kk_summary.json", envelope("s2", {
        "note": "placeholder：填 M_mu_criterion/M_best_chi2/M_used、逐点 max 与 RMS 残差、"
                "Lin-KK 配置（Z/Y 两种表示法都要）",
        "M_used": None, "mu": None, "rms_pct": None, "max_re_pct": None, "max_im_pct": None,
        "config": {"test": None, "representation": None, "add_capacitance": None,
                   "add_inductance": None, "F_ext": None}}, "scripts/s2_kk.py", case_name))
    write_json(res / "s3_fit_rl-rq-rq-wo_modulus.json", envelope("s3", {
        "note": "placeholder：跑 scripts/run_fit.py 后覆盖",
        "objective": {"weight": "modulus", "form": "L2", "value": None},
        "parameters": {}, "quality": {}, "multistart": {}}, "scripts/run_fit.py", case_name))
    with (res / "s3_fit_rl-rq-rq-wo_modulus_spectrum.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(["f_Hz", "Z_re_ohm", "Z_im_ohm", "Zfit_re_ohm",
                                 "Zfit_im_ohm", "resid_re_pct", "resid_im_pct"])
    write_json(res / "s4_ident_summary.json", envelope("s4", {
        "note": "placeholder：剖面似然（grid 用 to_theta 生成、横轴用 from_theta 换回）+ bootstrap；"
                "不可辨识参数只报区间并标注受约束/外推", "profile": {}, "bootstrap": {}},
        "scripts/s4_identify.py", case_name))
    (res / "s8_report_main.md").write_text(
        f"# {case_name} 等效电路拟合报告（骨架）\n\n按 SKILL.md §4 与 E16 的必报清单填写。\n",
        encoding="utf-8")
    write_json(res / "s9_env_versions.json", envelope("s9", env_snapshot(),
                                                      "scripts/init_case.py", case_name))

    shutil.copy2(HERE / "eis_core.py", case / "scripts" / "eis_core.py")
    (case / "scripts" / "run_fit.py").write_text(RUN_FIT, encoding="utf-8")

    with (res / "s1_data_clean.csv").open(encoding="utf-8-sig") as fh:
        n_rows = max(sum(1 for _ in fh) - 1, 0)
    artifacts = []
    for p in sorted(res.iterdir()):
        if not p.is_file() or p.name == "s9_manifest.json":
            continue
        stage = p.name.split("_")[0]
        artifacts.append({"path": f"results/{p.name}", "stage": stage,
                          "category": STAGE_CATEGORY.get(stage, "other"),
                          "status": "placeholder", "script": STAGE_SCRIPT.get(stage, ""),
                          "sha256": sha256(p), "bytes": p.stat().st_size,
                          "generated_at": datetime.now(timezone.utc).isoformat()})
    write_json(res / "s9_manifest.json", {
        "schema": "eis-fit-manifest/1", "case": case_name,
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "env": env_snapshot(),
        "vocabulary": {"model_slugs": ["rl-rq-rq-wo"], "tags": []},
        "data": {"results/s1_data_clean.csv": {"sha256": sha256(res / "s1_data_clean.csv"),
                                               "rows": n_rows}},
        "artifacts": artifacts})
    print(f"初始化完成：{case}")
    print(f"  下一步：把原始数据拷进 {case / 'data'}，清洗后写入 results/s1_data_clean.csv")
    print(f"  校验：python {HERE / 'validate_eis_outputs.py'} \"{case}\"")


def main() -> int:
    ap = argparse.ArgumentParser(description="生成符合 SKILL.md §4 的案例目录骨架")
    ap.add_argument("case_dir")
    ap.add_argument("--case-name", default=None)
    a = ap.parse_args()
    case = Path(a.case_dir).resolve()
    build(case, a.case_name or case.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
