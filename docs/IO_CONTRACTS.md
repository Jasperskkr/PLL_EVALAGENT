# 输入、输出与下游交接

## 用户输入入口

在仓库根目录运行：

```powershell
python -m pll_allocation pipeline --problem configs/problems/nominal.json --allocator-config configs/agent/spec_allocation.json --out experiments/my_allocation_01
```

`--problem` 是硬规格和设计域入口，采用 `pll-research-problem-2.0`：`specs` 定义指标、单位、启用状态、界限和评价来源；`parameters` 定义六个变量 `Icp/Rz/C1/C2/f0/Kvco` 的范围、默认值与坐标尺度；`fixed_parameters.N.value` 指定本次正整数分频比。标准主线目标频率为 `N × f_ref`，N 在一次运行中固定。改变 N 后，默认参数和范围仍须满足合法调谐条件。

`--allocator-config` 是策略和执行资源入口，采用 `pll-spec-allocation-1.0`：`mode` 选择策略，`target_count` 是 M1 候选池目标，`m2_target_count` 是原生联合通过候选目标，`m1_budget/m2_budget/llm_budget` 是硬预算。规格界限应写在 problem 中。省略 allocator 使用上述公开配置；仅提供 `--out` 使用 nominal 示例。结果目录必须全新。

输入 JSON 拒绝重复键、非有限数和合同不允许的字段。实际读取路径见 `execution_route.json`；解析后的完整问题和配置分别保存在 `problem_resolved.json`、`allocation_config.json`，索引见 `run_manifest.json` 的 `inputs/artifacts`。

源码执行与安装包共用 `verification.resources.CONFIGS` 定位配置：优先仓库配置，安装后读取当前 Python 环境的 `share/pll-allocation/configs`。Agent 的公式说明和来源摘要也使用该位置，无需复制配置到 site-packages。

## 输出读取顺序

|用途|文件与明确字段|含义|
|---|---|---|
|总索引|`run_manifest.json`|当前运行输入、权威输出、SHA256、交接消费者和交付数量|
|本次分配结果|`allocation_result.json`|状态、成本、候选统计、推荐依据与失败原因|
|全部候选|`candidates.json`|六轴带 SI 单位的参数、M1 证据及实际执行的 M2 结果|
|仅 M1 推荐|`allocation_result.json.recommended`|可能回退到 M1 可行点；须检查 `recommendation_basis`|
|已验证推荐|`allocation_result.json.recommended_M2_supported`|原生 M2 支持指标通过的推荐；没有则为 null|
|正式下游集合|`sizing_handoff.json.candidates`|质量、差异和原生 M2 支持指标门禁均满足的候选；空列表表示没有交付点|
|调用成本|`cost_summary.json`|实际 M1/M2/LLM 等调用及硬预算|
|可读结果|`allocation_report.md`|推荐依据、候选和验证范围|

`joint_status=PARTIAL` 表示已有交付点但未达到数量目标；以 `candidate_count`、`joint_target_reached` 为准。M1 PASS、进程退出成功或优化器收敛均不能替代原生 M2 验证。完整 SystemSpec、M2 PM/jitter、晶体管和 PVT 认证仍不由标准主链保证；未支持或未测保持 UNKNOWN。

## M1 → M2：候选交接

新文件 `initial/verification_handoff.json` 使用 `pll-m1-verification-handoff-2.0`。只有 `ready_for_verification=true`、`gate_status=READY`、`gate_reasons=[]` 同时成立，且原问题、模型、参数、独立正式 M1 复核、摘要和来源证据绑定全部通过，才能送入 M2。它的 `M2_status=NOT_EVALUATED`，不等于下游已验证交付。

继续验证使用职责名入口：

```powershell
python -m pll_allocation pipeline --handoff experiments/my_allocation_01/initial/verification_handoff.json --verification-problem configs/problems/nominal.json --verification-config configs/verification/verify_only.json --out experiments/my_verification_01
```

消费者为 `agent.feedback.load_handoff`。需保留完整来源目录；单独复制 JSON 不足以接续。相对 context 优先且绑定原摘要，缺失或损坏不得回退旧绝对路径。独立验证输出 `verification_result.json`、`verification_config.json`、`verification_problem_resolved.json`、`verification_run_events.jsonl`、`cost_summary.json`、`feedback_report.md`。

反馈配置使用 `pll-verification-feedback-2.0`，结果使用 `pll-verification-result-2.0`。标准连续域 M2 使用 `pll-continuous-m2-1.2` 适配器与 `integer_n_metrics_2.0` 协议；测量阈值保留，频率计划绑定本次 N 和 N×f_ref，冻结定义以 SHA256 引用。

## 已验证候选 → VCO 开发

`delivery.validate_sizing_handoff` 是生产端和下游共用的门禁。它核对集合摘要、候选、M1、原生 M2 观测、协议、频率计划和判决。下游读取 `sizing_handoff.json.candidates`；不能以 M1 交接中的 READY 或通用 `recommended` 替代。

VCO 导出可以显式选择 M1 交接或正式集合，来源状态会随 guidance 保留：

```powershell
python -m pll_allocation.vco_sizing export --handoff experiments/my_allocation_01/sizing_handoff.json --out experiments/my_vco_guidance_01.json
```

guidance 的偏好值不自动成为硬规格。实测反馈须绑定来源、证据、测量条件和用户约束；回填 `f0/Kvco` 后仍需独立问题身份与正式 M1/M2 再验证，详见 [VCO 开发合同](VCO_SIZING_CONTRACT.md)。

## 历史记录读取

旧 M1 交接、旧反馈配置、旧 M2 协议和旧 Python/CLI 别名继续可读。按声明的 schema 选字段，拒绝混合新旧就绪字段；旧摘要、证据 ID、来源路径和模型身份不改写。旧配置可在内存中解析为当前配置；签名证据保留记录形式。

继续执行旧交接时，应提供产生它的原始问题配置。新示例的职责名 `problem_id` 是新问题身份，不能替换旧交接中绑定的问题 ID。

`validate_handoff(..., require_current_model=False)` 和 `validate_sizing_handoff(..., require_current_model=False)` 仅用于历史记录检查，保留参数、指标、协议与判决校验，并明确不证明该历史模型就是当前安装模型。默认验证和所有接续执行仍要求当前 M1 模型；历史 VCO guidance 只表示已记录的来源状态。

新运行停止生成阶段名兼容文件副本。旧消费者应改读此文列出的职责名文件。已有历史数据、冻结验证扩展的模型/协议身份及 provenance 收据保留原始名称，具体边界见 [兼容说明](COMPATIBILITY.md)。`M1/M2`、`v1/v2` 和表示相位阶跃的 `phase_step` 保留。
