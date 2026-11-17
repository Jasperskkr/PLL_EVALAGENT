# 多策略多候选 Spec Allocation

这是现有正式 Pipeline 的配置与候选池扩展，使用相同 Physics Inverse、RegionExplorer、M1 和原生 M2。没有重写物理公式、判决或反馈控制器，原有单点配置继续可用。

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
|`m1_budget` / `m2_budget`|96 / 3|跨阶段总调用上限，含 M1 独立复核及 M2 posthoc；失败执行同样计费|
|`initial_search_m1_budget`|32|初始搜索上限，并为后续验证预留总预算|
|`minimum_margin`|0|最小归一化 M1 裕量要求|
|`minimum_distance`|0.05|按用户域的 log/linear 六轴归一化欧氏距离去重|
|`deterministic_rounds`|3|Auto 首次引入 LLM 前的确定性决策轮数|
|`llm_budget` / `allow_paid_llm`|4 / false|真实 API 硬预算与显式授权开关|
|`max_reallocations`|2|验证控制器的重分配上限|
|`m2_timeout_s`|180|原生 M2 超时|
|`seed`|23|确定性采样随机种子|

可选高级字段：`max_decisions=8`、`max_round_m1=24`、`construction_attempt_budget=128`、`max_build_attempts=16`，限制搜索/构造，不能扩大硬 M1/M2/LLM 总预算。参数校验见 `agent/spec_allocation.py:validate_config`。

达到 K 结束 M1 搜索，仍可对池内高质量且不同的点执行预算内 M2。候选不足时继续所选策略，预算耗尽正常报告部分结果。质量门槛不能因找到一个 M1 点而跳过；有限搜索失败不等于数学上无解。`m2_budget=0` 只做 M1，M2 状态为未执行。

## 输出与判决

|文件|内容|
|---|---|
|`allocation_result.json`|模式、池数量、K 是否达到、真实状态、推荐依据、失败与成本|
|`candidates.json`|不同六参数点，单位、正式 M1 指标/裕量/来源、已运行 M2 完整观察|
|`cost_summary.json`|M1/M2/LLM 实际调用、原生运行/积分点、耗时和硬预算|
|`allocation_report.md`|可读摘要及推荐参数|
|`initial/`、`verification/`|原候选账本、完整提案/失败、复核、Handoff、M2 请求/观察、反馈与重新分配历史|

六参数为 `Icp[A]`、`Rz[Ohm]`、`C1[F]`、`C2[F]`、`f0[Hz]`、`Kvco[Hz/V]`。每次候选先完整写盘再执行评价，验证证据绑定具体候选、问题、模型和协议。

- `M1_feasibility=FEASIBLE` 只证明正式 M1 支持指标。
- `M2_supported_status=PASS` 指已支持指标通过；必须同时读取 `M2_evidence_scope` 区分 NATIVE 与 TEST。失败、UNKNOWN、NOT_EVALUATED 分别保留。
- `recommended_M2_supported` 仅在真实原生 M2 已支持项通过且满足质量门槛时非空。TEST 注入结果不进入这个推荐。
- `recommended` 可回退到 M1 点，必须结合 `recommendation_basis` 读取，不是 M2 认证。
- 标准 M2 仅支持 BW 与指定初态下条件捕获，PM/jitter 仍 UNKNOWN，`FULL_SYSTEMSPEC_CERTIFIED=false`。

反馈由原 `agent/feedback.py:run_feedback` 执行。确定性策略提取 V2 已有 BW 偏差修正和 LOW_VOLTAGE 探索；LLM 使用原物理工具 Policy。`run_spec_allocation(..., feedback=...)` 保留外部反馈输入的扩展位置，不接入下游 Sizing，也不能导入外部 PASS。

## 从源码复现

安装、原生编译、八个输入案例及命令见 [RUNNING](RUNNING.md) 和 [tools README](../tools/README.md)。模板只包含输入，不含成功六参数或历史结果。确定性 nominal/tight 快速找点、M2 池内换点、确定性反馈、真实 LLM 与 Auto 切换都可重新执行；真实 API 需要自己的配置与显式授权，结果可能随服务版本变化。

离线接口回归在 `tests/test_spec_allocation.py`，明确区分 TEST Policy/M2 与真实运行。共享源码不依赖历史实验目录；档案专属检查缺失时显式跳过。当前未证明 LLM 比确定性方法更快或更可靠，也未验证真实 LLM 在 M2 失败后的重新分配收益。
