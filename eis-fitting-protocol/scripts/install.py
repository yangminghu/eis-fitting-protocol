#!/usr/bin/env python3
"""把 EIS 拟合技能安装到 DSH 技能目录。

    python scripts/install.py [--target <技能目录>] [--force]

默认技能目录：$DSH_SKILLS_DIR，否则 ~/.dsh/skills
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

NAME = "eis-fitting-protocol"
HERE = Path(__file__).resolve().parent          # .../eis-fitting-protocol/scripts
PAYLOAD = HERE.parent                            # 包根 = 技能本体（SKILL.md/references/scripts）


def default_root() -> Path:
    env = os.environ.get("DSH_SKILLS_DIR")
    return Path(env) if env else Path.home() / ".dsh" / "skills"


def main() -> int:
    ap = argparse.ArgumentParser(description="安装 eis-fitting-protocol 技能")
    ap.add_argument("--target", default=None, help="技能根目录（默认 ~/.dsh/skills）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的同名技能")
    a = ap.parse_args()

    if not (PAYLOAD / "SKILL.md").exists():
        print("错误：找不到 skill/SKILL.md，请确认解压完整", file=sys.stderr)
        return 2

    root = Path(a.target).expanduser().resolve() if a.target else default_root()
    dst = root / NAME
    if dst.exists():
        if not a.force:
            print(f"目标已存在：{dst}\n如需覆盖请加 --force（或先手动备份）", file=sys.stderr)
            return 1
        shutil.rmtree(dst)
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PAYLOAD, dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))

    n = sum(1 for _ in dst.rglob("*") if _.is_file())
    print(f"已安装：{dst}（{n} 个文件）")
    print("\n下一步：")
    print(f"  1) 检查环境： python \"{dst / 'scripts' / 'check_eis_env.py'}\"")
    print(f"  2) 自检核心： python \"{dst / 'scripts' / 'eis_core.py'}\" --selftest")
    print(f"  3) 新建案例： python \"{dst / 'scripts' / 'init_case.py'}\" ./my-case")
    print("  4) 新开一次会话，DSH 会把该技能列入技能目录；"
          "或直接把 skill/SKILL.md 当提示词使用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
