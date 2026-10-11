---
name: eis-fitting-protocol
display_name: EIS 等效电路拟合规范
display_name_en: EIS Equivalent-Circuit Fitting Protocol
description: "EIS 等效电路拟合全流程硬规范：给出阻抗数据（f / Z' / Z''）即可产出可复现、可发表的等效电路拟合结果。覆盖输入体检与符号定量判定、Lin-KK 校验口径（逐点残差 + Z/Y 表示法 + M 选取）、元素公式与自由参数核实、物理初值反解、多起点全局拟合与硬边界、剖面似然与 bootstrap 可辨识性、AICc 模型比较、多孔/传输线四步判据、电感扣除三候选判据、固定命名/目录/manifest 交付物与校验器、环境安装（国内镜像 + pip 缓存坑）与省 token 读法。当用户提供 EIS/阻抗谱数据并要求等效电路拟合、参数与不确定度、可辨识性分析、模型比较、扣除器件电感，或要求按规范命名归档拟合交付物时加载本技能。"
description_zh: "EIS 等效电路拟合全流程硬规范：E1–E18 硬门槛 + 九阶段流程 + 固定交付物命名与校验器，自带拟合核心、初始值反解、可辨识性分析与批次核查脚本。"
description_en: "A hard-gate protocol for reproducible equivalent-circuit fitting of EIS/impedance spectra: input health checks, Lin-KK validation, physical initial values, multistart global fitting with hard bounds, profile likelihood and bootstrap identifiability, AICc model selection, porous/transmission-line criteria, inductance removal, and fixed deliverable naming with a validator."
category: data-analysis
version: 6.1.0
author: Yangming Hu
license: Apache-2.0
---

> **技能包资源位置**（`<技能包>` ≡ 本 `SKILL.md` 所在目录；规范结构 = `SKILL.md` + `references/` + `scripts/`）
> | 用途 | 路径 |
> |---|---|
> | **拟合核心，不要重写** | `scripts/eis_core.py`（元素阻抗 + 多起点 + 剖面 + 官方对照，自带 `--selftest`） |
> | 案例骨架 / 输出物校验 / 环境检查 | `scripts/init_case.py`、`scripts/validate_eis_outputs.py`、`scripts/check_eis_env.py` |
> | **多份数据批量核查（E18）** | `scripts/scan_batch.py`（体检+拟合+组间离散度，一条命令出结论级 JSON） |
> | 安装到本机技能目录 / 打包自检 | `scripts/install.py`、`scripts/check_package.py` |
> | 参考（按需查，别整篇读） | @references/元素与公式.md（21 元素公式/CDC/判据/陷阱）、@references/器件元素清单.json（机器可读）、@references/实测依据.md（验证方法与可复现证据） |
> | 环境 / 安装 / 常见问题 | @references/环境与安装.md |
> | 许可与第三方声明 | @references/许可与第三方声明.md（摘要）；许可正文 `references/LICENSE`、归属声明 `references/NOTICE` |

# EIS 等效电路拟合规范 v6.1

> **用途**：本技能 + 数据文件路径 + 一两句说明交给 AI，即可得到可复现、可发表的等效电路拟合结果。
> **约束力**：本文件是执行规则的唯一来源，**§2 的 E1–E18 一条都不能省**；不得静默假设，所有假设必须写进报告。
> **用户不必指定模型细节**（权重、初值、起点数、是否放开 `n`、是否试多孔）——由 §1/§2 自动判定并说明理由。

## ★① 任务模板（复制这一段，和数据文件一起发给 AI）

```text
请按《EIS 等效电路拟合规范》技能（eis-fitting-protocol）做等效电路拟合分析。

【数据文件】[完整路径]
【电路（CDC）】[例如 [RL(RQ)(RQ)Wo]；或写"未指定，请按数据建议"]
【特别关注】[可留空；例如：Wo 的 n 该不该固定 / 低频扩散是否可辨识 / 是否该试多孔模型]

其余全部按技能默认执行，硬门槛 E1–E18 逐条执行并在报告中给出结论。
```

可选追加（要哪条复制哪条）：`【权重】改 proportional/unity/Boukamp 并报与 modulus 的差异`｜
`【固定/约束】R1 限 15–35 Ω；Wo 的 n 分别给"固定 0.5"与"放开"`｜`【指定检验】对 X 做剖面似然 + bootstrap，给 distinct 极小清单`｜
`【不做的步骤】跳过电感扣除（电感项已含在电路里）`｜`【命名】案例目录 <路径>，按 §4 命名并生成 s9_manifest.json`

## ★② 环境（首次运行先做，约 1 分钟）

```powershell
python <技能包>/scripts/check_eis_env.py          # 分 required / official / optional 三级报告
python <技能包>/scripts/check_eis_env.py --json   # 一行 JSON（给 AI 看，省 token）
```

只需 numpy/scipy 就能跑 `eis_core.py`/`init_case.py` 与 §1–§3；**pyimpspec** 是 E5（元素内省）与 E10（官方双实现互证）才需要，**deareis** 只是 DearEIS 桌面端（缺失不算 `NEEDS_INSTALL`）。要装就装进**独立 venv**（`pyimpspec 5.2.0` 要求 `numpy>=2.5`、`scipy>=1.17`、`matplotlib>=3.11`，装进 anaconda base 会连带升级这三个包）：

```powershell
python -m venv .venv_eis;  .\.venv_eis\Scripts\Activate.ps1;  python -m pip install -U pip
python -m pip install "deareis==5.1.3" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

国内镜像：清华 TUNA（推荐）/ 中科大 USTC / 阿里云 / 官方。
**⚠️ 报 `No matching distribution found for requests~=2.33` 时不是镜像缺包**，是本机 **pip 索引缓存过期**：加 `--no-cache-dir`，或先 `pip cache purge`。**不要**用 `--no-deps`。

## ★③ 省 token 读法（省"读两遍/写两遍"，绝不省检查）

| 要做什么 | 读这些 | 不要读 |
|---|---|---|
| 跑一次标准拟合 | 本文件 §1–§4 + `import eis_core` | `references/` 全部 |
| 查器件公式/默认值/上下限 | `references/器件元素清单.json`（grep 关键字） | 元素与公式.md 全文 |
| 遇到具体陷阱、要引用实测数字 | `references/元素与公式.md` 的陷阱/数值节 | 实测依据.md |
| 规范条款为什么这么定 | `references/实测依据.md` | — |

**十条纪律**：①只给路径不贴数据（一个 70 点谱 ≈ 2–4 k token，"脚本读文件 + 打印一行摘要"只要几十 token）；②脚本只打印结论级 JSON（`{"stage":"s2","M":11,"max_im_pct":1.40,"verdict":"fail"}`）；③结果写进 `results/*.json`，回复只说改了什么（≤3 行）；④改动用 diff，不重贴；⑤长文分段读；⑥维护 `facts.md`（≤20 行，确认过的版本/数字/结论）；⑦互不依赖的步骤合并成一条消息；⑧对话里数值只留 4 位有效数字（全精度只进 JSON）；⑨图不进对话（残差用最大/RMS/分频段表判断）；⑩结果落盘复用（`results/` + `work/` 保留，第二轮只读 JSON 不重跑）。

## 1. 执行流程（九个阶段 = §4 的命名前缀）

| stage | 做什么 | 主要产物 |
|---|---|---|
| `s1` | 读数据、体检、清洗 | `s1_data_clean.csv`、`s1_data_health.json` |
| `s2` | Lin-KK 校验 + 噪声量级 | `s2_kk_summary.json`、`s2_kk_residuals.csv`、`s2_kk_mscan.csv` |
| `s3` | 元素核实 → 物理初值 → 多起点拟合 | `s3_fit_<model>_<weight>.json` + `_spectrum.csv` + `_multistart.json` |
| `s4` | 剖面似然 + bootstrap | `s4_ident_summary.json`、`s4_ident_profile_<param>.csv`、`s4_ident_bootstrap.csv` |
| `s5` | 模型比较（AICc/F） | `s5_model_aicc.csv` |
| `s6` | 多孔/传输线四步判据 | `s6_porous_summary.json` |
| `s7` | 交叉验证（DRT / 独立实现 / 电感扣除） | `s7_*.json` |
| `s8` | 报告与图表 | `s8_report_main.md`、`s8_figure_*.png`、`s8_report_summary.xlsx` |
| `s9` | 环境与清单 | `s9_env_versions.json`、`s9_env_elements.json`、`s9_manifest.json` |

**一键起步**：`python <技能包>/scripts/init_case.py <案例目录> --case-name <名字>`（生成合规骨架，校验 0 违规）。

## 2. 硬门槛 E1–E18（**每条都要在报告里给出结论**）

| # | 判据 | 证据落盘 |
|---|---|---|
| **E1** | **输入口径**：①编码先探测（`utf-8-sig` 吃 BOM；**也要能读 GBK**）——只试 `utf-8` 会把 BOM 带进第一个数字；②分隔符**按首行 tab/comma/semicolon/pipe 计数显式判定**（禁止裸 `line.split()`——逗号数据会整行变一个字段；`split('\t')` 这类显式分隔符可以）；③**无表头文件**要能处理（第一行字段是否全可 `float` 判定表头；列数必须 3 = f, Z', Z''）；④符号（`Z''` 还是 `−Z''`）必须给**定量证据**：源文件列头 + 最高频相位 + 一次"反号对照拟合"（判据：正负号口径的 best SSE 差一个量级以上才作数；反号对照留 `s1_data_clean_flip.csv`）；⑤检查有限值、正频率、频率唯一 | `s1_data_health.json` 写明编码/分隔符/列头/是否取反及依据 |
| **E2** | **数据体检**：点数、频率范围与十倍频数、`\|Z\|` 范围、`Z''` 过零频率、`Z''` 在 log f 上的**内部极值个数**、是否对数等间隔。**⚠️ 极值个数只是描述，不是判据**：原始逐点极值计数**不抗噪、不可复现**，同一条谱换个口径（原始逐点 / 不同宽度的滑动平均 / 不同显著性阈值）能给出完全不同的个数，照原始计数加 RQ 块就会**凭空多出若干个弧**。两个坑：①**阈值必须是相对的**（如 `prominence > max(3σ_本频段, 2 % × 该点 −Z'')`）——用全频段 σ 的绝对阈值在真实谱上会恒等于 0、什么也报不出；②必须**同时报所用的平滑宽度与阈值**。**弧数最终由 E12（AICc）+ E13（残差结构）定** | `s1_data_health.json`（含两种口径与 σ） |
| **E3** | **Lin-KK 判据**：**逐点** `max\|ΔRe\|/\|Z\|` 与 `max\|ΔIm\|/\|Z\|` **均 < 1 %**（不是 RMS！RMS 小不能保证单点不超标）。**表示法必须声明并两种都跑**：同一份数据在 Z 与 Y 表示法下判据会翻转（同一份谱完全可以出现「Y 表示 FAIL / Z 表示 PASS」）；判据取**做等效电路拟合的那个表示法（Z）**并说明差异。报三个 M（`M_mu_criterion`/`M_best_chi2`/`M_used`）与选取理由；**M 由 μ 准则/Boukamp 定，不得为"让判据过关"而调 M**；μ 只作旁证，不作判据。写清配置（Z/Y、real/imaginary/complex、是否加 C/L、`F_ext` 固定还是搜索）。**pyimpspec 陷阱**：指定 `num_RC` 时必须同时给 `num_F_ext_evaluations=0` + `log_F_ext`，否则抛 `ValueError`；`perform_exploratory_kramers_kronig_tests` 的 `num_RCs` 必须留空 | `s2_kk_summary.json`（含 config 字段） |
| **E4** | **噪声量级**：高频点对点噪声 `σ ≈ std(Z_i − ½(Z_{i−1}+Z_{i+1}))/√1.5`（写明 ddof 与 Re/Im 口径）；残差水平必须与噪声量级比较后判定"够好"（Ω 与相对量级两个口径都要报） | `s1_data_health.json` 或 `s2_kk_summary.json` |
| **E5** | **元素核实**：从目标软件内省打印**公式 + 参数名 + 单位 + 默认固定状态 + 自由参数个数**；`equation` 字段与 `_impedance` 实现不一致时**以实现为准**（已知：`Ls` 的注册公式与实现差 76 %）；报告写明"哪些参数固定"。**可执行做法**：`pyimpspec.fit_circuit(parse_cdc(cdc), data).get_parameters()` → `{"R_1": {"R": FittedParameter(value, stderr, fixed, unit)}}`，`k` = 非 `fixed` 的个数（实测 `[RL(RQ)(RQ)Wo]` 的 `Wo_1.n.fixed=True` ⇒ k=10）。⚠️ **`Element` 实例没有 `get_parameters()`**（只有 `get_values()`/`set_values()`），别照直觉写 | `s9_env_elements.json` + 报告参数表 |
| **E6** | **初值必须物理**（禁用软件默认值）：`R_ser` = 最高频 `Z'` 均值；`L` = `dZ''/dω` 最小二乘斜率；**`R_k = 2·(-Z'')_peak / tan(nπ/4)`**（不是"两倍峰高"，n=0.8 会低估 27 %）；**`Y = 1/[R_k·(2πf_peak)^n]`**（写反会差 10⁶–10⁸ 倍）；`Wo` 的 **`B ≈ 1/(2π·f_cross)`**（B 是时间常数，单位 s）；`Wo` 与 `W` 的映射是 **`Y_W = Y^n`**（不是 `Y`）；`n` 先给 0.8–0.95。**初值只是种子，不保证好**——物理种子也可能离真解很远，靠多起点才收敛 | 报告"初值来源"表 |
| **E7** | **目标函数口径**：报告实际被最小化的是什么函数——**pyimpspec/lmfit 最小化的是 L4**（`_residual` 先平方分量误差、lmfit 再平方和 ⇒ `Σ(ΔRe⁴+ΔIm⁴)·w²`），而**它报告的 `pseudo_chisqr` 是二次口径** `Σ(|ΔRe|²+|ΔIm|²)·w²`（在 `modulus` 权重下等于 `Σ\|ΔZ\|²/\|Z_exp\|²`，可用自己的数据逐位验算）；`eis_core` 最小化 L2。**两者比值不是常数**（随残差量级变），**没有"换算系数"**，不同权重/口径的数值不得直接比较 | `s3_fit_*.json` 的 `payload.objective`（含 `weight` 与 `form`） |
| **E8** | **多起点**：起点数按参数个数（≤8 → ≥200；**9–12 → ≥300**；≥13 → 500–1000）；**必须含已知解种子**（逐分量裁剪到边界内，不要因某个分量超界就丢弃整条种子）；报告"**已发现的最低 SSE**"+去重后的解族，**参数口径与阻抗口径各报一次**（`n_distinct` / `n_distinct_spectrum`，另看 `top_solutions`）——不可辨识方向上的漂移会让参数口径虚报（同一条谱上两者差一个数量级很常见）；**禁止写"确认全局最优"** | `s3_fit_*_multistart.json` |
| **E9** | **边界与退化**：`bounds` 必须真的传给求解器（禁止用 `np.clip` 造边界——会形成平坦目标面）；**撒点范围 ≠ 硬边界**（把起点范围当边界会把 `n` 夹在 0.5–0.7311：实测真值 0.85 被夹成 0.7311、最大残差 3.73 %，放宽后 0.000 %）。退化要看**两个层次**：①**贴硬边界**（`params_on_hard_bound` + `bound_distance_theta`）；②**跑出物理合理窗口**（`params_outside_plausible_range`，对正量比对撒点窗口 START_LO/HI）——只报①会漏掉「某个串联电阻被推到比合理窗口低 8 个数量级、却离硬下界还差 0.65 个 log10」这类事实退化。**⚠️ 最低 SSE 常常来自退化解**：退化解可以把 SSE 压得更低、**最大残差反而更大**，无贴界解的最大残差常常明显更小。**无前缀字段描述 `best_params`，`valid_` 前缀描述 `best_valid_params`，两者不要混报**；当 `params_on_hard_bound` 或 `params_outside_plausible_range` 非空时必须改报 `best_valid_*` 作结论，或换模型 | `s3_fit_*.json` 的边界/退化字段 + `best_valid_*` |
| **E10** | **双实现互证**：官方 API（`pyimpspec.fit_circuit`，权重 `modulus`/`proportional`/`unity`/`boukamp`）+ 自写 scipy 各跑一次；**先统一目标口径再比较**（L4 vs L2 本来就不该完全一致）；差异要能由口径解释。元素级对照用 `eis_core.compare_official("[RL(RQ)(RQ)Wo]", p, f)`（实测 **1.75×10⁻¹⁶**；CDC 不要写 `R_1{...}` 标签，会抛 `InvalidElementSymbol`；参数名对不上会抛 `KeyError` 而不是静默跳过）。**对照必须配"注入敏感性"检查**（改参数后谱必须真的变），否则会退化成拿 CDC 内联初值和自己比 | `s7_check_dual.json` |
| **E11** | **可辨识性**：剖面似然（**把目标分量从优化向量里删除**，不是只钉初值；⚠️ **`grid` 是 θ 空间**——用 `to_theta(idx, [物理值...])` 生成，报告横轴用 `from_theta` 换回物理值；直接传 0.85 会静默固定成 0.70）+ bootstrap（写明①重采样对象②是否分块③Re/Im 是否成对④起点策略）。剖面起点要给已知解种子（`known=`），否则不可辨识方向会抽风。**不可辨识参数只能报区间并标注"受约束/外推"**，不得当测量值报（`B` 的拐点频率落在测量窗口外时就不可辨识）。**成本提醒**：N≥200 次完整重拟合很贵（每次都是一次完整多起点拟合），要并行或降低每次起点数，并在报告里写明起点策略 | `s4_ident_summary.json`、`s4_ident_profile_*.csv`、`s4_ident_bootstrap.csv` |
| **E12** | **模型比较**：AICc 必须在**同一权重、同一频率子集、同一残差口径**下计算（官方 `fit_circuit` 的 `pseudo_chisqr` 是二次口径，全模型统一用它即可）；`k` = E5 的"非 `fixed` 个数"（用 `n·ln(SSE/n)` 时再加 1）。**⚠️ 每个候选模型都必须先按 E6 给物理初值、再按 E8 多种子**，否则比的是"各模型各自落到的局部极小"——用软件默认初值直接排名可以把**错误拓扑**排到第一，而换物理初值后排名会整体翻转。**⚠️ AICc 只在"合格性"筛过之后才能用来排名**（见 E16）：先看每个候选的最大相对残差是否与 E4 的噪声同量级；**若连最优候选都 ≫ 噪声，就不存在"哪个模型更好"，只能报"本电路族全部不合格"**（实测：同一批多弧谱里，有的候选族最优解最大残差 15–16 % 而噪声只有零点几个百分点，此时 ΔAICc 的排名毫无意义）。**ΔAICc 不是置信概率**；嵌套 F 检验要注意前提（删整块 RQ、参数在边界、指数消失时渐近分布不成立，改用 bootstrap）。**`eis_core` 只内置主电路**，比较别的模型走 `pyimpspec.parse_cdc` + `eis_core.z_cdc` / `fit_circuit`（不要改 `z_model`） | `s5_model_aicc.csv` |
| **E13** | **多孔/传输线四步判据**：①比 ΔAICc 与最大残差（不是只看 SSE）②算特征频率 `f_L = ω_L/2π` 是否落在窗口内 ③对关键参数做剖面（报网格与判定口径）④检查参数跑飞/贴界。**注意**：`Tlmbo` 与重参数化 `Wo` 解析恒等（可自己用 `z_cdc` 验到机器精度），**不是独立物理证据**；`R_ct`/`R_B` 随 `L` 标度（`L→aL` 时 `R_ct→a·R_ct` 而阻抗不变），不是"与长度无关的绝对量" | `s6_porous_summary.json` |
| **E14** | **电感扣除（若做）**：三个候选（`dZ''/dω` 斜率=下界 / 使顶部十倍频 `Z''_corr` 单调不增的最大许可 L=上界 / 等效电路拟合值）+ **双条件**（校正后 Lin-KK **逐点**残差下降且 ≤ 噪声；顶部十倍频 `Z''_corr` 单调不增）。**不得直接采用拟合值**（自证）；写明最终取值与理由。若残差图呈现"高频段系统性偏差"（最大残差集中在顶部十倍频），先怀疑电感模型（理想 `L` vs 非理想 `La`）再做扣除 | `s7_check_l-selection.json`、`s1_data_clean_lc.csv` |
| **E15** | **输出物合规**：按 §4 命名与分类；`results/` 只放交付物（调试进 `work/`）；`s9_manifest.json` 覆盖全部文件且 sha256 一致；跑校验器**新增违规 = 0** | `<case>/work/output_spec_report.json` |
| **E16** | **报告必报项**：权重+为什么选它；求解器/容差/起点数；参数表（**值 + 区间**，非对称给上下界，顶界不报对称 σ）；**最大与 RMS 相对残差（注明口径）**；优化目标；残差图（Re/Im 分开）；派生量（τ、f_peak、C_eff、σ、外推 R_dc）；可辨识性结论；**模型比较只报通过合格性筛的候选**。**⚠️ 拟合合格性**：最大相对残差必须与 E4 的噪声量级比较；若**最大残差比噪声大一个数量级以上**、或残差呈**系统性频段偏差**，必须写明「该模型对本谱不合格」，并继续 E12/E13 换模型，**不得直接给参数结论** | `s8_report_main.md` |
| **E17** | **数字可追溯**：报告里每个数字都能在 `s9_manifest.json` 找到产地（脚本 + 输入 + sha256）；**不得手抄数字** | manifest + 重跑脚本 |
| **E18** | **多份数据 / 重复测量**（用 `scripts/scan_batch.py` 一条命令跑完）：同一电池的多份谱**逐份独立走 s1–s4**（不得先平均再拟合，除非说明理由）；报告必须给**组间离散度**（各份同一参数的值与极差/中位数），并与之比较：组间差异通常**远大于**谱内噪声（常常大 1–2 个数量级）⇒ **组间差异才是主导不确定度**；参数跨样品/跨状态的比较必须超过该离散度才有意义。若某份谱给出退化解（串联电阻→0、指数贴界）而另一份正常，**必须报告该不一致**并说明模型/约束不稳健（同一体系的不同谱可以给出完全不同的串联电阻与弧电阻），不得只报"最好看"的那份 | `s1_data_health.json`（每份）、`s8_report_main.md` 离散度表 |

> **门槛没过的处理**：E3 不过 → 先查表示法与配置、再怀疑样品；E8/E9 触发贴界或退化 → 该参数视为受约束，改报区间或换模型；E11 不可辨识 → 不得进结论表；E18 出现"某份退化解、另一份正常" → 报告模型/约束不稳健，不得只报最好那份。

## 3. 代码：**用 `eis_core.py`，不要重写**

```python
import sys; sys.path.insert(0, r"<技能包>/scripts")
from eis_core import (z_model, z_rq, z_wo, z_w, z_g, z_la, z_cdc,   # 元素阻抗 / 任意 CDC
                      global_fit, profile, to_theta, from_theta,    # 多起点 / 剖面
                      sse_rel, quality, compare_official,           # 指标 / 官方对照
                      PARAM_NAMES, pack, unpack)
check_data(f, z, 10)                     # E1 的可执行版：长度/有限值/正频率/重复频率/欠定 全部拦住
out = global_fit(f, z, n_starts=300)      # → best_sse/best_valid_*/n_distinct*/贴界字段/top_solutions
print(out["best_sse"], out["n_distinct_spectrum"], out["params_within_1_of_bound"])
if out["params_on_hard_bound"]:            # 最低 SSE 解贴界 ⇒ 结论改用无贴界解
    print("valid:", out["best_valid_sse"], out["best_valid_quality"])
prof = profile(f, z, 4, to_theta(4, [0.7, 0.85, 0.95]), known=out["best_valid_params"])
```

- 自检：`python <技能包>/scripts/eis_core.py --selftest`（参数回收 PASS、解析 Jacobian 校验 PASS、官方实现对照 **2.1×10⁻¹⁶**、固定真值 `n2` 的剖面 SSE ~1e-30、无参数贴硬边界）。
- 已修掉三个真实回归：**硬边界不能取撒点范围**、**剖面 grid 是 θ 空间**、**`tanh`/`exp` 溢出告警**（`z_wo` 裁 `Re(x)` 到 ±40、`sig` 用 `tanh` 写法）。
- **速度**：默认两阶段（松容差粗筛全部起点 → 紧容差精修最好的若干**盆地代表**），同一 `seed` 下 `best_sse` 与单阶段一致到 ~1e-14，耗时约为其 1/2–1/7；`jac="analytic"` 可再省差分评估（见 `global_fit` docstring）。
- 复数幂用 `(1j*w)**n`；`coth` 一律写 `1/np.tanh(x)`（`cosh/sinh` 会溢出）；残差加 `np.isfinite` 保护。
- 用官方元素时：`pyimpspec` 极端参数会抛 `InfiniteImpedance`，循环里要 `try/except`；**报告用的谱必须在"只用最优参数新建的对象"上重算**。
- **主电路之外的模型**（多孔/传输线/加弧）不要改 `z_model`：用 `z_cdc(cdc, f, values)` 或 `pyimpspec.fit_circuit(parse_cdc(cdc), data)`。

## 4. 输出物

```
<case>/ data/  results/  work/  scripts/
```
- **命名语法**：`<stage>_<subject>[_<tag>...].<ext>`；全小写 ASCII；`_` 分字段、`-` 分字段内部；模型用 CDC slug（`[RL(RQ)(RQ)Wo]` → `rl-rq-rq-wo`）。
- **最小交付集合**：`s1_data_clean.csv`、`s2_kk_summary.json`、`s3_fit_<model>_<weight>.json` + `_spectrum.csv`、`s4_ident_summary.json`、`s8_report_main.md`、`s9_env_versions.json`、`s9_manifest.json`；图 5 张（nyquist/bode/residual/kk/profile）。
- **JSON 信封**（每个结果 JSON）：`schema/stage/case/generated_at/inputs/code/env/status/payload`，结果一律进 `payload`。
- **CSV 列名**：小写 + 单位后缀（`f_Hz, Z_re_ohm, Z_im_ohm, Zfit_re_ohm, resid_re_pct, param, value, stderr, p16, p50, p84, M, mu, rms_pct, tau_s, gamma_ohm, aicc, delta_aicc`）。
- **禁用**：`final`/`new`/`test`/`dbg`/尾随数字/日期/人名前缀；版本靠**覆盖重生成 + `run_id`/sha256**，不靠改名。
- **跨平台提醒**：Windows/macOS 的文件系统**大小写不敏感**，`S1_x.csv` 与 `s1_x.csv` 是同一个文件 ⇒ "文件名全小写"这条在本地测不出来，必须在 Linux 上或打包流程里查。
- **校验**：`python <技能包>/scripts/validate_eis_outputs.py <case>`（检查 C1–C9，退出码非 0 = 不合规，报告写到 `<case>/work/output_spec_report.json`；既有项目先 `--baseline=<file>` 冻结历史违规，此后只允许"新增 = 0"）。

## 5. 速查：坑 → 正确做法（全部来自实测；详细依据见 `references/元素与公式.md` 陷阱节）

| 坑 | 正确做法 |
|---|---|
| `line.split()` 读逗号 CSV | 用 `csv`/`read_csv`；TAB 数据用显式 `split('\t')` |
| 没试 `utf-8-sig` | BOM 会混进第一个数字；符号不能靠"应该感性"猜，要 E1 的定量证据 |
| 只看 RMS 判 K-K | 判据是**逐点最大值** |
| 只跑一种表示法 | Z 与 Y 都跑（同一数据判据会翻转） |
| 用软件默认初值 | 用 E6 物理初值，但**多起点才是关键**（种子本身可能很差） |
| `Y = (2πf)^n/R` | `Y = 1/[R(2πf)^n]`（写反差 10⁶ 倍以上） |
| "两倍峰高"估 R | `2(-Z'')_peak/tan(nπ/4)`（n=0.8 时会低估 27 %） |
| `B = √(1/(2πf_min))` | `B` 是时间常数，`f_cross ≈ 1/(2πB)` |
| `Wo` 与 `W` 共用 `Y` | 须 `Y_W = Y^n`（否则高频段差 3000 %） |
| `clip` 造边界 / 撒点范围当硬边界 | 传 `bounds`；硬边界与贴界判据见 E9 |
| `profile` 传物理值当 grid | 用 `to_theta` 生成、`from_theta` 报告横轴 |
| 只报最低 SSE 或参数口径解数 | 报 `best_valid_*` 与 `n_distinct_spectrum`，并报最大残差 |
| 同一逻辑产物两个名字 | 只保留规范名（版本靠 `run_id`/sha256） |

## 6. 参考与版本

- 元素公式/CDC/选型/判据/陷阱全文 → `references/元素与公式.md`；机器可读元素表 → `references/器件元素清单.json`；每条规则的实测数字与"已撤回的疑点" → `references/实测依据.md`；命名校验规则 C1–C9 → `validate_eis_outputs.py` 的 docstring。
- 技能版本 **v6**（2026-10）。
- 作者：**Yangming Hu**。许可：本包自研部分为 **Apache License 2.0**（正文 `references/LICENSE`，归属声明 `references/NOTICE`，摘要见 @references/许可与第三方声明.md）；第三方依赖 pyimpspec（GPL-3.0-or-later）与 DearEIS（GPLv3 or later）**不含其代码**，仅为运行时依赖。环境基线 pyimpspec 5.2.0 / deareis 5.1.3 / lmfit 1.3.4 / numpy 2.5.3 / scipy 1.18.1 / matplotlib 3.11.2 / Python 3.12.14；换版本后重跑 `check_eis_env.py` 与 `eis_core.py --selftest`，器件数字以本机内省为准。
- v6 修订（相对 v5，全部有实测依据；第二轮自查又有 7 处已并入）：修 `tanh`/`exp` 溢出；补 **Z/Y 表示法**与 **`pyimpspec` 的 `num_RC`/`num_F_ext_evaluations` 互斥陷阱**（E3）、**阻抗口径去重 `n_distinct_spectrum`**（E8）、**θ 空间边界距离 + 退化解警戒 `best_valid_*`**（E9）、**无表头/TAB/BOM 输入**（E1）、**多模型走 `z_cdc`/`fit_circuit`**（E12/E13）、**`from_theta` 与剖面已知解种子**（E11）；**修 `z_cdc`/`compare_official` 参数注入静默失效**（`element_index` 双别名 + 未知名抛 `KeyError` + selftest 注入敏感性对照）；补 **CDC 标签语法**（`R_1{...}` 非法）与 **`Element` 无 `get_parameters()`** 两个 API 陷阱（E5）；**E12 补"每个候选模型必须先给物理初值 + 多种子"**（默认初值会让 AICc 排名整体翻转）；**修正"L4/L2 有固定比值"的错误说法**（E7，实测比值随残差变）；E13 补 `Wo.n` 必须显式设 `n/2`；E1 补反号对照文件名 `s1_data_clean_flip.csv`；校验器补 `flip` tag 与 `chi2/pseudo_chi2/sigma` 列、对齐最小交付集合；环境检查改三级；`references/` 从 210 KB 压到 49 KB（−77 %）、整包 zip 从 116 KB 压到 61 KB（−47 %）。
