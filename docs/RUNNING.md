# 运行、配置、测试与错误定位

所有命令从仓库根目录执行。推荐 Python 3.12，安装 `python -m pip install -e ".[integration,test]"`。当前原生 TB 验证环境是 Windows x64/MSVC 2022，不声称其他平台已经验收。

## 配置

|位置|用途|
|---|---|
|`configs/problems/nominal.json`|原连续域例题：BW150–300kHz、名义PM≥50°、条件Lock≤40µs，另有显式未支持 jitter|
|`configs/problems/tight.json`、`infeasible_pm.json`|紧约束例题、必要条件无解例题|
|`configs/agent/deterministic.json`、`llm_physics.json`|确定性/真实 LLM 物理工具策略和预算|
|`configs/agent/region_planning.json`、`region_search.json`|可选区域规划与搜索配置|
|`configs/providers/messages.json`|环境变量名称、认证、token/timeout，无凭据值|
|`configs/verification/verify_only.json`|一次真实 M2，零 LLM 反馈预算|
|`configs/verification/feedback.json`|有限 M1/M2/LLM 反馈重分配|
|`configs/provenance/`|来源哈希合同，不是实验结果|

六轴 SI 单位：A、Ohm、F、F、Hz、Hz/V。每轴包含 min/max/default/unit/scale；要求有限正数、min<max、default 在域内。Spec 明确 enabled、界限与评价来源。当前反解需要正 BW 目标。合法输入不保证存在解。

新配置复制原合同的数值和版本标识；职责重命名不改变默认问题含义。M1 支持项通过不能填补 Lock 或 jitter 的未知。

## 分配与验证

完整命令见根 README。推荐参数为 `--problem --allocator-config` 和 `--handoff --verification-problem --verification-config`，都由同一 pipeline 调度。

Handoff 只有 `gate_status=READY` 才放行。必须保留它引用的校准 context 和证据；源码/模型变更后的运行不能直接混用旧绑定。

编译理想 TB：

```powershell
cmd /c pll_allocation\verification\build_kernel.cmd
```

编译脚本当前定位 VS 2022 Community 标准路径，PATH 中的 python 应为所用虚拟环境。已有构建目录拒绝覆盖；缺 DLL、身份不符会明确失败，不生成模拟替代。

全套可选扩展回归还需要以下原生构建；脚本的旧名称属于保留的来源兼容层：

```powershell
cmd /c pll_allocation\verification\build_closed_loop.cmd
cmd /c pll_allocation\verification\build_return_ratio.cmd
cmd /c pll_allocation\verification\build_stage6c.cmd
python -m pytest -q
```

只研究标准初始分配与 M2 时，理想内核即可。完整测试前应完成四个构建；无编译器环境不能声称真实 M2 验收通过。

## LLM

本地进程环境需要 ANTHROPIC_BASE_URL、ANTHROPIC_AUTH_TOKEN、ANTHROPIC_MODEL；使用 README 的 `--llm-config`。当前 transport 是 Messages-compatible HTTPS，不保证任意 OpenAI-compatible endpoint 直接适用。

`real_network_call=true` 表示真实请求发起，还需查看响应状态才知道是否收到有效决策。Provider 错误、非法 JSON、超域、预算用尽均保留；不能将 TEST 或旧事件标签当作实际 API 证据。

兼容结果中仍可能出现 `STOPPED_BY_LLM`、`LLM_attempts`、`REAL_M2_REAL_LLM` 等历史标签；确定性 Policy 复用同一循环，一次零 LLM 的 M2 验证也会使用旧 mode。判断实际来源应同时检查 `strategy`、`cost.LLM_calls` 和调用 metadata，不能仅凭这些标签认定调用了模型。新的配置/CLI 名称不改变这些旧序列化合同。

## 测试边界

共享套件不要求历史实验档案。完全依赖档案的旧测试不随共享版发布；少量混合测试对缺失档案的历史部分显式 skip，独立不变量仍执行。跳过数必须与报告一起披露，不能补造历史结果。

固定小型测量夹具用于判决回归，不是新仿真。TEST Policy 和故障注入不是实际 LLM。需要冻结实验输入的可选 studies 适配器不保证在无档案源码包中直接执行。

主要测试：test_initial_allocation.py、test_llm_planning.py、test_region_executor.py、test_agent_handoff.py、test_verification_feedback.py、test_pipeline.py、test_m1.py 及 verification/。

## 状态解释

|状态|解释|
|---|---|
|M1 可行|只证明支持的连续 M1 指标；不等于 M2 通过|
|M2 支持子集 PASS / 完整 UNKNOWN|BW/条件Lock通过，启用的 PM/jitter 等没有完整 M2 认证|
|FAIL|已判定硬约束违反，不能用 M1 PASS 覆盖|
|UNKNOWN|未支持/未测/数值不收敛/区间跨界，不能擅改 PASS/FAIL|
|PROVEN_M1_INFEASIBLE|当前模型和用户域内有必要条件证书|
|预算用尽 / 未找到|有限搜索结论，不是数学全局无解|
|LLM_PROVIDER_FAILED|检查 metadata、transport 和服务配置，不等于物理不可行|

M2 的 Lock 限初态0.15V、160µs窗口；PM 未认证。联合通过的结论必须标清 M1/M2 来源和条件。不要覆盖旧输出，不提交凭据、DLL 或实验结果。

## 本次实际验收（2026-11-16）

在仅含共享文件的普通源码快照中运行，无历史 experiments、GUI 或预编译 DLL。四个构建脚本全部成功；随后 `python -m pytest -q`：**754 passed, 10 skipped，253.20秒**。时间为本机验收耗时，不是策略性能排名。

10 项跳过分别为历史 Agent 观察5项、历史 Handoff 1项、旧数值扫描1项、旧联合 M2 记录2项、旧随机试验1项。档案不存在时显式说明原因，其余独立合同、数值、预算、真实原生验证和 TEST 故障注入测试均执行。

不发布的旧测试模块：test_matlab_trajectories、test_scenarios_stage5、test_joint_verification、test_multi_region_planning、test_spec_allocation_ablation、test_window_contract_fix，因其依赖旧实验脚本或大型档案；test_gui 因共享版不含 GUI 而不发布。本地 GUI 另实跑20项兼容测试，全通过。

真实 CLI 使用 README 中的中性参数，分别执行确定性初始分配与 verify_only：初始分配92次正式 M1，后续1次独立 M1，1次完整 M2 / 106次原生运行 / 95,040,845积分点。LLM_calls=0。

|项目|真实结果|
|---|---|
|M1 BW / 名义 PM|225.00kHz / 81.9307°，受支持项可行|
|M2 BW|229.0049kHz，区间228.9117–229.0288kHz，PASS|
|M2 条件捕获|54µs，区间53–55µs，超过40µs，FAIL|
|M2 PM / jitter|UNKNOWN|
|最终完整认证|未签发，M2 FAIL|

旧 `--initial-allocation-problem --initial-allocation-config` 另实跑 infeasible_pm 例题，返回 PROVEN_M1_INFEASIBLE，零 M1/M2/LLM 调用。新旧参数的调度等价性也纳入共享测试。
