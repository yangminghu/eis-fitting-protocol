"""EIS 拟合环境检查（首次运行第 1 步）。纯标准库，不 import pyimpspec/deareis 本体。

    python check_eis_env.py                   # 检查当前解释器
    python check_eis_env.py --json            # 只输出一行 JSON（省 token）
    python check_eis_env.py --check-mirrors    # 额外测国内镜像有没有 deareis（联网）
    python check_eis_env.py --print-install    # 打印推荐安装命令

分级（不要一看到有包没装就以为整个技能不能用）：
    REQUIRED  numpy/scipy —— eis_core.py / init_case.py 与 E1–E4/E6–E9/E11 的最小集
    OFFICIAL  pyimpspec/lmfit/sympy/matplotlib —— 元素内省(E5)、官方双实现互证(E10)、出图
    OPTIONAL  deareis（DearEIS 桌面端与官方对照的可选后端）、requests（只影响 pip 解析）

verdict：OK（三档齐全）/ CORE_ONLY（只有 REQUIRED，E5/E10 会 SKIP）/ NEEDS_INSTALL。
退出码：0 = OK 或 CORE_ONLY；2 = NEEDS_INSTALL。
"""
from __future__ import annotations

import importlib.metadata as md
import importlib.util
import json
import re
import sys
import urllib.request

REQUIRED = {"numpy": ">=2.5", "scipy": ">=1.17"}
OFFICIAL = {"pyimpspec": "==5.2.0", "lmfit": ">=1.3", "sympy": ">=1.14",
            "matplotlib": ">=3.11"}
OPTIONAL = {"deareis": "==5.1.3", "requests": ">=2.33"}
MIRRORS = [
    ("tuna", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("ustc", "https://pypi.mirrors.ustc.edu.cn/simple"),
    ("aliyun", "https://mirrors.aliyun.com/pypi/simple/"),
    ("pypi", "https://pypi.org/simple"),
]


def ver_tuple(s: str):
    out = []
    for part in re.split(r"[.\-+]", s or ""):
        out.append((0, int(part), "") if part.isdigit() else (1, 0, part))
    return tuple(out)


def installed(name: str):
    if importlib.util.find_spec(name) is None:
        return None
    try:
        return md.version(name)
    except Exception:
        return "?"


def satisfies(version: str, spec: str) -> bool:
    m = re.match(r"(>=|==|<=)([\d.]+)", spec)
    if not (m and version and version != "?"):
        return False
    op, want = m.group(1), m.group(2)
    a, b = ver_tuple(version), ver_tuple(want)
    if op == "==":                       # 容忍 5.2.0.post1 这类后缀
        return a[:len(b)] == b
    return a >= b if op == ">=" else a <= b


def collect() -> dict:
    rows, tier_of = {}, {}
    for tier, spec_map in (("required", REQUIRED), ("official", OFFICIAL),
                           ("optional", OPTIONAL)):
        for name, spec in spec_map.items():
            v = installed(name)
            rows[name] = {"version": v, "require": spec, "tier": tier,
                          "ok": bool(satisfies(v, spec))}
            tier_of[name] = tier
    missing = {t: [n for n, r in rows.items() if r["tier"] == t and not r["ok"]]
               for t in ("required", "official", "optional")}
    if missing["required"]:
        verdict = "NEEDS_INSTALL"
    elif missing["official"]:
        verdict = "CORE_ONLY"
    else:
        verdict = "OK"
    return {"python": sys.version.split()[0], "executable": sys.executable,
            "packages": rows, "missing": missing, "verdict": verdict}


def check_mirrors(verbose: bool = False) -> dict:
    """用 simple index 判断该源有没有 requests>=2.33 与 deareis 5.1.3。"""
    res = {}
    for name, base in MIRRORS:
        out = {"requests_2_33_plus": False, "deareis_5_1_3": False, "error": None}
        for pkg, key, pat in (("requests", "requests_2_33_plus",
                               r"requests-2\.(3[3-9]|[4-9]\d)"),
                              ("deareis", "deareis_5_1_3", r"deareis-5\.1\.3")):
            try:
                with urllib.request.urlopen(f"{base}/{pkg}/", timeout=8) as fh:
                    html = fh.read().decode("utf-8", "ignore")
                out[key] = bool(re.search(pat, html))
            except Exception as exc:
                out["error"] = type(exc).__name__
        res[name] = out
        if verbose:
            flag = "OK " if out["requests_2_33_plus"] and out["deareis_5_1_3"] else "FAIL"
            print(f"  [{flag}] {name:<7} requests>=2.33: {out['requests_2_33_plus']} | "
                  f"deareis 5.1.3: {out['deareis_5_1_3']}"
                  f"{' | ' + out['error'] if out['error'] else ''}")
    return res


def install_commands(mirror: str | None = None) -> list[str]:
    url = dict(MIRRORS).get(mirror or "tuna", dict(MIRRORS)["tuna"])
    venv_py = (r".\.venv_eis\Scripts\python" if sys.platform == "win32"
               else ".venv_eis/bin/python")
    return [
        "python -m venv .venv_eis",
        f"{venv_py} -m pip install -U pip",
        f'python -m pip install "deareis==5.1.3" -i {url}',
        "# 若报 No matching distribution found：先怀疑 pip 索引缓存过期（本机实测过）",
        f'python -m pip install "deareis==5.1.3" -i {url} --no-cache-dir',
        "python check_eis_env.py    # 复验：应显示 verdict: OK",
    ]


def main(argv: list[str]) -> int:
    rep = collect()
    if "--check-mirrors" in argv:
        rep["mirrors"] = check_mirrors(verbose="--json" not in argv)
    if "--print-install" in argv:
        mir = rep.get("mirrors") or {}
        pick = next((m for m, _ in MIRRORS if mir.get(m, {}).get("requests_2_33_plus")),
                    "tuna")
        rep["recommended_mirror"] = pick
        rep["install_commands"] = install_commands(pick)
    if "--json" in argv:
        print(json.dumps(rep, ensure_ascii=False))
        return 0 if rep["verdict"] != "NEEDS_INSTALL" else 2

    pk = rep["packages"]
    def tag(n):
        r = pk[n]
        return f"{n}={r['version'] or 'MISSING'}" + ("" if r["ok"] else f"({r['require']} ✗)")
    print(f"[EIS env] python={rep['python']}  {rep['executable']}")
    print("  required: " + " | ".join(tag(n) for n in REQUIRED))
    print("  official: " + " | ".join(tag(n) for n in OFFICIAL))
    print("  optional: " + " | ".join(tag(n) for n in OPTIONAL))
    print(f"verdict: {rep['verdict']}")
    if rep["verdict"] == "NEEDS_INSTALL":
        print(f"  ⚠ required 缺 {rep['missing']['required']}，先装这两个：")
        print("     python -m pip install \"numpy>=2.5\" \"scipy>=1.17\"")
    if rep["missing"]["official"]:
        print(f"  note: official 缺 {rep['missing']['official']}"
              " → E5（元素内省）与 E10（官方双实现互证）会 SKIP，其余流程可跑")
    if rep["missing"]["optional"]:
        print(f"  note: optional 缺 {rep['missing']['optional']} → 仅影响 DearEIS 桌面端；"
              "requests 不满足只影响 pip 解析，不影响 import")
    if rep["verdict"] != "OK":
        print("  -> 用独立 venv 安装，不要装进 anaconda base（会升级 numpy/scipy/matplotlib）")
        for c in install_commands("tuna"):
            print("     " + c)
        print("  注意：pip 报 'No matching distribution found' 时优先怀疑**索引缓存过期**，")
        print("        加 --no-cache-dir 或先 pip cache purge（多数国内源都有 deareis 5.1.3）")
    return 0 if rep["verdict"] != "NEEDS_INSTALL" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
