面向 **DeepSeek Harness** 的 EIS 等效电路拟合全流程硬规范：给出阻抗数据（`f / Z' / Z''`）即可产出**可复现、可发表**的等效电路拟合结果。

## 内容

**九阶段流程 s1–s9**：数据体检 → Lin-KK 校验 → 元素与自由参数核实 → 物理初值反解 → 多起点全局拟合 → 可辨识性（剖面似然 + bootstrap）→ 模型比较（AICc）→ 报告 → 环境与清单归档。

**硬门槛 E1–E18**：每条都写明判据、失败处置与"不许做什么"，覆盖最容易出事的地方 ——

| 常见错误 | 对应门槛 |
|---|---|
| BOM/分隔符没查，第一个数字被读错 | E1 输入口径 |
| 只看 RMS 残差小就认为拟合好 | E3 逐点残差判据 + **E16 拟合合格性** |
| K-K 结论随 Z/Y 表示法翻转却只报一种 | E3 表示法必须声明且两种都跑 |
| 用软件默认初值（R=1000 Ω、L=1 μH…）直接开拟合 | E6 物理初值反解 |
| 单起点掉进局部极小还宣布"最优" | E8 多起点 + 已知解作种子 |
| 撒点范围当硬边界，`n` 被静默夹在 0.5–0.73 | E9 `bounds` 必须真传求解器 |
| 最低 SSE 其实来自退化解（串联电阻→0） | E9 必须同时报 `best_valid_*` |
| 不可辨识参数当测量值报告 | E11 剖面似然 + bootstrap |
| AICc 跨权重比较 / 各模型各自落在局部极小 | E12 同口径 + 先给物理初值多种子 |
| `Tlmbo` 被当成独立的多孔证据 | E13 四步判据（与重参数化 `Wo` 解析恒等） |
| 直接用拟合出的 `L` 扣电感（自证） | E14 三候选 + 双条件 |
| 多份谱先平均再拟合，系统漂移被伪装成低噪声 | E18 逐份独立 + 组间离散度 |
| 交付物命名随意、`manifest` 缺 sha256 | §4 固定命名 + C1–C9 校验器 |

**`references/`**：21 个元素的公式/单位/默认值/上下限与固定状态、CDC 语法与标签陷阱、权重与目标函数口径（L4 vs 二次口径）、初值反解表、K-K 配置与判据、AICc 前提、多孔/传输线四步判据、电感扣除、常见陷阱清单、验证方法与可复现证据。

**`scripts/`**：`eis_core.py`（拟合核心：元素阻抗 + 多起点 + 剖面 + 官方对照，自带 `--selftest`）、`init_case.py`（生成合规案例骨架）、`validate_eis_outputs.py`（输出物命名/manifest 校验器 C1–C9）、`scan_batch.py`（多份数据批量核查，出组间离散度表）、`check_eis_env.py`（环境三级检查）、`check_package.py`（打包自检，对照 WorkBuddy 技能规范）、`install.py`（安装到本机技能目录）。

## 安装

**DeepSeek Harness（推荐）** —— 把 `eis-fitting-protocol/` 整个目录放进 DSH 扫描的技能目录（项目级 `.dsh/skills/` 或用户级 `<dshHome>/skills/`，以 DSH 官方文档为准）；也可以直接 `python eis-fitting-protocol/scripts/install.py`。

**WorkBuddy 开放平台** —— 下载下方 Assets 里的 `eis-fitting-protocol-v6.1.0.zip`（13 条目，根结构 = `SKILL.md` + `references/` + `scripts/`）直接上传。

**其他支持 `SKILL.md` 的 agent**（Claude Code / Codex 等）—— 把 `SKILL.md` 当提示词或按各自的技能目录约定放置即可。

## 运行环境

DSH 自带 Python 已包含 numpy / scipy / matplotlib，**拟合核心开箱即用、无需安装任何包**：先调用 `load_workspace_dependencies` 取 Python 路径，再执行 `scripts/` 下的脚本。

只有"官方 API 对照 / 元素内省"才需要额外依赖（pyimpspec、deareis）：

```bash
python eis-fitting-protocol/scripts/check_eis_env.py            # 三级报告
python eis-fitting-protocol/scripts/check_eis_env.py --print-install
```

详见 [`references/环境与安装.md`](eis-fitting-protocol/references/环境与安装.md)（含国内镜像与 pip 缓存坑）。

## 快速验证

```bash
python eis-fitting-protocol/scripts/eis_core.py --selftest
# 期望 SELFTEST PASS：参数回收 + 解析 Jacobian 数值校验 + 与官方实现的元素级对照
```

## 数据保密

**本仓库与发布附件均不含任何实验数据。** 随包只含方法、公式、代码与验证方法；不含任何样品/批次数据，也不含指向任何具体数据集的痕迹（文件名、样品标识、实测数值、绝对路径均已清除）。

## 许可

**Apache License 2.0** —— 可自由使用、修改、分发、商用（含闭源再分发），须保留版权与许可声明、标注修改并随附许可正文。见 [LICENSE](https://github.com/yangminghu/eis-fitting-protocol/blob/main/LICENSE) 与 [NOTICE](https://github.com/yangminghu/eis-fitting-protocol/blob/main/NOTICE)。

本仓库**不含** pyimpspec（GPL-3.0-or-later）与 DearEIS（GPLv3 or later）的代码，二者仅为运行时依赖。详见 [`references/许可与第三方声明.md`](eis-fitting-protocol/references/许可与第三方声明.md)。

**下载的 zip 里也带着同一份许可**：包内 `eis-fitting-protocol/references/LICENSE`（Apache-2.0 官方正文）与 `eis-fitting-protocol/references/NOTICE`（归属声明），与仓库根的同名文件**逐字节相同**，可直接随包带走再分发。

本产品与 Anthropic、DeepSeek、腾讯 WorkBuddy 及其他任何组织无隶属、赞助或背书关系。

## v6.1.0 变更要点

- **提速**：`global_fit` / `profile` 改为**两阶段**（松容差粗筛全部起点 → 紧容差精修最好的若干盆地代表）。同一 `seed` 下 `best_sse` 与单阶段一致到 ~1e-14，耗时约为其 1/2–1/7（多弧数据上实测最快到 1/14）。另提供解析 Jacobian（`jac="analytic"`，自检里做数值校验，列归一化误差 < 1e-9）。
- **新增 E16 拟合合格性**：最大相对残差必须与噪声量级比较；比噪声大一个数量级或呈系统性频段偏差时，必须写明"该模型对本谱不合格"并继续换模型，不得直接给参数结论。AICc 排名也被限定为"只在通过合格性筛的候选之间"。
- **新增输入体检** `check_data()`：一次拦住长度不一致 / 空 / 非有限值 / 非正频率 / 重复频率 / `|Z|=0` / 自由度不足（2N ≤ 参数个数）。这几类旧版会以"看似成功"的方式给出垃圾结果。
- **新增 `scan_batch.py`**：多份数据的批量核查（体检 + 拟合 + 组间离散度表 + 合格性统计），直接支撑 E18。
- **新增 `check_package.py`**：把 WorkBuddy 技能规范变成可执行门禁（根目录名 = `name` 字段、根目录只允许 `SKILL.md`+`references/`+`scripts/`+`templates/`、5 个必填 frontmatter、`@references/` 引用可落地、无 NUL 字节）。
- **打包结构改为平台规范**：包根 = `eis-fitting-protocol/`，只含 `SKILL.md` + `references/` + `scripts/`（原 v6 的根级 install/README/LICENSE/VERSION 已收进对应位置）。
- **许可**：Apache License 2.0（第三方依赖声明同步保留）。
- **弧数判据修正**：原"`prominence > 3σ`"用全频段绝对阈值，在真实谱上恒等于 0、什么也报不出；改为相对化阈值并要求同时报平滑宽度与阈值，且只作**描述**、不作为判据。
