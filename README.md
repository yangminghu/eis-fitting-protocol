# EIS 等效电路拟合规范（eis-fitting-protocol）

> **给 EIS（电化学阻抗谱）做等效电路拟合的"硬门槛化"全流程规范。**
> 给出阻抗数据（`f / Z' / Z''`）即可产出**可复现、可发表**的拟合结果：
> 九个阶段流程、**硬门槛 E1–E18**、固定的输出物命名与 `manifest`，
> 以及"不要重写"的拟合核心代码与校验器。

许可：**Apache License 2.0**（见 [LICENSE](LICENSE) / [NOTICE](NOTICE)）·
面向 **DeepSeek Harness** 制作 · 兼容其他支持 `SKILL.md` 的 agent

---

## 这个规范解决什么问题

EIS 拟合最容易出的不是"算法不会写"，而是**流程上少做了某一步却照样给出漂亮结论**。这个规范把每一处
都写成可执行的条款与硬门槛：

| 常见错误 | 本规范的对应门槛 |
|---|---|
| 没查数据编码/分隔符/表头，BOM 被读进第一个数字 | **E1** 输入口径（编码探测 + 分隔符显式判定） |
| 只看 RMS 残差小就认为拟合好，单点早已超标 | **E3** Lin-KK 判据用**逐点**最大相对残差；**E16 拟合合格性**要求最大残差与噪声量级比较 |
| K-K 结论随 Z/Y 表示法翻转却只报一种 | **E3** 表示法必须声明且两种都跑 |
| 用软件默认初值（R=1000 Ω、L=1 μH…）直接开拟合 | **E6** 物理初值反解（含 `Y = 1/[R_k(2πf_peak)^n]` 这类易写反的式子） |
| 单起点拟合，掉进局部极小还宣布"最优" | **E8** 多起点（按参数个数定起点数）+ 已知解作种子；只准写"已发现的最低 SSE" |
| 把撒点范围当硬边界，把 `n` 静默夹在 0.5–0.73 | **E9** `bounds` 必须真传求解器；退化查**两层**（贴硬边界 + 跑出物理合理窗口） |
| 最低 SSE 其实来自退化解（串联电阻→0） | **E9** 同时报 `best_valid_*`（无贴界解），别只看 `best_sse` |
| 参数不可辨识却当测量值报告 | **E11** 剖面似然（grid 是 θ 空间）+ bootstrap；剖面 1σ 带覆盖 1–4 个数量级 ⇒ 只能报区间 |
| AICc 跨权重比较、或各模型各自落在局部极小 | **E12** 同权重/同口径/同频段 + 每个候选都必须先给物理初值再多种子；**先过合格性再排名** |
| 多孔/传输线元素乱加，`Tlmbo` 当成独立证据 | **E13** 四步判据（ΔAICc + 特征频率 + 剖面 + 参数跑飞）；`Tlmbo` 与重参数化 `Wo` 解析恒等 |
| 直接用拟合出的 `L` 扣电感（自证） | **E14** 三候选 + 双条件（K-K 逐点残差下降且 ≤ 噪声 + 顶部 `Z''` 单调不增） |
| 多份谱先平均再拟合，把系统漂移伪装成低噪声 | **E18** 逐份独立走 s1–s4 + 报组间离散度（`scripts/scan_batch.py` 一条命令） |
| 交付物命名随意、`manifest` 缺 sha256 | §4 固定命名/目录/manifest + **C1–C9 校验器** |

## 目录结构

```
eis-fitting-protocol/               ← 技能包（可直接 zip 上传 WorkBuddy 开放平台）
├── SKILL.md                        ← 执行规范（frontmatter + 流程 + E1–E18 + 输出物 + 坑）
├── references/
│   ├── 元素与公式.md                ← 21 个元素公式/单位/默认值/上下限 + CDC 语法 + 判据 + 陷阱
│   ├── 器件元素清单.json             ← 同上，机器可读（grep 用）
│   ├── 实测依据.md                  ← 每条规则"怎么验"的复现方法（不含任何样品数据）
│   ├── 环境与安装.md                ← 依赖/pip 镜像坑/快速开始/常见问题/打包自检
│   ├── LICENSE                     ← Apache-2.0 官方正文（与仓库根同名文件逐字节相同）
│   ├── NOTICE                      ← 版权归属 + 第三方依赖清单（与仓库根同名文件逐字节相同）
│   └── 许可与第三方声明.md           ← 中文摘要（授权/须遵守/免责/专利）+ 第三方依赖（GPL）声明
└── scripts/
    ├── eis_core.py                 ← 拟合核心（元素阻抗 + 多起点 + 剖面 + 官方对照，自带 --selftest）
    ├── init_case.py                ← 一键生成合规案例骨架
    ├── validate_eis_outputs.py      ← 输出物命名/manifest 校验器（C1–C9）
    ├── scan_batch.py               ← 多份数据批量核查（E18：体检 + 拟合 + 组间离散度）
    ├── check_eis_env.py            ← 环境检查（--json / --check-mirrors / --print-install）
    ├── check_package.py            ← 打包自检（对照 WorkBuddy 技能规范）
    └── install.py                  ← 安装到本机技能目录
```

## 快速开始

```bash
# ① 自检拟合核心（应输出 SELFTEST PASS）
python eis-fitting-protocol/scripts/eis_core.py --selftest

# ② 生成合规案例骨架（校验器应为 0 违规）
python eis-fitting-protocol/scripts/init_case.py ./my-case --case-name my-cell
python eis-fitting-protocol/scripts/validate_eis_outputs.py ./my-case

# ③ 把清洗后的数据写入 ./my-case/results/s1_data_clean.csv
#    列名固定：f_Hz, Z_re_ohm, Z_im_ohm
#    然后跑骨架里生成的 my-case/scripts/run_fit.py，再按 SKILL.md 的 ★① 任务模板交给 AI

# ④ 多份谱（重复测量 / 不同状态）一次跑完，出组间离散度
python eis-fitting-protocol/scripts/scan_batch.py <目录或文件...> --starts=200 --csv=spread.csv
```

## 运行环境

**在 DeepSeek Harness 中（推荐）**：把 `eis-fitting-protocol/` 整个目录放进 DSH 扫描的技能目录
（项目级 `.dsh/skills/` 或用户级 `<dshHome>/skills/`，**以 DSH 官方文档为准**）。
DSH 自带 Python 已包含 numpy / scipy / matplotlib，**拟合核心开箱即用、无需安装任何包**；
先调用 `load_workspace_dependencies` 取 Python 路径，再执行 `scripts/` 下的脚本。
技能目录视为只读资源，产物写到工作区。

**只有"官方 API 对照 / 元素内省"才需要额外依赖**（pyimpspec、deareis）：

```bash
python eis-fitting-protocol/scripts/check_eis_env.py            # 三级报告
python eis-fitting-protocol/scripts/check_eis_env.py --print-install
```

详见 [`references/环境与安装.md`](eis-fitting-protocol/references/环境与安装.md)（含国内镜像与 pip 缓存坑）。

**在其他环境中**：`SKILL.md` 是通用格式，Claude Code / Codex 等支持该格式的 agent 也能用；
本包结构同时符合 WorkBuddy 开放平台的技能规范（`SKILL.md` + `references/` + `scripts/`），
可直接打包成 zip 上传（上传前先跑 `python eis-fitting-protocol/scripts/check_package.py <zip>`）。
另注：多进程并行**没有**写进核心脚本 —— Windows 是 spawn，从脚本/REPL 直接调用会因缺
`if __name__ == "__main__":` 抛 `RuntimeError`；要并行请自行包好主模块。

## 数据保密

**本仓库不包含任何实验数据。** 随包只含方法、公式、代码与验证方法，不含任何样品/批次数据，
也不含指向任何具体数据集的痕迹（文件名、样品标识、实测数值、绝对路径均已清除）。
`.gitignore` 已挡住 `*.txt` / `*.csv` / `*.xlsx` / `*.zip`，避免误提交。

## 许可与归属

- 本作品以 **Apache License 2.0** 授权 —— 可自由使用、修改、分发、商用（含闭源再分发），
  须保留版权与许可声明、标注修改，并随附许可正文。见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
- **本仓库不含** pyimpspec（GPL-3.0-or-later）与 DearEIS（GPLv3 or later）的代码，
  二者仅为运行时依赖，由使用者自行安装。详见
  [`references/许可与第三方声明.md`](eis-fitting-protocol/references/许可与第三方声明.md)。
- 本产品与 Anthropic、DeepSeek、腾讯 WorkBuddy 及其他任何组织无隶属、赞助或背书关系。

## 版本

**v6.1.0**（2026-10）。变更要点见 [`SKILL.md`](eis-fitting-protocol/SKILL.md) §6。
