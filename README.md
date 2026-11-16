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

从仓库根目录运行。已验证环境为 Windows x64、Python 3.12、MSVC 2022 Community C++17，不依赖原作者的磁盘路径。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[integration,test]"
python -m pll_allocation pipeline --help
```

**确定性分配和 M1：**

```powershell
python -m pll_allocation pipeline --problem configs/problems/nominal.json --allocator-config configs/agent/deterministic.json --out experiments/my_allocation_01
```

**真实 LLM 分配：**先在本机设置 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_MODEL`。名称沿用现有环境合同，实际服务须支持 Messages-compatible HTTPS 请求。

```powershell
python -m pll_allocation pipeline --problem configs/problems/nominal.json --allocator-config configs/agent/llm_physics.json --llm-config configs/providers/messages.json --out experiments/my_agent_01
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

配置已按 problems / agent / providers / model / verification / baselines / provenance 组织；详见 [configs 说明](configs/README.md)。维护目录只保留五个工具，职责和命令见 [tools 说明](tools/README.md)。

## 结果和测试

- 初始分配：`m1_allocation.json`、`candidate_archive.jsonl`、`verification_handoff.json`。
- 决策/工具：`SEARCH_DECISION_TRACE.jsonl`、`REGION_CONSTRUCTION_RESULTS.json`、真实 Observation。
- 联合验证：`verification_result.json`、`m2_verifications.jsonl`、`feedback_summaries.jsonl`、`reallocation_candidates.jsonl`、`cost_summary.json`。
- 真实 LLM：查看调用 metadata 的 `real_network_call`、响应状态及 `cost.LLM_calls`；事件名字本身不是调用证据。

执行 `python -m pytest -q`。原生扩展构建、档案依赖和错误定位见[运行说明](docs/RUNNING.md)。TEST/mocked Policy 仅用于回归，不能计作研究成果。

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
