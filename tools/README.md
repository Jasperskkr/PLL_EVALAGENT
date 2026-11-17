# 分配工具与维护工具

正式运行入口是 `python -m pll_allocation pipeline`。物理工具是现有 Python 函数/类，不需要 MCP 或 Tool Registry。三种策略共享下列实现；Policy 提议动作，Runner 校验、计费并执行，验证器判决。

默认是新版三模式分配，`--problem` 可选当前问题，allocator 省略时使用 `agent/spec_allocation.json`；只给 `--out` 执行 nominal 示例。旧冻结链须显式 `--legacy-frozen`。复现工具继续显式传入每个案例的配置；启动及 `execution_route.json` 记录实际路由，混用参数直接拒绝。旧 v1 `run/suite` 必须加 `--legacy-v1`，不与新版 Agent 能力等同。

## 可复用分配能力

|能力|源码入口|输入与输出/边界|
|---|---|---|
|物理反解|`allocation/physics.py:inverse_at_shape`、`exploration/physics_region_builder.py:build_physics_region`|当前问题、形状/BW/调谐目标 → 六参数种子和合法局部域；使用原公式|
|Cold Start 与初始候选|`agent/initial_allocation.py:run_initial_allocation`|问题、策略配置 → 原候选账本、正式 M1、独立复核和 Handoff；多候选配置使用 V2 Cold Start|
|确定性搜索/优化|`region_explorer/explorer.py:RegionExplorer.execute`|经过校验的决策 → Sobol/SLSQP 等原工具结果、缓存和正式 M1 成本|
|正式 M1|`physics_mapping/model.py:M1Evaluator.evaluate`|带单位六参数 → 连续模型 BW、名义 PM、调谐点；问题判决由 `exploration/contracts.py:judge` 完成|
|候选池|`agent/candidate_pool.py:distinct_candidates` / `select_m2`|真实账本、质量门槛和六轴归一化距离 → 不同 M1 点、优先 M2 点；不删除原始失败/近重复证据|
|正式 M2|`verification/continuous.py:verification_request` / `execute_request` / `judge_measurements`|通过绑定检查的候选 → 原生 TB 结果与原判决；PM/jitter 未支持时仍 UNKNOWN|
|反馈与重分配|`agent/feedback.py:run_feedback`、`agent/deterministic_feedback.py:DeterministicFeedbackPolicy`|M1/M2 证据与剩余预算 → 池内换点或 V2 确定性修正后重新分配；每个新点继续正式验证|
|真实 LLM 工具选择|`agent/physics_tool_policy.py:make_policy`、`agent/region_policy.py:LLMRegionPolicy`、`agent/pool_search.py:PoolLLMPolicy`|物理先验、当前 Spec、历史验证/失败、剩余预算 → 工具动作；六参数由工具生成，API 有授权门禁与硬预算|
|三模式编排|`agent/spec_allocation.py:run_spec_allocation`|`pll-spec-allocation-1.0` 配置 → 候选、推荐依据、真实 M1/M2/LLM 成本；由正式 Pipeline 调用|

模式、配置字段和产物合同见 [Spec Allocation](../docs/SPEC_ALLOCATION.md)。不要用直接调用底层评价器绕开候选写盘、绑定检查或正式预算。

## 复现输入与命令

先按 [运行说明](../docs/RUNNING.md)安装依赖、编译原生后端。以下封装只生成配置并调用正式 CLI，不含另一套求解/验证逻辑，不读取旧实验目录。

```powershell
python tools/run_allocation_examples.py --list
python tools/run_allocation_examples.py --case nominal_m1 --case tight_m1 --out experiments/my_m1_01
python tools/run_allocation_examples.py --case nominal --case tight --case feedback --case auto --out experiments/my_native_01
```

真实 API 需要自己的 Messages-compatible 服务和进程环境 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_MODEL`。明确授权本次付费调用后使用：

```powershell
python tools/run_allocation_examples.py --case llm --case auto_trigger --allow-paid-llm --out experiments/my_llm_01
```

|case|输入/预算特点|
|---|---|
|`nominal_m1` / `tight_m1`|确定性 K=5，M2=0|
|`nominal` / `tight`|确定性 K=5，M2≤3|
|`feedback`|nominal K=1，M2≤2，最多一次反馈重分配|
|`auto`|Auto K=5，M2≤3，真实 LLM 授权关闭；足够时不进入 LLM|
|`llm`|LLM K=5，真实 API≤4，M2≤3；需显式授权|
|`auto_trigger`|Auto K=10，一轮确定性后可进入 LLM，真实 API≤2，M2=0；需显式授权|

输入在 `configs/examples/spec_allocation.json`，继承 `configs/agent/spec_allocation.json` 的总 M1≤96 等默认值。`--allow-paid-llm` 仅作用于所选 `llm`/`auto_trigger`；默认 `auto` 仍不授权。脚本预检授权及变量是否存在，不打印变量值。输出目录必须全新，分别保存生成配置、CLI 命令、stdout/stderr、各 case 完整结果及真实 `summary.json`。非零退出码和缺失结果会如实报告；得到报告并不代表通过 M2。

LLM 响应受模型与服务版本影响，模板复现输入、预算和验证流程，不保证与历史候选逐字一致。没有 API 时运行确定性和离线接口回归即可，不将其记为真实 LLM 验收。

## 其他维护命令

下列五个工具服务于现有源码、模型关系和可选内核。

|工具|具体工作|产物/使用时机|
|---|---|---|
|`audit_architecture.py`|检查正式模块依赖方向；核对六份原分配实现的来源 SHA256|只读审计 JSON；整理代码后检查|
|`build_block_relation_atlas.py`|用原反解和正式 M1 整理冻结模型变量关系、条件域及局部示例，并做独立 KCL 数值核对|JSON/CSV/HTML 关系图谱和计费；帮助理解现有模型，不是新的 Allocation Solver，也不执行 M2/LLM|
|`create_verification_profiles.py`|生成预声明的噪声、非理想环境和协议模板|17份 JSON 及 manifest；只写全新目录，不覆盖活动配置|
|`generate_phase_step_kernel.py`|从理想内核生成相位阶跃观测/激励扩展|`phase_step_kernel.cpp`；维护生成源码时使用|
|`generate_nonideal_noise_kernel.py`|从同一理想内核生成可选噪声/非理想扩展|`nonideal_noise_kernel.cpp`；维护生成源码时使用|

从仓库根目录运行，例如：

```powershell
python tools/audit_architecture.py --out experiments/my_audit_01.json
python tools/build_block_relation_atlas.py --out experiments/my_atlas_01
python tools/create_verification_profiles.py --out experiments/my_profiles_01
```

输出路径必须全新；审计文件的父目录须先存在。两个内核生成器直接运行也拒绝覆盖现有 `.cpp`。仓库已包含生成源码，正常编译/分配无需再次生成；不要为执行生成器删除冻结源码。非理想构建入口为 `pll_allocation/verification/build_nonideal.cmd`。

移除了70个旧阶段审计、固定实验运行、汇报绘图、打包和一次性迁移脚本。它们服务于旧研究过程，正式 Pipeline 不依赖它们。可复用的计算窗口适配器已迁入 `pll_allocation/agent/computational_window.py`，仍采用原 Policy/Runner 和真实 API；旧批量压力实验编排已删除。历史实验不随源码发布，本地历史保留。
