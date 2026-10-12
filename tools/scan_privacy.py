#!/usr/bin/env python3
"""scan_privacy.py — 发布前的隐私体检（**只用通用规则，不含任何具体数据标识**）。

    python tools/scan_privacy.py eis-fitting-protocol          # 查目录
    python tools/scan_privacy.py dist/*.zip                    # 查 zip
    PRIVACY_DENY="样品A,批次-42" python tools/scan_privacy.py …  # 追加自定义禁词

设计要点：本脚本要进公开仓库，所以**绝不能把"要隐藏的字符串"写进源码** ——
那等于把要藏的东西公开。这里只做通用规则；具体标识通过环境变量 `PRIVACY_DENY`
（或 CI Secret）在运行时传入，不落盘。

通用规则：
  1. 包内不得出现数据类文件（.txt/.csv/.xlsx/.xls/.dat/.mpr/.z）
  2. 不得出现绝对路径（`X:\\`、`/Users/`、`/home/`、`/mnt/`）
  3. 不得出现邮箱 / 手机号样式字符串
  4. 不得有 NUL 字节
  5. 追加 `PRIVACY_DENY` 里的自定义禁词

退出码 0 = 通过，1 = 有命中。
"""
from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path

DATA_EXT = {".txt", ".csv", ".xlsx", ".xls", ".dat", ".mpr", ".z"}
PATH_PAT = re.compile(r"[A-Za-z]:\\\\|/Users/|/home/|/mnt/|[A-Za-z]:\\")
EMAIL_PAT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_PAT = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

TEXT_EXT = {".md", ".py", ".json", ".yml", ".yaml", ".txt", ".toml", ".cfg", ".gitignore",
            ".gitattributes", ""}


def tokens_from_env() -> list[str]:
    raw = os.environ.get("PRIVACY_DENY", "").strip()
    return [t.strip() for t in raw.split(",") if t.strip()]


def check_text(rel: str, text: str, deny: list[str], hits: list[str]) -> None:
    for i, line in enumerate(text.splitlines(), 1):
        for pat, label in ((PATH_PAT, "绝对路径"), (EMAIL_PAT, "邮箱"), (PHONE_PAT, "手机号")):
            m = pat.search(line)
            if m:
                hits.append(f"{rel}:{i} 出现{label}：{m.group(0)[:40]}")
        for tok in deny:
            if tok in line:
                hits.append(f"{rel}:{i} 命中自定义禁词（{len(tok)} 字符）")


def scan_dir(root: Path) -> list[str]:
    hits: list[str] = []
    deny = tokens_from_env()
    for p in sorted(root.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(root).as_posix()
        if p.suffix.lower() in DATA_EXT:
            hits.append(f"{rel} 是数据类文件（包内不应有）")
            continue
        raw = p.read_bytes()
        if b"\x00" in raw:
            hits.append(f"{rel} 含 NUL 字节")
        if p.suffix.lower() in TEXT_EXT or p.name in ("LICENSE", "NOTICE"):
            try:
                check_text(rel, raw.decode("utf-8"), deny, hits)
            except UnicodeDecodeError:
                pass
    return hits


def scan_zip(zp: Path) -> list[str]:
    hits: list[str] = []
    deny = tokens_from_env()
    with zipfile.ZipFile(zp) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            rel = info.filename
            if Path(rel).suffix.lower() in DATA_EXT:
                hits.append(f"{rel} 是数据类文件（包内不应有）")
                continue
            raw = z.read(rel)
            if b"\x00" in raw:
                hits.append(f"{rel} 含 NUL 字节")
            if Path(rel).suffix.lower() in TEXT_EXT or Path(rel).name in ("LICENSE", "NOTICE"):
                try:
                    check_text(rel, raw.decode("utf-8"), deny, hits)
                except UnicodeDecodeError:
                    pass
    return hits


def main() -> int:
    targets = [Path(a) for a in sys.argv[1:]] or [Path("eis-fitting-protocol")]
    all_hits: list[str] = []
    for t in targets:
        if not t.exists():
            print(f"跳过（不存在）：{t}")
            continue
        hits = scan_zip(t) if t.is_file() else scan_dir(t)
        print(f"{t}: {len(hits)} 处命中")
        all_hits += hits
    print("-" * 66)
    for h in all_hits:
        print("  ✗", h)
    if not all_hits:
        print("  通用隐私规则：全部通过")
    print("PRIVACY", "PASS" if not all_hits else "FAIL")
    return 0 if not all_hits else 1


if __name__ == "__main__":
    sys.exit(main())
