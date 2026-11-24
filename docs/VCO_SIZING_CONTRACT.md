# VCO Sizing Contract（独立附加文件）

基线：`e2d4dfa2d1d68247df11ede477a5d28df693078e`。本功能只消费已完成的正式输出，默认分配路径不导入本包，也不增加 M1/M2 调用。`inverse_at_shape()`、原六变量、原生协议、原始哈希和候选 PASS/FAIL 均保留。

2026-11-24 冻结修订：保持 Guidance/Feedback 的 `schema_version=1.0`，新 Guidance 增加 `contract_revision="1.1"`、`design_policy_sha256` 和每候选 `target_confirmation`。新增字段为附加合同，不修改原始 Handoff。旧1.0默认策略/精确测量数据仍可解析；旧自定义约束必须显式补原策略，非零误差工作点需重新导出并提供测量精度依据。消费者应检查 `target_operating_point_confirmed`，不能只看回报的 `target_reachable=true` 或有无局部参数。

## 导出

先照常运行 `python -m pll_allocation pipeline ...`，再显式执行：

```powershell
python -m pll_allocation.vco_sizing export --handoff experiments/<run>/sizing_handoff.json
# 可选：--out <新文件> --options <用户硬约束与实测 CP 合规区间 JSON>
```

默认在源文件旁创建 `vco_sizing_guidance.json`，拒绝覆盖已有文件。支持多候选 `pll-sizing-targets-1.0`，也支持原带签名 `pll-stage9-nominal-handoff-1.0`；后者只是 M1 交接，导出的 M2 状态仍为 `NOT_EVALUATED`。空多候选交接导出空集合，不从仅 M1/TEST/失败点补造正式联合候选。

多点源验证每个候选的正式 M1、原域、原生 M2 请求/观测/判决绑定。导出无需加载 DLL，不重跑物理。哈希用于检测记录不一致，不提供来源认证，也不替代波形审计。

## Guidance v1 格式

以下是字段节选，`<...>` 为实际源身份；完整样例可通过上面的命令生成：

```json
{
  "schema_version": "pll-vco-sizing-guidance-1.0",
  "contract_revision": "1.1",
  "design_policy_sha256": "<独立原始策略规范化后的canonical摘要；不提供来源认证>",
  "generated_at": "2026-11-23T00:00:00+00:00",
  "generator": "pll_allocation.vco_sizing.contract",
  "source_uri": "<原始 sizing_handoff.json 绝对路径>",
  "source_handoff_sha256": "<原 Handoff 身份>",
  "source_handoff_hash_kind": "CANONICAL_JSON_SHA256",
  "source_file_sha256": "<源文件原始字节 SHA256>",
  "system_spec_identity": {
    "problem_id": "<原 Problem ID>",
    "problem_sha256": "<原 resolved Problem 身份>",
    "system_spec_sha256": "<原 specs 列表身份>",
    "specs": ["<原始完整 resolved specs，含 UNKNOWN/PENDING_M2>"]
  },
  "candidate_count": 2,
  "candidates": [{
    "source_candidate_id": "<原 evidence_id>",
    "source_candidate_sha256": "<原六轴完整 parameters 身份>",
    "source_handoff_sha256": "<上述容器身份>",
    "native_verification_handoff_sha256": "<该点原生 M2 请求中带签名 Handoff 身份>",
    "model_fingerprint": "<原 M1 模型身份>",
    "problem_sha256": "<原 Problem 身份>",
    "target_frequency_hz": 80000000,
    "preferred_vlock_v": 0.4,
    "preferred_kvco_hz_per_v": 20000000,
    "nominal_f0_hz": 72000000,
    "units": {
      "target_frequency_hz": "Hz",
      "preferred_vlock_v": "V",
      "preferred_kvco_hz_per_v": "Hz/V",
      "nominal_f0_hz": "Hz"
    },
    "control_voltage_limits": {
      "min": 0, "max": 1.2, "unit": "V",
      "source": "DECLARED_SYSTEM_MODEL", "physically_verified": false
    },
    "cp_compliance": null,
    "joint_cp_vco_valid_interval_status": "UNCONFIRMED_REQUIRES_MATCHED_PHYSICAL_EVIDENCE",
    "required_tuning_margin": {
      "voltage_v": null, "frequency_hz": null,
      "units": {"voltage_v": "V", "frequency_hz": "Hz"},
      "status": "UNSPECIFIED_REQUIRES_DESIGN_REQUIREMENT"
    },
    "hard_constraints": {},
    "target_confirmation": {"max_frequency_error_hz": null},
    "exact_f0_match_required": false,
    "exact_kvco_match_required": false,
    "FULL_SYSTEMSPEC_CERTIFIED": false
  }, "<第二个候选，结构相同>"],
  "feedback_schema_version": "pll-vco-physical-feedback-1.0"
}
```

每个完整条目还带 `nominal_block_spec`（原参数 envelope）、`cp_lf_parameters`（原 Icp/Rz/C1/C2 及单位）、`hard_requirements`、`preference_fields` 和 `source_evidence_status`。目标由 `N*f_ref` 得到，偏好电压由 `(target-f0)/Kvco` 得到。原 nominal f0/Kvco 保存在原 Handoff 及附加文件的副本中。

源多点 Handoff 本身没有 `handoff_sha256`，因此附加文件对其完整解析 JSON 使用现有 `fingerprint()` 的 canonical SHA256；带签名单点则沿用其原签名字段。文件字节身份单独存储，不能与 canonical 身份混用。每个多点条目额外关联原生 M2 请求的独立带签名 Handoff。

## 硬要求与偏好

必须实测目标频率可达、实际 Vlock 在合法且 CP/VCO 共同有效的范围内、满足调谐余量、可靠起振及驱动 Divider，并在该工作点提取局部 Kvco 后回填正式 M1/M2。nominal 精确匹配只是偏差记录，不能单独构成 MOS 失败或系统通过。

用户独立保存的 `design_policy.json` / options 示例：

```json
{
  "hard_constraints": {
    "kvco_local_hz_per_v": {"min": 15000000, "max": 45000000, "unit": "Hz/V"},
    "vlock_v": {"min": 0.25, "max": 0.85, "unit": "V"}
  },
  "required_tuning_margin": {"voltage_v": 0.05, "frequency_hz": 1000000},
  "target_confirmation": {"max_frequency_error_hz": 4000},
  "cp_compliance": {
    "min": 0.2, "max": 1.0, "unit": "V",
    "source_candidate_sha256": "<本次CP测量适用候选的参数哈希，含Icp身份>",
    "conditions": {"pdk": "<PDK及版本>", "corner": "tt", "temperature_c": 27, "supply_v": 1.2},
    "evidence": [{"uri": "<CP实测结果路径>", "sha256": "<64位十六进制摘要>"}]
  }
}
```

三种可解析硬约束是 `vlock_v`、`kvco_local_hz_per_v`、`f0_local_hz` 的 min/max 区间（允许 min=max 表示精确硬约束）；未知项拒绝，不能静默丢弃用户要求。`exact_*_match_required=false` 不会覆盖显式硬约束。没有数值余量要求时保留 UNKNOWN，不自行编造门槛。声明的 0–1.2 V 是模型限制，不能据此声称 CP 已物理验证；即使提供 CP 测量，仍需匹配 VCO 条件和有效区间。CP测量必须关联其适用候选（包含Icp身份），不会自动应用到其他多点目标；反馈也检查这一绑定。

`validate_guidance(guidance, handoff, options=original_policy)` 只从原 Handoff 和调用方提供的独立原策略重建预期合同，不读取待验 Guidance 的硬约束来生成“预期”值。未提供 options 时仅使用空硬约束、未指定余量和 CP 区间的默认策略；含自定义要求的 Guidance 会拒绝，不能自行降级。export、assess、prepare 必须使用同一份原策略。摘要仅检测一致性；若原策略与 Guidance 都能被同时修改，本模块无法认证其原始用户来源，调用方负责原策略的可信保管。

## 真实物理反馈 v1

`assess_feedback(feedback, guidance, original_handoff, options=original_policy, source_handoff_path=...)` 验证绑定及数据一致性，CLI：

```powershell
python -m pll_allocation.vco_sizing assess --handoff <原交接> --guidance <附加文件> --feedback <反馈JSON> --options <独立原design_policy.json> --out <新评估JSON>
```

反馈必需字段：

| 字段 | 含义 |
|---|---|
| schema_version | `pll-vco-physical-feedback-1.0` |
| source_candidate_id / source_candidate_sha256 / source_handoff_sha256 / problem_sha256 | 对应 Guidance 条目的原始身份 |
| experiment_id | 独立物理实验 ID |
| units | 完整 `contract.UNITS` 映射（包括 Hz、Hz/V、V） |
| target_frequency_hz / frequency_tolerance_hz | 原目标；反馈容差非负且小于目标的1%，仅作回报值，不能自行授权目标根确认 |
| mos_design.netlist | `{uri, sha256}`，真实网表身份 |
| mos_design.sizes_and_biases | 非空尺寸/偏置对象，键中注明单位，例如 w_m、l_m、ibias_a |
| conditions | `{pdk, corner, temperature_c, supply_v}`；PDK 包括版本 |
| tuning_samples | 按电压升序的 `{vctrl_v, frequency_hz}` 数组，至少两点，覆盖声明的 VCO 有效区间 |
| vco_valid_control_voltage | `{min,max,unit:"V"}`，该工况下经下游测量声明的 VCO 有效区间 |
| cp_compliance | 可空，格式同 options；非空时工况必须与 VCO 完全一致 |
| target_reachable | true/false/null；不能只凭插值声称实测达到目标 |
| vlock_v / kvco_local_hz_per_v / f0_local_hz | 实际测量锚点及局部参数；不可达/无工作点时为 null |
| target_point_measurement | 非零残差确认需 `{frequency_uncertainty_hz, method, evidence:[{uri,sha256}]}`；证据必须关联反馈 evidence 列表 |
| kvco_extraction_voltages_v | 有效 VCO 区间内最近的两个实测邻点，严格包围 Vlock；v1 校验两点中心割线斜率与回报 Kvco 的相对误差不超过 1e-6，输出实际提取窗口及有限差分近似声明 |
| startup_status / divider_drive_status | `PASS` / `FAIL` / `UNKNOWN`，由下游测量负责 |
| measurement_method / evidence | 非空方法说明及 `{uri,sha256}` 证据列表 |
| validation_status / failure_reasons | `MEASURED` / `FAILED` / `INCOMPLETE`；FAILED 必须给出原因 |

测量锚点电压必须对应真实采样点。局部模型始终以 **`f0_local_hz = f_measured - kvco_local_hz_per_v*v_measured`** 构造，不用目标频率平移曲线。局部增益仍以最近相邻实测点的割线校验；它是有限差分近似，并非完整非线性曲线或真正无穷小导数。

确认目标工作点须 `validation_status=MEASURED` 且频率残差不超过回报容差。无精度元数据的旧数据，仅接受4 ULP的数值舍入误差，状态 `target_root.status=LEGACY_EXACT_SAMPLE`。真实非零误差不要求浮点精确相等，但须同时有：原策略的 `max_frequency_error_hz`、带关联证据的 `target_point_measurement`、`abs(residual)<=frequency_uncertainty_hz`，且 `abs(residual)+frequency_uncertainty_hz<=max_frequency_error_hz`。通过后为 `MEASURED_WITHIN_TRUSTED_ACCURACY`，仍保留实际频率、残差和实测截距。该限制只控制目标确认，不自动添加 nominal Kvco/f0 硬约束。

例如80 MHz目标、80.4 MHz实测、0.5 V、35 MHz/V时，截距为62.9 MHz。即使反馈声明500 kHz容差，没有独立策略和可信精度依据仍为 `APPROXIMATE_MEASURED_POINT`，不得标为 `MEASURED_TARGET_REACHED`。79.9987 MHz、0.47214 V、22.365 MHz/V在原策略允许4000 Hz、测量不确定度1500 Hz、回报容差2000 Hz时可确认；局部模型保留实测79.9987 MHz，不改写为精确80 MHz。

输出新增 `frequency_residual_hz`、`measured_anchor_frequency_hz`、`frequency_measurement_basis`、`target_operating_point_confirmed` 和 `target_root`。合法采样区间包围目标时，可给出 `INTERPOLATED_NOT_REMEASURED` 电压估计及原始包围点；多重根不擅自挑选唯一根。插值不产生测量证据，不开放正式回填。`actual_local_parameters` 在近似情况下仅供诊断，必须结合确认标志使用。目标位于扫描频率范围外且下游明确回报不可达时，返回 `FREQUENCY_UNREACHABLE_IN_REPORTED_SCAN`；不足以定位时为 UNKNOWN/UNCONFIRMED，不外推整个物理域不可行。

CP证据分别保留在 `cp_evidence_sources`，包括 Guidance 已绑定证据和 Feedback 新证据。两者必须匹配同一候选/Icp身份及VCO的PDK、corner、温度、电源；不可比较的证据明确报错，普通反馈不支持隐式替换。可比较时只取交集，再与声明rails和实测VCO区间相交。上游0.3–0.6 V不会被下游0.1–1.1 V扩大；空交集为 `NO_COMMON_INTERVAL`、CP工作点FAIL，无任何CP证据则为 `UNCONFIRMED`/UNKNOWN。文件摘要不认证CP或VCO测量真实性。

若不起振或扫描中止，没有有效频率数据，可以回报 `validation_status=FAILED/INCOMPLETE`、`tuning_samples=[]`，并将 VCO有效区间、可达性及工作点参数设为 null。此时返回 `UNKNOWN_NO_VALID_TUNING_MEASUREMENTS`，保留实际失败原因；不把没有数据误判成频率不可达或 M2 FAIL。

`f0_local_hz` 是上述实测锚点局部切线截距，**不等于实测零控制电压频率**。完整原参数误差保存在 `nominal_parameter_errors`。偏差本身不改变 `physical_status`；明确违反物理/用户硬要求才返回 `REQUIREMENTS_FAILED`，证据或目标确认不足为 `UNKNOWN`，要求齐备则为 `READY_FOR_SYSTEM_REVALIDATION`。所有评估的 M1/M2 均为 `NOT_EVALUATED`，没有最终 MOS PASS 或 SystemSpec PASS。

assess/prepare CLI总是读取 `--handoff` 原始字节并对比 `source_file_sha256`；只改空白而canonical JSON不变也拒绝，缺少摘要亦拒绝。Python只传解析JSON时不声称检查原字节，评估内 `guidance_validation.source_file_bytes_status=NOT_CHECKED_PARSED_JSON_ONLY`；传 `source_handoff_path` 成功后为 `VERIFIED`。`validate_guidance(..., return_report=True)` 可直接取得同一报告，默认返回原 Guidance 以兼容旧调用。`source_handoff_sha256`/候选指纹是canonical身份，与源文件字节SHA256分别校验。`authentication_status=NOT_AUTHENTICATED` 始终保留。

## 合法回填转换

Python 接口 `prepare_revalidation(feedback, guidance, handoff, problem=<新的原始ResearchProblemV2>, options=original_policy, source_handoff_path=...)`：

1. 校验独立策略/来源/物理反馈，固定原 Icp/Rz/C1/C2，以实测锚点局部 Kvco/f0_local 构造完整参数。未确认目标工作点返回 `TARGET_OPERATING_POINT_UNCONFIRMED`，`parameters=null`，不能作为正式输入。
2. 要求独立 problem_id，保留原 resolved SystemSpec、固定参数和拓扑；不改原身份或状态。
3. 分别报告 `OUTSIDE_ORIGINAL_SEARCH_DOMAIN` 与新 Problem 的正式域筛查。新域不接受时返回 `REVALIDATION_DOMAIN_REJECTED`，不偷偷扩大范围，也不用 `check_bounds=False` 绕过模型。
4. 返回可交给原评价器的参数/新 Problem 及来源身份；`READY_FOR_FORMAL_REVALIDATION` 不是 M1/M2 PASS。负频率、非法线性代理等仍由原模型拒绝。

若已知物理要求或显式 Block 硬约束失败，转换返回 `PHYSICAL_REQUIREMENTS_FAILED` 且不输出可用参数；UNKNOWN 仍可准备分析输入，其物理评估保持 UNKNOWN。

只有目标工作点已确认时，其他证据（例如CP）UNKNOWN才可准备数学分析输入；其 `physical_assessment` 始终保留UNKNOWN，`READY_FOR_FORMAL_REVALIDATION` 仅表示通过原模型的域筛查，不意味着CP/VCO联合合规或SystemSpec通过。本模块自动回填只覆盖 **f0、Kvco**，保留原始Icp/Rz/C1/C2。历史Stage 6对实际CP电流的测量及等效Icp由独立工具处理；本模块未实现Icp自动回填，也不支持完整六变量物理测量。

该接口不运行下游 ngspice、不自动回写系统验证。原生 M2 使用全电压线性 VCO；将真实非线性曲线的局部切线回填时，结果仍只是该代理模型的行为证据，不能声称整条真实曲线的瞬态已经验证。

也可使用 CLI `prepare --handoff <原交接> --guidance <附加文件> --feedback <反馈JSON> --problem <新的原始Problem> --options <独立原design_policy.json> --out <新转换JSON>`。无自定义要求可省略options。新域需要由调用方显式声明。

## P1：可选离散可接受点分析

```powershell
python -m pll_allocation.vco_sizing region --handoff <原交接> --candidate-sha256 <参数哈希> --experiment-id vco_region_01 --out experiments/<新目录> --kvco-values 20000000 30000000 40000000 --vlock-values 0.3 0.5 0.7 --sample-budget 9 --m1-budget 9
```

Python 接口 `analyze_vco_acceptance_region(candidate, problem=resolved_problem, out=..., experiment_id=...)`。固定 CP/LF，逐点使用 `f0=target-Kvco*Vlock`，经原 `make_parameters`、原 Runner 筛查和正式 M1。不会自动扩域；可显式传 `--revalidation-problem <新原始Problem>`，必须保留原 SystemSpec/固定拓扑并使用独立问题 ID。

默认 `m2_budget=0`。显式 `--m2-budget 1` 才调用原 Handoff 独立审计及原 `verification_request/execute_request`；最多4次，每次有 `--m2-timeout-s`（默认180秒），M1总预算必须预留每次审计和 posthoc 的两次机会。采样和M1预算各最多256；请求网格最多4096点，超预算点逐个标记未执行。代表点是离散可行列表的首尾及剩余点，不称作真实可行域边界。

输出 `vco_acceptance_region.json` 分列 `M1_feasible_points`、`M1_failed_points`、`M1_unknown_points`、`domain_rejected_points`、`M2_passed_points`、`M2_failed_points`、`M2_unknown_points`、`unverified_points`，每点附约束裕量及真实证据，保留全局预算/模型/原Spec身份。M2的 PASS 仅指原生已支持项；PM/jitter等仍 UNKNOWN。全部未采样位置明确未认证，不连接稀疏 M2 点形成 PASS 区域，搜索轴也不是模型有效域证明。

## 验证与隔离

```powershell
python -m pytest tests/test_vco_sizing_contract.py tests/test_vco_acceptance_region.py -q
```

新测试包含真实多点原生 M2 导出、离散点 M2 调用、超时预算计费和 UNKNOWN 分级；没有构建标准 DLL 时明确跳过原生部分。其余合同/反馈测试使用真实 M1 与显式 TEST 物理数据。默认流程关闭兼容性还用同一基线参数哈希与独立 baseline 运行对照；原 Handoff 导出前后逐字节比较。

候选 `A8S...` 只在单次运行内编号。Golden Case 必须同时绑定参数哈希和问题/模型/协议；不能用另一场实验的同名编号制造相同数值的断言。当前稳定基线的测试配置实际 A8S0000005（参数哈希 `0f7d5eb93e1d7d38b92dafe7521d49445d7d9a4775e49cd58a74f919d654e0fa`）为 BW≈225 kHz、PM≈77.24°、原生 M2 捕获≈35 μs，已有数值断言。对原工作区及紧凑审计包的候选记录检索未找到用户所举 BW≈202.46 kHz、PM≈76.88° 的同身份实例，因此该精确 Golden 尚不能复现，也不能据此断定它依赖未合并代码；未复制任何实验实现。
