#!/usr/bin/env python3
"""build_zip.py — 按包约定把 eis-fitting-protocol/ 打成 zip（确定性输出）。

    python tools/build_zip.py [输出路径]        # 默认 dist/eis-fitting-protocol.zip

包约定（与仓库内已发布的历史包一致）：
  * 单一顶层目录 = 包名
  * **不写目录条目**、全部 deflate
  * 中文文件名置 UTF-8 标志位
  * create_system = 0、external_attr = 0x81b60000
  * 固定时间戳 1980-01-01 ⇒ **同样输入必得同样字节**（CI 里靠这一点做可复现性校验）
  * 条目顺序：SKILL.md → references/ → scripts/ → templates/
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "eis-fitting-protocol"
RANK = {"references": 1, "scripts": 2, "templates": 3}


def sort_key(rel: str):
    top = rel.split("/")[0]
    return (0 if rel == "SKILL.md" else RANK.get(top, 4), rel)


def build(out: Path) -> Path:
    if not (PKG / "SKILL.md").is_file():
        raise SystemExit(f"找不到包根或 SKILL.md：{PKG}")
    files = sorted(
        (p for p in PKG.rglob("*") if p.is_file() and "__pycache__" not in p.parts),
        key=lambda p: sort_key(p.relative_to(PKG).as_posix()),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            rel = p.relative_to(PKG).as_posix()
            arc = f"{PKG.name}/{rel}"
            zi = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 0
            zi.external_attr = 0x81B60000
            if any(ord(c) > 127 for c in arc):
                zi.flag_bits |= 0x800
            z.writestr(zi, p.read_bytes())
    return out


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / f"{PKG.name}.zip"
    build(out)
    with zipfile.ZipFile(out) as z:
        n = len(z.namelist())
    print(f"{out}: {out.stat().st_size} bytes, {n} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
