# 本轮执行与检查记录

日期：2026-11-06，Asia/Shanghai。工作目录：`F:\LJP\概伦AI\PLL_allocation`。

## 范围与完成状态

- 已完成：项目与参考工作流图对应审计；Block Space来源、构建、范围与公式适用域审查；Verifier来源、事件积分、实验、测量与判决审查；三条反馈路径的实际接通状态审查。
- 已完成：48份关键来源快照、5份上游MATLAB公式源SHA校验、原Python事件函数来源与快照校验、编译内核身份检查，以及一份历史Baseline的结果合同绑定复核。
- 已完成：85项针对性既有测试，全部通过。
- 部分完成属于项目现有能力：独立BW测量及确定性设计修复。完整PM与严格频率认证未完成；模型更新和验证复测反馈尚未自动闭环。
- 待验收：用户审阅本轮审计结论与收敛顺序。报告中的建议没有实施为新的模型、规格、协议或策略版本。

## 实际执行命令

只读证据与合同快照：

```powershell
python docs/workflow_model_verifier_audit_20261106_01/capture_snapshot.py
```

该脚本仅能创建新的`snapshot_01`；目录存在时拒绝重跑覆盖。读取历史结果并调用当前`check_result`，没有重新执行历史TB。

针对性回归，实际执行命令如下：

```powershell
python -m pytest -q tests/test_physics_mapping_stage1.py tests/verification/test_verification.py tests/verification/test_measurements.py::test_complex_response_fit_recovers_known_gain_phase_independent_of_M1 tests/verification/test_measurements.py::test_PM_inversion_prototype_never_claims_independent_measurement tests/verification/test_measurements.py::test_simulation_measurement_modules_do_not_use_M1_transfers tests/test_block_space_v1.py::test_calibration_record_separates_protocols_and_does_not_correct -p no:cacheprovider --basetemp=docs/workflow_model_verifier_audit_20261106_01/test_tmp_01 --junitxml=docs/workflow_model_verifier_audit_20261106_01/tests_01.xml
```

结果：`85 passed in 1.38s`。保留JUnit XML及测试临时产物。测试包括M1数值/合同、人工已知波形的测量单测、非法Proposal拒绝与受支持状态检查。5次非法Proposal验证入口调用均在运行内核前拒绝，不能计为完整TB。

最终保护检查：

```powershell
python docs/workflow_model_verifier_audit_20261106_01/finalize_audit.py
```

脚本核对审计开始时全部tracked文件的SHA及缺失状态、48份关键来源、上游公式与事件参考、编译内核身份、测试XML；仅在本审计目录新建`PROTECTION.json`及`DELIVERY_MANIFEST.json`。详见实际输出。

## 本轮真实调用与成本边界

|操作|本轮新增次数|说明|
|---|---:|---|
|完整M2评价|0|只读历史Baseline/Stage5证据。|
|native事件仿真|0|测量单测使用人工波形；非法输入在内核前拒绝。|
|外部LLM调用|0|不以历史调用或回放冒充新调用。|
|MATLAB运行|0|仅校验原公式源文件，未启动MATLAB。|
|M1函数求值|未逐调用统计|既有单测内执行，不推算或伪造次数。|

历史Baseline中的106次native属于原实验，未计入本轮新调用。Stage5历史完整评价同样不重计。本轮回归不是全域行为验证或全系统新认证。

## 文件保护

本轮只新增`docs/workflow_model_verifier_audit_20261106_01/`内的文件。既有源码、冻结输入、历史运行、`docs/PROJECT_STATUS.md`及`docs/DECISIONS.md`均不修改；开始时已有的工作树差异与删除状态保留。最终检查以`PROTECTION.json`为准。
