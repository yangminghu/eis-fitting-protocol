"""校验一个 EIS 拟合案例是否满足输出物命名规范（SKILL.md §4）。纯标准库，无第三方依赖。

    python validate_eis_outputs.py <case_dir> [--manifest=results/s9_manifest.json]
                                   [--baseline=baseline.json]

检查项
------
C1 目录结构      data/ results/ work/ scripts/ 是否存在
C2 文件名语法    <stage>_<subject>[_<tag>...].<ext>，全小写 ASCII；tag 需在词表内
C3 禁用词        final/new/latest/tmp/temp/dbg/debug/test/ok/copy/backup/v2/v3
C4 阶段与扩展名  每个 stage 允许的扩展名
C5 JSON 信封     每个交付 JSON 必须含 schema/stage/case/generated_at/inputs/code/payload
C6 CSV 表头      列名必须在词表内（或带合法单位后缀）
C7 manifest      results/s9_manifest.json 覆盖全部交付物且 sha256 一致
C8 最小交付集合  见 MIN_DELIVERABLES（与 SKILL.md §4 一致）
C9 work/         work/ 内的文件不得出现在 manifest 的交付清单里

退出码：0 = 合规；1 = 有违规。报告写到 <case>/work/output_spec_report.json。
用 --baseline 冻结历史违规，此后只报**新增**违规（既有项目渐进落地用）。
生成合规骨架请用 init_case.py（本文件不做目录初始化）。

⚠️ C3 的"大小写"规则在 **Windows / macOS 这类大小写不敏感的文件系统上无法本地复现**（`S1_x.csv` 与 `s1_x.csv` 是同一个文件），它针对的是从 Linux 打包/检出的仓库 —— 请在 Linux 上或打包流程里做这项检查，别以为本机 0 违规就等于跨平台合规。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

STAGES = {"s1": "输入与清洗", "s2": "数据有效性（K-K）", "s3": "拟合",
          "s4": "可辨识性与不确定度", "s5": "模型比较", "s6": "多孔/传输线专项",
          "s7": "交叉验证（DRT / 独立实现）", "s8": "交付报告与图表",
          "s9": "环境、元素清单与 manifest"}

STAGE_EXT = {s: {".csv", ".json", ".png"} for s in STAGES}
STAGE_EXT["s8"] = {".md", ".xlsx", ".png", ".json"}
STAGE_EXT["s9"] = {".json", ".txt"}

FORBIDDEN_TOKENS = ["final", "new", "latest", "tmp", "temp", "dbg", "debug",
                    "test", "ok", "copy", "backup", "v2", "v3"]

NAME_RE = re.compile(r"^(s[1-9])_([a-z0-9]+(?:-[a-z0-9]+)*)((?:_[a-z0-9]+(?:-[a-z0-9]+)*)*)\.([a-z0-9]+)$")

# 允许出现在文件名中的 tag（覆盖 SKILL.md §1/§4 里出现的全部文件名）
TAG_VOCAB = {
    # 权重
    "unity", "modulus", "proportional", "boukamp",
    # 模型/方案
    "nfix", "nfree", "main", "alt",
    # 图
    "nyquist", "bode", "residual", "residuals", "kk", "mscan", "profile", "drt",
    # 数据（clean/flip = E1 的原号与反号对照；lc = E14 扣除电感后）
    "raw", "clean", "flip", "lc", "health",
    # 产物
    "multistart", "spectrum", "summary", "diagnostics", "elements", "versions",
    "bootstrap", "jacobian", "aicc", "f_test", "equivalence", "porous", "corrected",
    # 交叉验证
    "dual", "l-selection",
    # 剖面对象（s4_ident_profile_<param>.csv）：PARAM_NAMES 的 slug
    "r1", "l1", "r2", "y2", "n2", "r3", "y3", "n3", "yw", "bw", "nw",
}

MIN_DELIVERABLES = [
    ("s1", "s1_data_clean.csv"),
    ("s2", "s2_kk_summary.json"),
    ("s3", None),                       # s3_fit_*_*.json 至少一份
    ("s4", "s4_ident_summary.json"),
    ("s8", "s8_report_main.md"),
    ("s9", "s9_env_versions.json"),
    ("s9", "s9_manifest.json"),
]

COLUMN_VOCAB = {
    "param", "name", "value", "stderr", "lower", "upper", "unit", "fixed",
    "model", "k", "n", "sse", "aicc", "delta_aicc", "status", "note",
    "f", "z_re", "z_im", "z_abs", "phase", "zfit_re", "zfit_im",
    "resid_re", "resid_im", "resid_abs", "resid_max",
    "m", "mu", "rms", "tau", "r",
    "chi2", "pseudo_chi2", "sigma",
    "param_value", "delta_sse", "p16", "p50", "p84", "mean", "std",
    "gamma", "lambda", "lambda_",
}
UNIT_SUFFIXES = ["hz", "khz", "ohm", "cm2", "s", "f", "h", "v", "pct", "deg", "sm1"]
JSON_ENVELOPE_REQUIRED = ["schema", "stage", "case", "generated_at", "inputs", "code", "payload"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_name(p: Path, extra_tags: set[str] | None = None) -> list[str]:
    errs: list[str] = []
    name = p.name
    if name != name.lower():
        errs.append("C3 含大写字母（跨平台/脚本易错）")
    if " " in name:
        errs.append("C3 含空格")
    if re.search(r"[^\x00-\x7f]", name):
        errs.append("C3 含非 ASCII（如中文）字符")
    low = name.lower()
    for tok in FORBIDDEN_TOKENS:
        if re.search(r"(^|_)%s(_|\.|$)" % tok, low):
            errs.append("C3 含禁用词 '%s'（版本请靠 manifest/run_id，不要写进文件名）" % tok)
    m = NAME_RE.match(name)
    if not m:
        return errs + ["C2 不符合 <stage>_<subject>[_<tag>...].<ext> 语法"]
    stage, _subject, tags, ext = m.group(1), m.group(2), m.group(3), "." + m.group(4)
    if ext not in STAGE_EXT[stage]:
        errs.append("C4 %s 不允许扩展名 %s（允许：%s）"
                    % (stage, ext, ",".join(sorted(STAGE_EXT[stage]))))
    allowed = TAG_VOCAB | {str(t).lower() for t in (extra_tags or set())}
    for tag in [t for t in tags.split("_") if t]:
        if tag not in allowed:
            errs.append("C2 未登记的 tag '%s'（加入 TAG_VOCAB，或在 manifest 的 "
                        "vocabulary.tags/model_slugs 里声明）" % tag)
    return errs


def check_json_envelope(p: Path) -> list[str]:
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return ["C5 JSON 无法解析：%s" % exc]
    if not isinstance(obj, dict):
        return ["C5 顶层不是对象"]
    missing = [k for k in JSON_ENVELOPE_REQUIRED if k not in obj]
    if missing:
        return ["C5 缺少信封字段 %s" % ",".join(missing)]
    if obj.get("schema") != "eis-fit-result/1":
        return ["C5 schema 应为 'eis-fit-result/1'"]
    if str(obj.get("stage")) not in STAGES:
        return ["C5 stage 非法"]
    return []


def check_csv_header(p: Path) -> list[str]:
    try:
        with p.open(encoding="utf-8-sig") as fh:
            header = fh.readline().strip()
    except Exception as exc:
        return ["C6 无法读取：%s" % exc]
    if not header:
        return ["C6 缺少表头"]
    bad = []
    for col in header.split(","):
        col = col.strip().lower()
        if not re.fullmatch(r"[a-z0-9_]+", col):
            bad.append("%s(非小写下划线)" % col)
        elif col in COLUMN_VOCAB or any(col.endswith("_" + u) for u in UNIT_SUFFIXES):
            continue
        else:
            bad.append("%s(不在词表且无单位后缀)" % col)
    return ["C6 列名不合规：%s" % ", ".join(bad)] if bad else []


def run(case: Path, manifest_rel: str, baseline: dict | None) -> dict:
    report = {"case": str(case), "generated_at": datetime.now(timezone.utc).isoformat(),
              "violations": [], "summary": {}}
    results = case / "results"
    for sub in ("data", "results", "work", "scripts"):
        if not (case / sub).is_dir():
            report["violations"].append({"check": "C1", "path": sub + "/", "msg": "目录缺失"})
    if not results.is_dir():
        return report

    manifest_path = case / manifest_rel
    manifest = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = None
    extra_tags: set[str] = set()
    if isinstance(manifest, dict):
        vocab = manifest.get("vocabulary") or {}
        for key in ("model_slugs", "tags"):
            extra_tags |= {str(t).lower() for t in (vocab.get(key) or [])}

    files = [p for p in sorted(results.iterdir()) if p.is_file() and not p.name.startswith(".")]
    for p in files:
        for e in check_name(p, extra_tags):
            report["violations"].append({"check": e[:2], "path": "results/" + p.name, "msg": e})
        if p.suffix == ".json" and p.name != manifest_path.name:
            for e in check_json_envelope(p):
                report["violations"].append({"check": e[:2], "path": "results/" + p.name, "msg": e})
        if p.suffix == ".csv":
            for e in check_csv_header(p):
                report["violations"].append({"check": e[:2], "path": "results/" + p.name, "msg": e})

    if not manifest_path.exists():
        report["violations"].append({"check": "C7", "path": manifest_rel, "msg": "manifest 缺失"})
    elif manifest is None:
        report["violations"].append({"check": "C7", "path": manifest_rel,
                                     "msg": "manifest 无法解析"})
    else:
        if manifest.get("schema") != "eis-fit-manifest/1":
            report["violations"].append({"check": "C7", "path": manifest_rel,
                                         "msg": "schema 应为 'eis-fit-manifest/1'"})
        listed = set()
        for a in manifest.get("artifacts", []):
            rel = str(a.get("path", ""))
            listed.add(rel)
            fp = case / rel
            if not fp.exists():
                report["violations"].append({"check": "C7", "path": rel,
                                             "msg": "manifest 列出但文件不存在"})
                continue
            if a.get("sha256") and a["sha256"] != sha256(fp):
                report["violations"].append({"check": "C7", "path": rel,
                                             "msg": "sha256 不一致（文件已改但 manifest 未更新）"})
            if rel.startswith("work/"):
                report["violations"].append({"check": "C9", "path": rel,
                                             "msg": "work/ 内文件不得作为交付物登记"})
        for p in files:
            if "results/" + p.name not in listed and p.name != manifest_path.name:
                report["violations"].append({"check": "C7", "path": "results/" + p.name,
                                             "msg": "未登记进 manifest"})

    names = {p.name for p in files}
    for _stage, exact in MIN_DELIVERABLES:
        if exact is None:
            if not any(n.startswith("s3_fit_") and n.endswith(".json") for n in names):
                report["violations"].append({"check": "C8", "path": "results/",
                                             "msg": "缺少最小交付物 s3_fit_*_*.json"})
        elif exact not in names:
            report["violations"].append({"check": "C8", "path": "results/",
                                         "msg": "缺少最小交付物 " + exact})

    if baseline is not None:
        known = {json.dumps(v, sort_keys=True, ensure_ascii=False)
                 for v in baseline.get("violations", [])}
        new = [v for v in report["violations"]
               if json.dumps(v, sort_keys=True, ensure_ascii=False) not in known]
        report["baseline_mode"] = {"known": len(known), "total": len(report["violations"]),
                                   "new": len(new)}
        report["violations"] = new

    by_check: dict = {}
    for v in report["violations"]:
        by_check[v["check"]] = by_check.get(v["check"], 0) + 1
    report["summary"] = {"total": len(report["violations"]), "by_check": by_check}
    return report


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    opts = [a for a in argv[1:] if a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    case = Path(args[0]).resolve()
    manifest_rel = next((o.split("=", 1)[1] for o in opts if o.startswith("--manifest=")),
                        "results/s9_manifest.json")
    base_opt = next((o.split("=", 1)[1] for o in opts if o.startswith("--baseline=")), None)
    baseline = (json.loads(Path(base_opt).read_text(encoding="utf-8"))
                if base_opt and Path(base_opt).exists() else None)
    rep = run(case, manifest_rel, baseline)
    (case / "work").mkdir(parents=True, exist_ok=True)
    out = case / "work" / "output_spec_report.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    s = rep["summary"]
    print("case:", rep["case"])
    print("violations:", s.get("total"), s.get("by_check"))
    if rep.get("baseline_mode"):
        print("baseline mode:", rep["baseline_mode"])
    for v in rep["violations"][:15]:
        print("  [%s] %s -- %s" % (v["check"], v["path"], v["msg"]))
    if len(rep["violations"]) > 15:
        print("  ... %d more in %s" % (len(rep["violations"]) - 15, out))
    return 0 if not rep["violations"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
