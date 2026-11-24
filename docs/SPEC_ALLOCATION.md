# 多策略多候选 Spec Allocation

这是现有正式 Pipeline 的配置与候选池扩展，使用相同 Physics Inverse、RegionExplorer、M1 和原生 M2。没有重写物理公式、判决或反馈控制器，原有单点配置继续可用。

此路径现为 CLI 默认主线；只指定 `--problem --out` 即使用新版默认配置，只给 `--out` 则使用 nominal 示例。冻结兼容链须显式 `--legacy-frozen`。新版预算只由 allocator JSON 管理，混入旧策略/预算参数会在运行前报错。启动路由和最终 `execution_route.json` 可用于确认实际执行路径，迁移说明见 [COMPATIBILITY](COMPATIBILITY.md)。

## 模式

|`mode`|行为|
|---|---|
|`DETERMINISTIC`|V2 Cold Start、物理反解构造不同点，必要时原 Sobol/SLSQP；M2 失败后先换池内点，再确定性反馈重分配；零 LLM|
|`LLM_PHYSICS_GUIDED`|LLM 读取物理先验、当前问题和已有验证，选择共享物理/搜索工具；不能直接替代求解器或验证器|
|`AUTO_HYBRID`|先确定性搜索；数量/质量不足后可引入 LLM；M2 反馈也先确定性处理，后续重分配可启用 LLM|

`allow_paid_llm=false` 是默认硬门禁。配置为 LLM/Auto 不等于已授权 API。没有授权或预算时保留已找到的点、真实停止原因和错误，不能伪造成功。原始 LLM 请求、响应和 metadata 仅保存在本地运行目录。

## 配置

正式入口：

```powershell
python -m pll_allocation pipeline --problem configs/problems/nominal.json --allocator-config configs/agent/spec_allocation.json --out experiments/my_pool_01
```

|字段|默认值|含义|
|---|---:|---|
|`schema_version`|`pll-spec-allocation-1.0`|由正式 Pipeline 识别|
|`target_count`|5|目标质量合格且互异的 M1 点数 K|
|`m2_target_count`|3（公开默认配置）|交付目标：互异、质量合格的正式 M1 + 原生 M2 已支持指标通过点数；历史配置省略此项仍为 1|
|`m1_budget` / `m2_budget`|96 / 8（公开默认配置）|跨阶段总调用上限，含 M1 独立复核及 M2 posthoc；失败执行同样计费|
|`initial_search_m1_budget`|32|初始搜索上限，并为后续验证预留总预算|
|`minimum_margin`|0|最小归一化 M1 裕量要求|
|`minimum_distance`|0.05|按用户域的 log/linear 六轴归一化欧氏距离去重|
|`deterministic_rounds`|3|Auto 首次引入 LLM 前的确定性决策轮数|
|`llm_budget` / `allow_paid_llm`|4 / false|真实 API 硬预算与显式授权开关|
|`max_reallocations`|2|验证控制器的重分配上限|
|`m2_timeout_s`|180|原生 M2 超时|
|`seed`|23|确定性采样随机种子|

可选高级字段：`max_decisions=8`、`max_round_m1=24`、`construction_attempt_budget=128`、`max_build_attempts=16`，限制搜索/构造，不能扩大硬 M1/M2/LLM 总预算。参数校验见 `agent/spec_allocation.py:validate_config`。

达到 `target_count` 暂停初始 M1 搜索。M2 首个通过后继续选点，直到达到 `m2_target_count` 或预算/搜索上限耗尽。先验证池内其他质量合格且不同的点，再按需重新搜索；补点每次寻找一个新的未测候选，最多 `max_reallocations` 次，失败修复与成功后的补点共享此上限。

仅在 M1 裕量达标、原生 M2 已支持指标 PASS 且六轴距离达标时计入交付数量。先筛出通过子集再去重，防止更高 M1 排名但未通过 M2 的邻点遮蔽交付点。选下一个 M2 点时先剔除已测点和已通过点的近邻，再筛质量与差异，原始证据不删除。

成功后池耗尽会反馈 `REPLENISH_JOINT_POOL` 和已通过点，探索其他不同候选，不把成功冒充失败。Auto 成功补点本身不触发“确定性修复失败”升级；初始轮次超限或已有失败修复历史仍按原规则开放 LLM。LLM 读取当前交付目标、已通过点数、成功/失败证据和预算。所有新点继续正式 M1/原生 M2。

预算允许小于目标，耗尽时正常保存部分结果，不能降质量或声称全域无解。`m2_budget=0` 只做 M1，`joint_status=DISABLED`。公开默认配置是 M1 池 5、交付目标 3、M2 预算 8；手写历史配置省略 `m2_target_count` 时保留首个通过停止，未显式设置的 `m2_budget` 仍按接口兼容默认值 3。

## 输出与判决

|文件|内容|
|---|---|
|`allocation_result.json`|模式、池数量、K 是否达到、真实状态、推荐依据、失败与成本|
|`candidates.json`|不同六参数点，单位、正式 M1 指标/裕量/来源、已运行 M2 完整观察|
|`sizing_handoff.json`|只含真实原生联合通过子集、当前 SystemSpec/域、单位、模型与协议证据；不含仅 M1 点或 TEST 通过点|
|`cost_summary.json`|M1/M2/LLM 实际调用、原生运行/积分点、耗时和硬预算|
|`allocation_report.md`|可读摘要及推荐参数|
|`initial/`、`verification/`|原候选账本、完整提案/失败、复核、Handoff、M2 请求/观察、反馈与重新分配历史|

六参数为 `Icp[A]`、`Rz[Ohm]`、`C1[F]`、`C2[F]`、`f0[Hz]`、`Kvco[Hz/V]`。每次候选先完整写盘再执行评价，验证证据绑定具体候选、问题、模型和协议。

- `M1_feasibility=FEASIBLE` 只证明正式 M1 支持指标。
- `M2_supported_status=PASS` 指已支持指标通过；必须同时读取 `M2_evidence_scope` 区分 NATIVE 与 TEST。失败、UNKNOWN、NOT_EVALUATED 分别保留。
- `recommended_M2_supported` 仅在真实原生 M2 已支持项通过且满足质量门槛时非空。TEST 注入结果不进入这个推荐。
- `recommended` 可回退到 M1 点，必须结合 `recommendation_basis` 读取，不是 M2 认证。
- `joint_candidates` 与 `sizing_handoff.json.candidates` 是正式交付集合；`M2_supported_pass_count` 是其中互异点数。`joint_target_reached` 独立于 M1 的 `pool_target_reached`。
- `joint_status` 为 `TARGET_REACHED` / `PARTIAL` / `NOT_REACHED` / `DISABLED` / `TEST_ONLY`。多点运行顶层状态为 `M2_JOINT_TARGET_REACHED` 或 `M2_JOINT_PARTIAL`；部分找到不会冒充目标完成。旧目标 1 的状态保留。
- `time_to_first_joint_s` / `time_to_joint_target_s` 为从分配开始到首个/目标联合点数的实际时间；未达目标为 null。TEST 结果不填充正式交付时间。
- 标准 M2 仅支持 BW 与指定初态下条件捕获，PM/jitter 仍 UNKNOWN，`FULL_SYSTEMSPEC_CERTIFIED=false`。

Sizing handoff 交付的是行为目标，不认证晶体管/PVT 可实现性，也不提供未经扰动验证的独立参数容差。每个点保留 M1 指标/裕量/来源和完整 M2 观察，允许下游追溯相同候选、问题、模型及测量条件。

反馈由原 `agent/feedback.py:run_feedback` 执行。确定性策略提取 V2 已有 BW 偏差修正和 LOW_VOLTAGE 探索；LLM 使用原物理工具 Policy。`run_spec_allocation(..., feedback=...)` 保留外部反馈输入的扩展位置，不接入下游 Sizing，也不能导入外部 PASS。

## 从源码复现

安装、原生编译、输入案例及命令见 [RUNNING](RUNNING.md) 和 [tools README](../tools/README.md)。新增 `tight_llm` / `tight_auto`、`joint_partial`（预算不足）和 `joint_replenish`（小池反馈与补点）案例。模板只包含输入，不含成功六参数或历史结果。确定性 nominal/tight 快速找点、M2 池内换点、确定性反馈、真实 LLM 与 Auto 切换都可重新执行；真实 API 需要自己的配置与显式授权，结果可能随服务版本变化。

离线接口回归在 `tests/test_spec_allocation.py`，明确区分 TEST Policy/M2 与真实运行。共享源码不依赖历史实验目录；档案专属检查缺失时显式跳过。真实LLM在M2失败后读取反馈、调用共享工具和重新验证的路径已实跑，但未证明有速度、成功率或修复收益优势。

## 当前已知限制

- M2选点排除已测参数的相同哈希和已通过点的近邻；它不保证与所有FAIL/UNKNOWN已测点都保持 `minimum_distance`。实测出现局部优化数值微变体重复消耗M2预算的问题，尚未修复。交付集合的质量/距离筛选仍独立执行。
- LLM的简短理由不是执行效果保证；实测出现声称调整电容比但请求/种子没有落实，以及跨模型BW补偿方向或尺度不合理的情况。以实际工具请求、六参数和正式验证为准，不能由文本补签PASS。
- 真实LLM预算门禁耗尽可能保留宽泛的 `LLM_PROVIDER_FAILED` 标签；需读取 `failure.reason` 区分 `REAL_LLM_CALL_BUDGET_EXHAUSTED` 与真实网络故障。必要条件已给出不可行证书时，顶层也可能仍是普通预算内未找到状态，应同时查看初始终止原因和 `physics_screening.json`。上述状态分类尚未细化。
- 独立KCL回代支持同一理想模型的计算一致性，不证明动态捕获、物理准确性或搜索完备性。M1连续小信号与原生M2采样测量定义不同，不能将跨模型BW差异直接解释为同定义下数值误差。
- 下游仅消费 `sizing_handoff.json.candidates` 中的完整参数组合及证据；零点或部分交付是正常结果。当前未认证模块器件可实现性、管级/PVT，也未提供经验证的参数容差区域或自动Sizing反馈闭环。

手工Spec与六轴范围设置见 [配置输入说明](../configs/README.md#手工输入-systemspec-和六变量范围)。不应修改冻结 `model/block_space.json` 来配置当前问题。

## 可选条件噪声与启动排序（2026-11-20）

原 `pll-spec-allocation-1.0` allocator 合同新增四个可选布尔字段，省略全部为 false；原问题、默认配置、三种模式及 Auto 切换规则保持。`PhysicsRegionRequest 1.0` 不增加任何字段。共享工具配置经 Runner 校验后作为 builder 的独立参数传入。

|开关|作用|
|---|---|
|`analytic_features_enabled`|记录自然频率、近似阻尼、精确三阶线性极点、初始频偏、调谐裕量及启发式滑脱风险|
|`noise_allocation_enabled`|复用原噪声估算器筛选形状/电容/增益分解；候选池停止要求满足配置中的条件 jitter；原 RegionExplorer SLSQP 增加归一化 jitter 裕量|
|`initial_state_aware_enabled`|在与 f0 范围相交的安全电压区间内构造 `clip(0.15+delta)`，同时保留中点、低电容、低电流、Noise-Favorable 等偏好候选|
|`physics_ranking_enabled`|首次交接与后续 M2 均调用 `candidate_pool.select_m2`；只提议优先级，独立复核及正式验证不变|

独立示例：`configs/agent/noise_aware.json` 和 `configs/agent/physics_enhanced.json`，均 K=5、M1上限96、M2上限3、联合支持项目标3，无真实 API 授权。

```powershell
python -m pll_allocation pipeline --problem configs/problems/nominal.json --allocator-config configs/agent/noise_aware.json --out experiments/my_noise_01
python -m pll_allocation pipeline --problem configs/problems/tight.json --allocator-config configs/agent/physics_enhanced.json --out experiments/my_enhanced_01
python tools/run_physics_comparison.py --out experiments/my_physics_comparison_01
```

可选 `physics_options` 对象包含：`delta_offsets_V=[0.03,0.10]`、`safe_rail_margin_V=0.02`、`noise_band_Hz=[10000,1000000]`、`noise_points=2049`、`noise_trial_points=257`、`noise_profile`（可选 profile JSON 路径或完整对象）。默认 profile 为 `configs/verification/profiles/noise_all.json`。正式结果绑定解析后的 profile SHA、频带及积分网格；不修改来源配置。jitter 上限只读取当前问题已启用的 `jitter_s.max`，没有启用上限则标 `NO_ENABLED_LIMIT`。

预测沿用 Hz/V 的 Kvco、单边 rad²/Hz、独立源方差求和、原时间抖动换算与 log 梯形积分。薄封装按源调用 `optimizer_noise_estimate`，避免为了附加显示字段暗中调用正式 M1 扫描；与 `noise_mapping` 数值一致。构造用257点廉价估计，正式候选附2049点条件估计并重新判断阈值。额外工作分别记录 `conditional_prediction_calls`、`conditional_noise_trial_integrations`，不冒充正式 M1 或 M2 调用。候选的正式 M1 仍全部由 RegionExplorer 先写盘再计费执行。

线性闭环特征多项式为 `Rz*C1*C2*s³+(C1+C2)*s²+(Icp*Kvco/N)*Rz*C2*s+Icp*Kvco/N`。Kpd 的 `1/(2π)` 与 Kvco 到 rad/s/V 的 `2π` 抵消。阻尼为近似二阶描述，极点是当前理想线性模型的三阶根。滑脱风险仅按 `|df_initial|/(N*omega_n/(2π))` 分档：≤0.1 LOW、≤1 MEDIUM、其余 HIGH；超出适用域为 UNKNOWN，不据此淘汰或签发捕获不可行证书。没有已验证的捕获估计、初始相位和锁定容限，`predicted_lock_time_s` 保持 null。

新排序先沿用正式 M1、`minimum_margin`、参数哈希去重、`minimum_distance` 及通过点距离门槛，再作词典序比较，避免权重抵消硬条件：

1. 条件噪声：达标0 / 未知0.5 / 超标1；再比较正缺口 `gap/(limit+gap)`。
2. LOW/MEDIUM/HIGH风险0/0.5/1；初始输出频偏除以目标频率并截到[0,1]。
3. 调谐裕量除以半轨宽（越大优先）；有可靠预测时锁定时间除以配置上限。
4. 正式 M1 最差裕量映射为 `m/(1+|m|)`（越大优先）。
5. 原六轴归一化的 Icp、C1/C2坐标均值、到已测点的最小距离/√6（越远优先）；最后参数 SHA 稳定打破平局。

缺失动力学项取中性0.5；全无适用预测时按原已测距离/M1排序回退。归一化向量、理由、profile、jitter、风险、轨裕量和 fallback 标志写入 `physics_selection`、handoff 的 `selection_evidence` 及验证事件。候选不会因缺失动力学预测被直接移除。

构造在相同预算内枚举 LF shape、电容与增益拆分，再在最佳 M1/条件噪声可行层中选择实现偏好；没有满足条件噪声的点时保留最佳预测值和缺口，继续预算内搜索，不放宽规格。`conditional_noise_summary` 报告全部正式质量合格点中的最佳点、差距和停止原因；条件池计数先筛条件再按原距离去重。解析不足仍保留原 Sobol/SLSQP/RegionExplorer 路径。

`conditional_noise_status` 和 `joint_conditional_feasibility` 仅为研究 profile 下的条件预测。原 `joint_candidates` / `joint_status` 继续表示正式 M1 + 原生 M2 **已支持项**；它们不能证明10ps达标。标准 M2 PM/jitter 仍 UNKNOWN，`FULL_SYSTEMSPEC_CERTIFIED=false`。一次两问题对照不构成统计优越性证明。

## LLM 主动选择条件物理目标

启用上述开关后，原 Planner State 可选增加 `conditional_physics`；全部关闭时不增加该字段，原 Prompt 完全保持。LLM、Auto 和确定性仍使用同一 Runner；Auto 的切换规则没有改变。本轮只用离线 Mock 验证接口及真实 M1 执行，没有发起付费 LLM 调用。

`BUILD_PHYSICS_REGION` 可选使用 `pll-physics-region-request-1.1`。保留 1.0 的全部字段，只增加以下两个字段；其余动作及 1.0 请求继续接受：

```json
{
  "schema_version": "pll-physics-region-request-1.1",
  "physical_objectives": ["FAST_LOCK", "NOISE_AWARE"],
  "tool_options_sha256": "COPY_conditional_physics.tool_options_sha256"
}
```

上例仅展示需要替换/增加的字段，实际请求还必须包含原有 problem/model、strategy、target_bw_fraction、physics_focus、tuning_preference、seed_count、region_width_policy、budget、request_id 与 evidence_ids。配置仍使用 `pll-spec-allocation-1.0`，无需额外配置字段。

|合法目标|可见条件|执行含义|
|---|---|---|
|`NOISE_AWARE`|`noise_allocation_enabled=true`|优先原条件噪声前沿|
|`INITIAL_STATE_AWARE`|`initial_state_aware_enabled=true`|优先调谐点接近既定初始控制电压0.15V|
|`FAST_LOCK`|`initial_state_aware_enabled=true`|优先较小绝对初始输出频偏；仅为启发式|

目标列表非空、无重复并有序，在既有 M1/条件噪声可行层内依次分配种子偏好，之后仍保留原多样性偏好；多目标不表示数值加权或保证最优。阈值、noise profile、频带、启动偏移、安全轨裕量及硬预算由配置与 Runner 管理。旧版本加新字段、配置未启用目标、身份过期、参数值或 PASS 等未知字段一律拒绝。工具执行记录包含 `objective_selection` 和实际正式 M1 费用。

紧凑 Observation 最多提供24个互异候选，包含条件 RMS jitter、四源贡献/主导源、jitter 裕量，以及启用时的自然频率、近似阻尼、初始频偏、轨裕量与风险。每条 `CPRED:<sha>` 绑定来源 M1 证据、完整候选 SHA、问题/模型与解析后的工具配置 SHA；noise profile 身份包含积分频带和网格。预测携带适用性、无效原因及独立摘要 SHA，可供动作引用，不能冒充 formal seed、测量或正式 PASS。未知预测保留 UNKNOWN，捕获时间为 null，`capture_certified=false`。

`OPTIMIZE_LOCAL` 继续原 SLSQP，`PROBE_REGION` 直接使用原 Sobol，`MEASURE_LOCAL_SENSITIVITY` 继续原正式 M1 差分。LLM 选择策略、目标、已有区域及预算，不能提交六维求解结果。下游反馈仍走已有带来源证据的 advisory 边界，未来必须经 Runner 重新检查；本轮未定义 Sizing 接口或新增跨层控制器。
