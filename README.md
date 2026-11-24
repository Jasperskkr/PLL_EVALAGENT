# PLLAgent

面向整数 N 电荷泵锁相环（Integer-N CPPLL）的行为级联合规格分配工具。

PLLAgent 根据系统指标和模块参数范围，结合物理反解、数值搜索与行为仿真，生成并验证多组参数候选。项目提供确定性、LLM 引导和混合三种策略，用于研究固定拓扑下的参数分配与验证反馈。

[快速开始](#快速开始) · [配置说明](#配置说明) · [输出结果](#输出结果) · [开发与测试](#开发与测试) · [文档](#文档)

## 功能

- **联合参数分配**：在给定范围内搜索 `Icp`、`Rz`、`C1`、`C2`、`f0` 和 `Kvco`，保留满足质量与差异要求的候选。
- **多种搜索策略**：支持确定性搜索、LLM 物理工具选择，以及先确定性搜索再按需使用 LLM 的混合模式。
- **分层验证**：通过连续模型（M1）检查带宽、名义相位裕度和调谐点，再通过独立行为仿真（M2）测量带宽与条件捕获时间。
- **反馈重分配**：根据 M2 结果，在剩余预算内选择其他候选或重新分配参数。
- **条件物理与噪声**：可选连续噪声预测、启动候选构造和统一排序；另有独立原生噪声/非理想验证后端，预测与正式验证分开记录。
- **VCO 开发交接**：从正式结果导出 VCO guidance，检查实测反馈和用户硬约束，准备回填 `f0/Kvco` 后的重新验证输入。
- **结果记录**：保存候选、工具决策、测量证据及 M1、M2、LLM 调用成本。

```text
系统指标 + 参数范围
        ↓
策略选择 → 物理反解 / 数值搜索 → M1 评价与候选池
                                      ↓
                              独立复核与 M2 验证
                                      ↓
                          验证结果 → 预算内反馈重分配
```

LLM 负责选择工具、搜索区域和预算；参数由计算工具求解，执行器负责约束检查与预算控制，验证器给出判决。

## 适用范围

标准流程采用固定拓扑的 Integer-N CPPLL 行为模型：参考频率 10 MHz、控制电压范围 0–1.2 V，反馈分频比读取当前问题的正整数 `fixed_parameters.N.value`，目标输出为 `N × f_ref`；nominal 示例仍为 N=8、80 MHz。包含理想对称电荷泵、线性 VCO 和既定的两电容一电阻环路滤波器。不同 N 的候选仍须满足调谐与数值分辨率条件，详见[运行说明](docs/RUNNING.md)。

| 验证层级 | 支持的指标 | 适用条件 |
| --- | --- | --- |
| M1：连续模型 | 带宽、名义相位裕度、静态调谐点 | 当前拓扑和输入参数范围 |
| M2：行为仿真 | 带宽、条件捕获时间 | 指定激励与初态；捕获测试初始控制电压 0.15 V，观测窗口 160 µs |

项目处于研究原型阶段，输出为行为模块参数。晶体管尺寸、器件可实现性、版图和 PVT 验证不在当前范围内。标准 M2 尚未认证周期相位裕度及完整 jitter/power 指标；未支持、未测量或数值无法判定的项目保留为 `UNKNOWN`。可选噪声、非理想和相位响应扩展见[运行说明](docs/RUNNING.md)。

当前尚无充分的对照证据证明 LLM 策略优于确定性策略。

## 快速开始

### 环境要求

- Python 3.11 及以上，推荐 Python 3.12。
- M1 分配依赖 NumPy 和 SciPy，无需编译原生内核或配置 API。
- 原生 M2 已验证环境为 Windows x64、Visual Studio 2022 Community C++ 工具链（C++17）。构建脚本使用 VS 的默认安装路径。

以下命令使用 PowerShell，均从仓库根目录执行。

### 1. 安装

```powershell
git clone https://github.com/Jasperskkr/PLL_EVALAGENT.git
cd PLL_EVALAGENT
$env:PYTHONUTF8 = "1"
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[integration,test]"
```

### 2. 运行 M1 示例

```powershell
python tools/run_allocation_examples.py --case nominal_m1 --case tight_m1 --out experiments/m1_example
```

该命令分别运行普通约束和紧约束问题的确定性分配，仅执行 M1。汇总结果位于 `experiments/m1_example/summary.json`，每个案例的报告位于对应的 `<case>/run/allocation_report.md`。

### 3. 运行 M1 + M2 分配

先构建标准行为仿真内核，再运行完整分配流程：

```powershell
cmd /c pll_allocation\verification\build_kernel.cmd
python -m pll_allocation pipeline --problem configs/problems/nominal.json --out experiments/joint_example
```

默认使用 `configs/agent/spec_allocation.json`：确定性策略，先构造 5 个不同的 M1 候选，目标交付 3 个正式 M1＋原生 M2 已支持指标通过点；总预算为 96 次 M1 和 8 次 M2，最多 2 次反馈搜索（含补点）。首个通过后继续验证，预算耗尽时如实交付部分结果。运行结束后查看 `experiments/joint_example/allocation_report.md`。

每次运行都需要新的输出目录；构建脚本也会拒绝覆盖已有构建目录。再次运行时请更换目录名。更多示例、构建选项和故障排查见[运行说明](docs/RUNNING.md)及[工具说明](tools/README.md)。

## 配置说明

问题配置定义系统指标、启用项和六个参数的范围；策略配置定义搜索方式、候选数量与调用预算。

| 配置位置 | 用途 |
| --- | --- |
| [`configs/problems/`](configs/problems/) | 系统指标、固定模型参数和搜索范围 |
| [`configs/agent/spec_allocation.json`](configs/agent/spec_allocation.json) | 策略模式、候选数量、质量阈值和总预算 |
| [`configs/providers/messages.json`](configs/providers/messages.json) | LLM 服务参数及环境变量名称 |
| [`configs/verification/`](configs/verification/) | M2 测量协议和反馈配置 |

复制已有配置后，通过统一入口传入自己的文件：

```powershell
python -m pll_allocation pipeline --problem path/to/problem.json --allocator-config path/to/allocator.json --out experiments/custom_example
```

六个参数的输入单位依次为 `Icp [A]`、`Rz [Ohm]`、`C1 [F]`、`C2 [F]`、`f0 [Hz]`、`Kvco [Hz/V]`。当前反解路径要求启用正的带宽目标。将策略配置中的 `m2_budget` 设为 `0` 可仅执行 M1。

`mode` 支持以下取值：

| 模式 | 行为 |
| --- | --- |
| `DETERMINISTIC` | 使用物理反解与确定性搜索，默认模式 |
| `LLM_PHYSICS_GUIDED` | 由 LLM 根据当前观察选择物理工具与搜索动作 |
| `AUTO_HYBRID` | 先进行确定性搜索，候选数量或质量不足时再使用 LLM |

完整字段、预算计数和候选筛选规则见[多策略分配说明](docs/SPEC_ALLOCATION.md)；其他配置见[配置目录说明](configs/README.md)。

### 噪声与启动增强

默认配置保留原分配行为。`configs/agent/noise_aware.json` 与 `physics_enhanced.json` 分别提供条件噪声和完整物理增强配置，可通过同一个 `--allocator-config` 入口使用。连续噪声预测复用已有 PSD/积分模型；独立时域噪声验证需另建非理想/噪声后端，见[运行指南](docs/RUNNING.md)。条件预测不赋予标准 M2 jitter/PM 通过资格，可选扩展仍遵守各自的 N=8 适用域。

### 使用 LLM

LLM 模式需要支持 Messages API 的 HTTPS 服务，以及以下本机环境变量：

| 环境变量 | 内容 |
| --- | --- |
| `ANTHROPIC_BASE_URL` | 服务地址 |
| `ANTHROPIC_AUTH_TOKEN` | API 凭据 |
| `ANTHROPIC_MODEL` | 模型名称 |

完成 M2 内核构建并设置环境变量后，可运行 LLM 示例：

```powershell
python tools/run_allocation_examples.py --case llm --allow-paid-llm --out experiments/llm_example
```

`--allow-paid-llm` 授权该示例在配置预算内发起真实 API 调用。默认配置的 `allow_paid_llm=false`；使用自定义策略配置时，需要同时设置该开关、`llm_budget` 并传入 `--llm-config configs/providers/messages.json`。凭据应保存在本机环境中。

## 输出结果

多候选分配的输出目录包含以下主要文件：

| 文件或目录 | 内容 |
| --- | --- |
| `run_manifest.json` | 多候选运行的统一索引；指向权威输入快照、结果、成本与下游交接文件，并记录文件 SHA256 |
| `allocation_report.md` | 参数候选、推荐依据和验证结果的可读报告 |
| `allocation_result.json` | 运行状态、候选统计、推荐结果和失败原因 |
| `candidates.json` | 六参数候选、单位、M1 指标与已执行的 M2 结果 |
| `sizing_handoff.json` | 多个联合通过的行为目标及证据，只收录质量/差异达标且原生 M2 已支持项通过的点 |
| `cost_summary.json` | M1、M2、LLM 调用次数与执行成本 |
| `execution_route.json` | 实际执行路径及配置来源 |
| `initial/`、`verification/` | 搜索轨迹、候选记录、独立复核和反馈证据 |

下游应读取 `sizing_handoff.json.candidates`，并检查 `joint_status` / `joint_target_reached`：预算内可能只交付部分点。`target_count` 控制 M1 池，`m2_target_count` 控制联合通过目标，两个目标独立；旧配置省略后者时保留首个通过停止。`recommended_M2_supported` 仅在原生 M2 已支持项通过时有值；`recommended` 仍可能回退到仅 M1 点。所有结果均不代表完整 SystemSpec、管级或 PVT 已获认证。

示例问题有意保留未支持的 jitter 约束，因此即使已支持项通过，也可能仍有 `UNKNOWN` 项。详细状态定义见[配置与结果合同](docs/SPEC_ALLOCATION.md#输出与判决)。

### VCO contract

完整分配后，可显式导出后续 VCO 开发合同：

```powershell
python -m pll_allocation.vco_sizing export --handoff experiments/joint_example/sizing_handoff.json
```

导出复用共享交付门禁，保留原交接文件；目标频率确认、局部 `Kvco/f0`、CP 合规区间和实测条件分别校验。`assess` 检查物理反馈，`prepare` 生成重新验证输入；实际分配与 M2 仍由正式 pipeline 执行。详见 [VCO Sizing Contract](docs/VCO_SIZING_CONTRACT.md)。

## 项目结构

程序对接从 `run_manifest.json` 定位文件。下游交付只消费 `sizing_handoff.json`，可用 `pll_allocation.delivery.validate_sizing_handoff` 校验摘要、候选及正式证据；`recommended` 可能只是 M1 诊断推荐，不能作为正式交付。`initial/verification_handoff.json` 则供 M2 接续执行；新运行支持连同整个运行目录迁移，旧阶段名副本仅用于兼容。具体清洗边界见 [结构审核](docs/STRUCTURE_AUDIT_20261124.md)。

```text
pll_allocation/
├── pipeline.py         # 统一命令入口与流程调度
├── io_contracts.py     # 严格外部 JSON 与权威产物索引
├── delivery.py         # 生产端和下游共用的正式交付校验
├── agent/              # 策略、候选池、预算与反馈重分配
├── allocation/         # 物理反解与分配算法
├── exploration/        # 问题定义、物理区域与敏感度分析
├── region_explorer/    # Sobol 采样与 SLSQP 局部优化
├── physics_mapping/    # M1 连续模型与物理映射
├── verification/       # C++ 行为内核、测量与 M2 判决
├── vco_sizing/         # 可选 VCO 开发合同、反馈与回填输入
└── studies/            # 可选对照研究
configs/                # 问题、策略、模型与验证配置
tools/                  # 示例运行与维护工具
tests/                  # 回归测试与轻量夹具
docs/                   # 架构、运行与开发文档
```

## 开发与测试

完整测试需要先构建标准内核及三个可选后端：

```powershell
cmd /c pll_allocation\verification\build_kernel.cmd
cmd /c pll_allocation\verification\build_phase_step.cmd
cmd /c pll_allocation\verification\build_return_ratio.cmd
cmd /c pll_allocation\verification\build_nonideal.cmd
python -m pytest -q
```

已构建的后端无需重复构建。部分历史档案测试在档案缺失时会显式跳过，原因见[测试边界](docs/RUNNING.md#测试边界)。离线 LLM 测试使用模拟策略，不会发起付费 API 调用。

开发前请阅读 [AGENTS.md](AGENTS.md) 和[兼容性说明](docs/COMPATIBILITY.md)。欢迎通过 [Issues](https://github.com/Jasperskkr/PLL_EVALAGENT/issues) 反馈问题；复现信息建议包含运行环境、命令、配置与错误摘要。实验输出、API 原始日志、凭据和编译产物保存在本地。

2026-11-24 集成验收已覆盖 N=4/8/10/16、不同 BW/PM/lock、失败重分配和边界输入：12组流程的211项产物检查通过。N4/N10案例仅部分交付，完整结果与适用条件见[多规格验收](docs/SPEC_MATRIX_AND_REMOTE_20261124.md)。完整回归958通过、10项历史档案依赖跳过；具体提交版本的发布复核见[提交版本审核](docs/PUBLISH_AUDIT_20261124.md)。

## 文档

- [当前代码状态与推送交接](docs/CODE_STATE_20261124.md)：集成改动、验收证据、分支与远端状态。
- [提交版本审核](docs/PUBLISH_AUDIT_20261124.md)：发布范围、独立检出构建与全链路验收。
- [VCO 开发合同](docs/VCO_SIZING_CONTRACT.md)：guidance、实测反馈、约束与回填再验证。
- [运行指南](docs/RUNNING.md)：安装、原生构建、示例与故障排查。
- [多策略分配](docs/SPEC_ALLOCATION.md)：模式、配置字段、预算与结果语义。
- [架构说明](docs/ARCHITECTURE.md)：模块边界与主要调用链。
- [代码导读](docs/CODE_MAP.md)：源文件职责与阅读入口。
- [研究范围](PROJECT_CHARTER.md)与[审查指南](docs/REVIEW_GUIDE.md)：研究目标、证据要求和能力边界。
- [命名规则](docs/NAMING.md)与[兼容性说明](docs/COMPATIBILITY.md)：模块命名及历史接口。
- [变更记录](docs/RELEASE_NOTES.md)：重构、迁移与历史验收记录。
