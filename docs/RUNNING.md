# 运行、配置、测试与错误定位

2026-11-18 多点交付：公开默认配置先构造5个 M1 候选，目标交付3个质量及差异达标的 M1＋原生 M2 已支持指标通过点，M2总预算8；读取 `sizing_handoff.json` 和 `joint_status`，部分找到会标为 `PARTIAL`。旧配置省略 `m2_target_count` 时仍以首个通过停止，PM/jitter UNKNOWN 不变。详见 [Spec Allocation](SPEC_ALLOCATION.md)。

所有命令从仓库根目录执行。推荐 Python 3.12，安装 `python -m pip install -e ".[integration,test]"`。当前原生 TB 验证环境是 Windows x64/MSVC 2022，不声称其他平台已经验收。

默认入口现为新版连续域、多候选分配：`pipeline --problem <problem.json> --out <fresh>` 可省略 allocator 配置；只给 `--out` 使用 nominal 示例并记录输入路径。旧冻结命令须增加 `--legacy-frozen`；更早的 `run/suite` 须在子命令前加 `--legacy-v1`。不同路径参数混用会在读输入前拒绝，不能在新版命令使用旧 `--strategy` / `--m2-budget` 作为覆盖。每次 CLI 输出 `execution_route.json`，迁移表见 [COMPATIBILITY](COMPATIBILITY.md)。

入口收口后独立源码复核：273份源码运行前后哈希不变，四个后端重建成功，完整回归 **813 passed / 10 archive skipped / 0 warnings**（启用 UTF-8、`-W error`）。默认新版、仅 tight 问题、feedback、Auto 均找到原生 M2 支持指标通过点；显式冻结仍可运行，原单点仅 M1 且正确记录零 LLM/零 TEST 调用。四组新版的候选六参数、M1 指标/判决及推荐 M2 数值与上轮逐项一致。本轮未调用真实 API，LLM 选择接口使用离线回归；未升级 PM/jitter 的 UNKNOWN。

2026-11-18 多点交付验收：两组 spec × 三种模式均交付3个原生联合通过点；两组 Auto 均零 API。真实 LLM 共5次 HTTP200，尚无策略优越性结论。预算不足实际1/3、修复后小池反馈与补点实际2/2。最终完整回归 **826 passed / 10 archive skipped / 0 warnings**（203.44秒，UTF-8、`-W error`），架构及六份原物理实现哈希审计通过。原始失败、修复重跑、API 和波形仅保存在本地实验目录。

## 新克隆源码的多策略复现

共享源码包含求解/验证实现、输入配置、原生 C++ 源码和构建脚本，不包含历史实验、DLL 或 API 凭据。无需取回旧实验目录。

```powershell
git clone --depth 1 https://github.com/Jasperskkr/PLL_EVALAGENT.git
cd PLL_EVALAGENT
$env:PYTHONUTF8 = "1"
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[integration,test]"
python tools/run_allocation_examples.py --case nominal_m1 --case tight_m1 --out experiments/my_m1_01
cmd /c pll_allocation\verification\build_kernel.cmd
python tools/run_allocation_examples.py --case nominal --case tight --case feedback --case auto --out experiments/my_native_01
```

M1 案例无需编译；原生 M2 需要 Windows x64 与 VS 2022 Community C++ 工具链。构建脚本目前使用标准安装路径，其他安装位置需要调整本机构建环境，不是已经验证的平台。构建目录和实验输出目录必须全新。

`configs/agent/spec_allocation.json` 选择三种模式、K、总预算和质量门槛，见 [配置与结果合同](SPEC_ALLOCATION.md)。复现案例清单在 `configs/examples/spec_allocation.json`，`tools/run_allocation_examples.py` 只准备配置并调用 `python -m pll_allocation pipeline`；每个 case 保存自己的完整输出，根 `summary.json` 汇总真实调用及结果。

真实 LLM 的两组输入可在自己的 Messages-compatible 服务和授权下重跑。先在本机进程环境设置 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_MODEL`，不要写入仓库：

```powershell
python tools/run_allocation_examples.py --case llm --case auto_trigger --allow-paid-llm --out experiments/my_llm_01
```

`llm` 为 nominal M1池5、联合目标3、API≤4、M2≤8；`tight_llm` / `tight_auto` 提供相同预算的 tight 输入。`auto_trigger` 为 nominal K10、一轮确定性后可引入 LLM、API≤2、M2=0。`auto` 默认不授权 API，用于验证足够候选时零 LLM。显式授权开关仅影响所选的真实 LLM 案例，缺少授权或环境时脚本在运行前退出。模型响应及候选可能变化；复现的是输入、工具、预算和验证过程，不保证随机服务输出相同，也不保证有限预算必达目标。M2 未执行必须报告为未执行。

边界验收用公开案例 `joint_partial`（联合目标3，M2预算3）和 `joint_replenish`（初始池1，联合目标2，M2预算6，反馈搜索上限4）：

```powershell
python tools/run_allocation_examples.py --case joint_partial --case joint_replenish --out experiments/my_joint_boundaries_01
python tools/run_allocation_examples.py --case tight_llm --case tight_auto --allow-paid-llm --out experiments/my_joint_tight_01
```

完成以下三个可选后端构建后，运行完整共享回归：

```powershell
cmd /c pll_allocation\verification\build_phase_step.cmd
cmd /c pll_allocation\verification\build_return_ratio.cmd
cmd /c pll_allocation\verification\build_nonideal.cmd
python -m pytest -q
python tools/audit_architecture.py --out experiments/my_architecture_01.json
```

离线策略/故障注入回归不会发起付费 API，明确标注 TEST，不能替代真实 LLM/M2 证据。真实 API、波形、失败历史和审计包只存本地；推送输入模板不等于推送实验结果。

2026-11-17 源码交付复核：从 Git 暂存内容单独导出272份文件，在全新 venv 中安装依赖并从源码重建四个后端，八个公开案例均完成；完整回归 **786 passed / 10 archive skipped**，架构与六份原算法哈希审计通过，272份源码运行前后未变。环境为 Windows x64、Python 3.12.10、MSVC 2022、NumPy 2.5.5、SciPy 1.18.1、pytest 9.2.0。初轮回归有一条 GBK 子进程解码警告；使用上文 `PYTHONUTF8=1` 后，该项以 `-W error` 单独复验通过，`pip freeze` 同样成功。真实 LLM 响应与原实验存在变化，因此不承诺旧候选或耗时完全相同；原始产物继续留在本地。

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

完整配置分类与可修改项见 [configs 说明](../configs/README.md)；保留工具见 [tools 说明](../tools/README.md)。

## 分配与验证

完整命令见根 README。推荐参数为 `--problem --allocator-config` 和 `--handoff --verification-problem --verification-config`，都由同一 pipeline 调度。

Handoff 只有 `gate_status=READY` 才放行。必须保留它引用的校准 context 和证据；源码/模型变更后的运行不能直接混用旧绑定。

编译理想 TB：

```powershell
cmd /c pll_allocation\verification\build_kernel.cmd
```

编译脚本当前定位 VS 2022 Community 标准路径，PATH 中的 python 应为所用虚拟环境。已有构建目录拒绝覆盖；缺 DLL、身份不符会明确失败，不生成模拟替代。

全套可选扩展回归还需要以下原生构建：

```powershell
cmd /c pll_allocation\verification\build_phase_step.cmd
cmd /c pll_allocation\verification\build_return_ratio.cmd
cmd /c pll_allocation\verification\build_nonideal.cmd
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

在仅含共享文件的普通源码快照中运行，无历史 experiments、GUI 或预编译 DLL。四个构建脚本全部成功；配置/工具清理后执行 `python -m pytest -q`：**750 passed, 10 skipped，203.82秒**。时间为本机验收耗时，不是策略性能排名。比上一共享版删除7项已移除驱动的专属测试，新增3项活动配置迁移/安装目录/profile防覆盖测试。

10 项跳过分别为历史 Agent 观察5项、历史 Handoff 1项、旧数值扫描1项、旧联合 M2 记录2项、旧计算窗口记录1项。档案不存在时显式说明原因，其余独立合同、数值、预算、真实原生验证和 TEST 故障注入测试均执行。

不发布的旧测试模块：test_matlab_trajectories、test_scenarios_stage5、test_joint_verification、test_multi_region_planning、test_spec_allocation_ablation、test_window_contract_fix，因其依赖旧实验脚本或大型档案；test_gui 因共享版不含 GUI 而不发布。本地 GUI 另实跑20项兼容测试，全通过。

真实 CLI 使用 README 中的中性参数，分别执行确定性初始分配与 verify_only：初始分配92次正式 M1，后续1次独立 M1，1次完整 M2 / 106次原生运行 / 95,040,845积分点。LLM_calls=0。与上一个共享版逐项比较，六参数、M1指标、M2数值及判决完全相同；真实证据路径存在。

|项目|真实结果|
|---|---|
|M1 BW / 名义 PM|225.00kHz / 81.9307°，受支持项可行|
|M2 BW|229.0049kHz，区间228.9117–229.0288kHz，PASS|
|M2 条件捕获|54µs，区间53–55µs，超过40µs，FAIL|
|M2 PM / jitter|UNKNOWN|
|最终完整认证|未签发，M2 FAIL|

旧 `--initial-allocation-problem --initial-allocation-config` 另实跑 infeasible_pm 例题，返回 PROVEN_M1_INFEASIBLE，零 M1/M2/LLM 调用。新旧参数的调度等价性也纳入共享测试。

另外实际执行架构审计，六份原分配实现 SHA 均保持；物理关系图谱生成通过独立数值核对（12次正式M1，零M2/LLM）。两个内核生成器与四份 C++ 源码字节不变，计算窗口适配器迁移前后 AST 相同。配置迁移收据与活动 profile 身份均经回归核对。


## 职责命名迁移验收（2026-11-16）

后续命名迁移在本机全新职责目录构建三个扩展后端，生成器与生成源码一致、身份检查通过。完整维护套件 **763 passed / 10 archive skipped，169.53秒**。之后补充命名反例检查并扩展审计覆盖到tools/tests，相关 **38项**接口/架构/config回归通过；最终命名审计调整后架构 **11项**再验通过。这些检查存在重叠，不相加为全套测试总数。

本轮完整测试首轮进程曾在修复前导入Planner变量改名冲突，出现80项失败；修复后新进程重跑全部通过。旧失败日志保留，没有将其隐藏或当作成功。

旧、新DLL做12组直接ABI比较（三个后端、两种步长、两种激励或噪声设置），有效轨迹、边沿、事件与汇总均逐字节相同。两个迁移生成器与新C++源一致；六份原分配实现、理想kernel、profile合同实现、17份profile和6份移动JSON夹具保持原字节。扩展C++仅首行职责注释改变，物理更新与ABI保持。

修复后再次执行正式nominal确定性M1→verify_only M2，与迁移前六参数、M1 metrics/judgment、M2 metrics/constraints/status逐项精确一致；11项绑定检查通过。M1 BW225kHz、PM81.93069884°；M2 BW229004.90846Hz通过，条件捕获54µs失败，PM/jitter UNKNOWN，未签发完整SystemSpec认证。M2耗时9.6022秒，新增1次M1、1次完整M2、106次原生执行、0次LLM。

实际本地证据位于 `experiments/naming_refactor_20261116_01/`：`pytest_02.xml`、`pytest_02.log`、`verifier_pipeline_comparison_02.json`、`verifier_dll_abi_comparison_01.json`、`numerical_source_preservation.json`。实验输出继续被Git忽略；源码附有迁移收据，见 [NAMING](NAMING.md)。
