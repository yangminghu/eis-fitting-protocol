"""check_package.py — 技能包打包自检（对照 WorkBuddy 开放平台技能规范）。

    python check_package.py <zip 或 目录>

规范结构：
    {skill-name}/            ← 必须等于 SKILL.md frontmatter 的 name
    ├── SKILL.md             ← 必须
    ├── references/          ← 可选
    ├── scripts/             ← 可选
    └── templates/           ← 可选

frontmatter 必填：description / description_zh / description_en / version / author

本脚本把这份规范变成可执行的门禁：上传前跑一次，把"解析失败"挡在本地。
退出码 0 = 全部通过，非 0 = 有硬错误（另打印警告项）。
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

REQUIRED_FM = ["description", "description_zh", "description_en", "version", "author"]
ALLOWED_ROOT = {"SKILL.md", "references", "scripts", "templates"}
ALLOWED_DIRS = {"references", "scripts", "templates"}
HARD, WARN = [], []


def bad(msg):
    HARD.append(msg)


def warn(msg):
    WARN.append(msg)


def parse_frontmatter(text: str):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    body = m.group(1)
    out = {}
    for line in body.splitlines():
        mm = re.match(r"^([A-Za-z_][\w\-]*):\s*(.*)$", line)
        if mm:
            out[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return out


def check_tree(name_of, files: dict, is_zip: bool, zf=None):
    """files: {相对路径(相对包根): bytes}；name_of: 包根目录名。"""
    if not files:
        bad("包内没有任何文件")
        return

    # 1) 包根目录名
    if name_of is None:
        bad("zip 里没有唯一的顶层目录（所有条目都应在 {skill-name}/ 之下）")

    # 2) 根目录只允许 SKILL.md + references/ + scripts/ + templates/
    top = set()
    for rel in files:
        top.add(rel.split("/")[0])
    extra = top - ALLOWED_ROOT
    if extra:
        bad(f"包根出现规范外的条目：{sorted(extra)}（只允许 {sorted(ALLOWED_ROOT)}）")
    if "SKILL.md" not in top:
        bad("包根缺少必需的 SKILL.md")

    # 3) 子目录里只允许文件（不出现二级目录嵌套之外的东西）
    for rel in files:
        parts = rel.split("/")
        if len(parts) > 2 and parts[0] in ALLOWED_DIRS:
            warn(f"子目录里出现更深层级：{rel}")

    # 4) frontmatter
    sk = files.get("SKILL.md")
    if sk is None:
        return
    text = sk.decode("utf-8", errors="replace")
    if "\x00" in text:
        bad("SKILL.md 含 NUL 字节")
    fm = parse_frontmatter(text)
    if fm is None:
        bad("SKILL.md 缺少 YAML frontmatter（--- 包裹）")
        return
    if fm.get("name", "").strip() != (name_of or ""):
        bad(f"frontmatter name={fm.get('name')!r} 与包根目录名 {name_of!r} 不一致"
            "（规范要求两者相同）")
    missing = [k for k in REQUIRED_FM if not fm.get(k)]
    if missing:
        bad(f"frontmatter 缺必填字段：{missing}")
    if not re.match(r"^\d+(\.\d+)*", fm.get("version", "")):
        warn(f"version 不是数字版本号：{fm.get('version')!r}")

    # 5) @references/ 引用是否都存在（文件名以扩展名收尾，避免把全角括号一起吞进来）
    for mm in re.finditer(r"@references/([^\s`（）()、,;<>\"]+?\.(?:md|json|ya?ml|txt|csv|py))",
                          text):
        tgt = "references/" + mm.group(1)
        if tgt not in files:
            bad(f"SKILL.md 引用了不存在的文件：{tgt}")

    # 6) 所有文本文件不得含 NUL
    for rel, data in files.items():
        if rel == "SKILL.md":
            continue
        if b"\x00" in data[:4096] and not rel.endswith((".png", ".jpg", ".xlsx", ".docx")):
            warn(f"{rel} 疑似含 NUL 字节")

    # 6b) 许可声明自洽：声明了 license 就必须有对应正文文件，且不得残留旧许可
    lic = fm.get("license", "")
    licfile = files.get("references/LICENSE")
    if lic and licfile is None:
        bad(f"frontmatter 声明了 license: {lic}，但包内没有 references/LICENSE")
    if licfile is not None:
        lt = licfile.decode("utf-8", "replace")
        if "Apache License" not in lt or "Version 2.0, January 2004" not in lt:
            bad("references/LICENSE 不是 Apache-2.0 官方正文")
        if not re.search(r"Copyright\s+\d{4}\s+\S+", lt):
            bad("references/LICENSE 缺少已填写的版权行（附录里的 [yyyy]/[name] 没替换）")
        if files.get("references/NOTICE") is None:
            warn("有 references/LICENSE 但没有 references/NOTICE（上游无 NOTICE 时可忽略）")
    for rel, data in files.items():
        if rel == "scripts/check_package.py":
            continue        # 本文件把那些 token 当检索模式，扫自己没有意义
        if not (rel.endswith((".md", ".py", ".json", ".txt")) or rel.endswith(("LICENSE", "NOTICE"))):
            continue
        try:
            s = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for tok in ("保留所有权利", "PolyForm"):
            if tok in s:
                bad(f"{rel} 含旧许可残留：{tok}")
        # 许可/声明类文件只陈述事实，不得夹带"法律意见"式免责或给使用者的合规建议
        if rel.endswith(("LICENSE", "NOTICE", "许可与第三方声明.md")):
            for tok in ("非法律意见", "不构成法律意见", "法律意见", "建议咨询律师",
                        "分发义务", "使用提示"):
                if tok in s:
                    bad(f"{rel} 含法律意见式表述：{tok}（许可文件只陈述事实）")
        if re.search(r"\bMIT\b", s):
            # 许可文件与技能定义里出现 MIT 一律是硬错误；其他文件可能是描述依赖，降为警告
            (bad if rel.endswith(("LICENSE", "NOTICE", "SKILL.md", "许可与第三方声明.md"))
             else warn)(f"{rel} 出现 'MIT' 字样（确认是否旧许可残留）")

    # 7) zip 专有：目录条目 / 压缩方式 / 中文名 UTF-8 标志
    if is_zip and zf is not None:
        if any(i.is_dir() for i in zf.infolist()):
            warn("zip 含目录条目（原包约定为不写目录条目，多数平台也能接受）")
        if not all(i.compress_type == 8 for i in zf.infolist() if not i.is_dir()):
            warn("存在非 deflate 压缩的条目")
        for i in zf.infolist():
            if any(ord(c) > 127 for c in i.filename) and not (i.flag_bits & 0x800):
                warn(f"中文文件名未置 UTF-8 标志：{i.filename}")


def load_zip(p: Path):
    zf = zipfile.ZipFile(p)
    names = [i.filename for i in zf.infolist() if not i.is_dir()]
    roots = {n.split("/")[0] for n in names}
    root = roots.pop() if len(roots) == 1 else None
    files = {}
    for n in names:
        rel = n.split("/", 1)[1] if (root and n.startswith(root + "/")) else n
        files[rel] = zf.read(n)
    return root, files, zf


def load_dir(p: Path):
    root = p.name
    files = {q.relative_to(p).as_posix(): q.read_bytes() for q in p.rglob("*") if q.is_file()}
    return root, files, None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    p = Path(sys.argv[1])
    if not p.exists():
        print("路径不存在:", p)
        return 2
    if p.is_dir():
        root, files, zf = load_dir(p)
        is_zip = False
    else:
        root, files, zf = load_zip(p)
        is_zip = True

    check_tree(root, files, is_zip, zf)

    print("=" * 66)
    print(f"包根目录名 : {root}")
    print(f"条目数     : {len(files)}")
    for rel in sorted(files):
        print(f"   {rel:46} {len(files[rel]):>8} B")
    fm = parse_frontmatter(files.get("SKILL.md", b"").decode("utf-8", "replace")) or {}
    print("frontmatter:", ", ".join(f"{k}={fm.get(k, '—')[:40]}" for k in
                                    ("name", "version", "author")))
    print("-" * 66)
    for w in WARN:
        print("  ⚠️ ", w)
    for b in HARD:
        print("  ✗  ", b)
    print("=" * 66)
    print("PACKAGE", "PASS" if not HARD else f"FAIL（{len(HARD)} 项硬错误）")
    return 0 if not HARD else 1


if __name__ == "__main__":
    sys.exit(main())
