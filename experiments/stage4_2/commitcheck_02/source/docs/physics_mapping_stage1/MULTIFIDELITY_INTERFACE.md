# 多精度接口与接入边界

`pll_allocation.physics_mapping` 是独立命名空间，不导入 v1 contracts、behavioral、runner、policies 或 legacy 模型。核心只依赖标准库；旧入口与旧测试不变。唯一新增可复现实验入口为 `python -m pll_allocation.physics_mapping`。

|层级|本阶段能力|未来接入要求|
|---|---|---|
|M0 解析近似 / 公式反推|`UnavailableEvaluator('M0')` 返回 UNSUPPORTED|真实实现后提供 MetricEvaluator；说明近似前提、适用指标、有效域；不能冒用 M1 测量标签|
|M1 完整锁定点连续频域|`M1Evaluator` 可执行五个 Factor、调谐点、局部增益、Zlf/L/T、UGF/BW/PM|保持 MODEL_ID、参数语义、单位、指标 protocol 及来源；此处“完整”限于支持的理想连续线性模型|
|M2 非线性事件行为 TB|`UnavailableEvaluator('M2')` 返回 UNSUPPORTED|真实执行事件模型，保存候选、TB 条件、原始波形、测量窗和实际成本；独立证明数值收敛；不能直接包装 v1 周期电荷后端并称事件模型|

接口位于 `model.py`：

```python
request = MetricRequest(
    parameters=parameter_envelope,
    metrics=('BW_Hz', 'PM_deg'),
    scan=FrequencyScan(),
    response_frequencies_Hz=(1e4, 1e5, 1e6),
)
result = M1Evaluator().evaluate(request)
```

`parameter_envelope` 包含 schema_version、conventions 和 values。values 每项是 `{value, unit}`，要求列全全部 17 个输入；没有单位推断或非理想项默认归零。使用 `parameters_from_experiment` 可由经过验证的 v2 实验配置生成完整参数。纯 SI 数值和 schema 字典便于未来跨进程实现，不要求依赖同一个 Python 对象实例。

`MetricEvaluator` 是 Protocol，`evaluate(MetricRequest)->MappingResult`。结果包含 model_level、model_id、status、reason、parameter_sha256、metrics、units、protocols、factors、diagnostics、response、scope 和 verified_joint_block_spec=false。复数响应使用 `[real, imag]` JSON 数组，Zlf 单位 Ω，L/T 无量纲。每个 Factor 保存原 MATLAB 公式来源；频域结果绑定输入参数哈希。

`Status` 为 OK / UNSUPPORTED / OUT_OF_DOMAIN / NUMERICAL_FAILURE。OK 不等于规格通过。任何失败清空系统指标、units、protocols 和响应；保留已经完成且有定义的 Factor 供诊断。UNSUPPORTED 表示本阶段没有可信模型；OUT_OF_DOMAIN 表示参数/单位/锁点不适用；NUMERICAL_FAILURE 包括未包围交越点和非有限运算。未知的 metric 请求返回 UNSUPPORTED。

`judge_experiment` 独立核对参数完整性、单位、空间成员、结果哈希、模型层级/ID、指标 protocol 和草案边界，仅产生 M1_SPEC_PASS / M1_SPEC_FAIL / UNKNOWN。任何失败状态不得为 M1_SPEC_PASS。该函数不是 v1 MetricVerifier，也不为完整 TB 签发通过。`output_frequency_Hz` protocol 明确为条件锁定频率，不伪称尾窗实测。

未来可按 metric 路由给不同 evaluator；本阶段配置中每个 metric 有显式 evaluator=M1，因此无需提前建立模型注册框架。路由时必须保留每个指标的模型层级/版本、参数哈希和 protocol，禁止把同名但不同定义的 BW、相位误差或时间窗拼成一个全局 PASS。M1 的静态调谐和频域结果可以做先验，M2 才能回答捕获、限幅、真实事件锁定等问题。

## 数值对照的独立性

主实现沿 MATLAB 的尺度使用 8000 个 log 点，只用于包围交越，再对 log(f) 二分求根。验证实现不调用主传函，改以 `x=ω²` 的幅度方程三次多项式求正根；相位使用 atan(ω/ωz)-atan(ω/ωp)。两者比较属于相同物理方程的独立数值路径，不能证明行为模型或晶体管准确度。

默认点另对照旧 `python_crosscheck_results.json`（原绝对路径、SHA 见 audit）。扰动点的参考来源是本次 `validation.polynomial_reference`，不是不存在的历史 MATLAB 扰动记录。测试还用独立两节点 KCL 逆矩阵核对 Zlf，并检查 Icp×Kvco 不变时环路指标不变、锁定控制电压改变。
