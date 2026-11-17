# PLLAgent：行为级联合规格分配

给定系统规格、固定 PLL 拓扑和六个模块参数的范围，由确定性策略或真实 LLM Agent 调用物理反解与搜索工具生成联合候选，再用独立 M1 / M2 验证。验证失败时，Agent 可以在预算内读取反馈、重新分配并复验。

这是适合代码审查和策略研究的行为级原型。目前尚未证明 LLM 比确定性方法更快、更可靠；不提供晶体管可实现性保证。

```text
SystemSpec + 六轴范围
 → Policy 决策 → 物理反解 / 搜索 → 正式 M1
 → 独立复核 → Verification Handoff → 真实 M2
 → 测量判决 → 可选反馈重分配 → 参数、证据与成本
```

## 当前支持什么

- 固定 Integer-N CPPLL：10 MHz 参考、N=8、80 MHz 输出、0–1.2 V 控制轨。
- 六变量：`Icp / Rz / C1 / C2 / f0 / Kvco`，输入合同使用 SI 单位。
- M1：连续模型 BW、名义 PM、调谐点。M2：独立 BW、指定初态下条件捕获时间。
- LLM 选择策略、工具、区域和预算；工具算参数，Runner 控制执行，验证器决定状态。
- 不支持、未测和不收敛保持 UNKNOWN；M1 PM 不等于 M2 周期 PM，不签发完整 SystemSpec 认证。

## 快速开始

先完成下文依赖安装与原生理想内核构建，再运行多候选分配（确定性优先，含预算内原生 M2 和确定性反馈）：

```powershell
python -m pll_allocation pipeline --problem configs/problems/nominal.json --out experiments/my_pool_01
```

省略 `--allocator-config` 默认使用三模式配置 `configs/agent/spec_allocation.json`。只给 `--out` 也走新版，使用明确记录的 nominal 示例；自定义问题请传 `--problem`。旧冻结链必须显式加 `--legacy-frozen`，不再隐式回落。每次启动打印实际路由，输出 `execution_route.json`；不同模式参数混用会在运行前报错。

`spec_allocation.json` 的 `mode` 可选 `DETERMINISTIC`、`LLM_PHYSICS_GUIDED`、`AUTO_HYBRID`；`target_count` 为 K，`m1_budget`/`m2_budget` 是含独立复核及 posthoc 的总预算。`minimum_margin` 与 `minimum_distance` 分别控制正式 M1 最小归一化裕量和六轴归一化距离。默认 Cold Start 零校准反解，候选不足再搜索；M2 先试高质量、不同的池内候选，再按预算反馈重分配。达到 K 仅结束 M1 搜索；可继续 M2 找至少一个支持指标通过点。

`AUTO_HYBRID` 在 `deterministic_rounds` 内先做确定性搜索，数量/质量不足才进入 LLM 分支；M2 反馈也先确定性处理，未取得合格结果时可在后续重分配启用 LLM。`allow_paid_llm=false` 为默认硬门禁，进入 LLM 分支会如实报告未授权，保留已找到的候选；不会自行调用真实 API。真实运行须用户明确授权后设置该开关和 `llm_budget`，并提供 `--llm-config`。离线 Policy 测试不证明真实 LLM 的分配收益。

主结果为 `allocation_result.json`、`candidates.json`、`cost_summary.json`、`allocation_report.md`。每个候选包含带单位六参数、正式 M1、裕量、来源和已运行 M2 的完整观察。`recommended_M2_supported` 仅在真实原生 M2 已支持项通过时非空；`recommended` 可回退为明确标注的 M1 点。M2 PM/jitter 仍 UNKNOWN，未签发完整 SystemSpec 认证。设置 `m2_budget=0` 可仅运行多点 M1；旧配置和单点入口继续可用。

配置、判决和产物合同见 [多策略分配说明](docs/SPEC_ALLOCATION.md)。下述安装和原生构建完成后，可以使用[复现工具](tools/README.md)重新运行 nominal/tight、反馈、LLM 与 Auto 输入案例；它只生成输入并调用正式 Pipeline，不需要历史实验数据。

从仓库根目录运行。已验证环境为 Windows x64、Python 3.12、MSVC 2022 Community C++17，不依赖原作者的磁盘路径。

```powershell
$env:PYTHONUTF8 = "1"
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[integration,test]"
python -m pll_allocation pipeline --help
```

**保留的连续域单点配置（只执行 M1）：**

```powershell
python -m pll_allocation pipeline --problem configs/problems/nominal.json --allocator-config configs/agent/deterministic.json --out experiments/my_allocation_01
```

**新版真实 LLM 分配：**先在本机设置 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_MODEL`。名称沿用现有环境合同，实际服务须支持 Messages-compatible HTTPS 请求；以下命令明确授权本次预算内调用。

```powershell
python tools/run_allocation_examples.py --case llm --allow-paid-llm --out experiments/my_agent_01
```

**真实 M2：**默认脚本使用 VS 2022 Community 标准安装位置，拒绝覆盖已有构建目录。

```powershell
cmd /c pll_allocation\verification\build_kernel.cmd
python -m pll_allocation pipeline --handoff experiments/my_allocation_01/verification_handoff.json --verification-problem configs/problems/nominal.json --verification-config configs/verification/verify_only.json --out experiments/my_verification_01
```

需要真实 Agent 反馈时，将验证配置换为 `configs/verification/feedback.json`，并传入 `--llm-config configs/providers/messages.json`。必须先有 `gate_status=READY` 的 Handoff。输出目录及分配的同名 `_calibration` 目录都必须全新。

默认例题保留原合同中的待验证和未支持指标，用于显式展示能力边界。修改问题 JSON 可设置规格、启用项及六轴范围；当前反解路径需要启用正 BW 目标。

## 按职责阅读

|位置|职责|
|---|---|
|`configs/problems/`|SystemSpec、固定拓扑、六轴范围|
|`configs/agent/`、`configs/providers/`|策略预算及 API 配置，无凭据值|
|`pll_allocation/pipeline.py`|唯一正式 CLI 和调度入口|
|`pll_allocation/agent/`|观察、Policy、决策校验、候选账本、Handoff、反馈|
|`pll_allocation/allocation/`|原物理反解、确定性分配与基线|
|`pll_allocation/exploration/`|问题合同、必要条件、物理区域、敏感度|
|`pll_allocation/region_explorer/`|Sobol/SLSQP 工具、边界、缓存、M1 预算|
|`pll_allocation/physics_mapping/`|正式 M1 评价和物理映射|
|`pll_allocation/verification/`|原生行为 TB、测量、M2 判决、连续候选适配|
|`pll_allocation/studies/`|可选冻结对照编排，不参与默认分配链|
|`tests/`|数值、合同、预算、反馈、兼容回归|

建议阅读顺序：`agent/initial_allocation.py` → `physics_tool_policy.py` → `search_loop.py` → `exploration/physics_region_builder.py` → `allocation/physics.py` → `agent/feedback.py`。

配置已按 problems / agent / providers / examples / model / verification / baselines / provenance 组织；详见 [configs 说明](configs/README.md)。共享物理工具、复现入口及五个维护工具的职责和命令见 [tools 说明](tools/README.md)。

## 结果和测试

- 初始分配：`m1_allocation.json`、`candidate_archive.jsonl`、`verification_handoff.json`。
- 决策/工具：`SEARCH_DECISION_TRACE.jsonl`、`REGION_CONSTRUCTION_RESULTS.json`、真实 Observation。
- 联合验证：`verification_result.json`、`m2_verifications.jsonl`、`feedback_summaries.jsonl`、`reallocation_candidates.jsonl`、`cost_summary.json`。
- 真实 LLM：查看调用 metadata 的 `real_network_call`、响应状态及 `cost.LLM_calls`；事件名字本身不是调用证据。

执行 `python -m pytest -q`。原生扩展构建、档案依赖和错误定位见[运行说明](docs/RUNNING.md)。TEST/mocked Policy 仅用于回归，不能计作研究成果。

2026-11-17 多策略源码交付复核：干净源码副本中新建 venv、重建四个后端，八组公开输入均重新执行；完整回归786通过、10项历史档案跳过，架构和原算法哈希审计通过。中文路径的 Windows 环境应启用上文 UTF-8 设置；详细边界和定向复验见运行说明。

2026-11-16 配置/工具整理后的共享版验收：精简源码快照中重建四个原生后端，750 项测试通过、10 项历史档案测试跳过。真实确定性分配得到 M1 可行候选；M2 BW≈229.00kHz，但条件捕获54µs超过40µs，因此如实报告 FAIL。重构前后候选与指标相同。本轮没有新增真实 LLM 研究调用，详见[整理说明](docs/RELEASE_NOTES.md)。

本次后续职责命名迁移完成21项文件迁移，完整回归763通过、10项历史档案跳过；三个扩展后端12组旧/新DLL输出逐字节一致，正式M1/M2指标与判决保持。新增命名规则检查及兼容测试，详见[命名说明](docs/NAMING.md)与[实际验收](docs/RUNNING.md)。

共享源码不含 GUI、实验输出、波形、DLL、原始 API 日志或凭据。保留少量必要测试夹具和来源哈希合同。Git 历史未重写；可用 `git clone --depth 1` 或下载最新版源码避免获取完整历史。

- [架构与调用链](docs/ARCHITECTURE.md)
- [全部维护代码的逐文件说明](docs/CODE_MAP.md)
- [运行、配置、测试](docs/RUNNING.md)
- [审查重点和研究边界](docs/REVIEW_GUIDE.md)
- [名称迁移和兼容合同](docs/COMPATIBILITY.md)
- [职责命名规则与完整迁移表](docs/NAMING.md)
- [本次整理说明](docs/RELEASE_NOTES.md)

当前研究目标、实现状态、验收和下一步见 [PROJECT_CHARTER.md](PROJECT_CHARTER.md)。原始任务全文已在本地历史目录留档；研究目标不等于已经完成的认证。
