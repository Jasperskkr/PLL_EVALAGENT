# Stage 6A delivery index

本阶段研究执行完成，待用户/技术Leader审阅；不自动进入后续阶段。全部成果在独立研究worktree，master保持不变。

|交付|权威位置|
|---|---|
|原始任务|TASK_REQUEST.md（原文逐字节复制）|
|A 主线安全与修改范围|MAINLINE_SAFETY_REPORT.md；experiments/stage6a/safety_01|
|B 指标能力矩阵|SPEC_CAPABILITY_MATRIX.md；analysis_02/registry_binding_checks.json、reuse_manifest.json|
|C 六参数耦合与可行域|MULTISPEC_FEASIBILITY_ANALYSIS.md；analysis_02/*.csv / sensitivities.json / summary.json|
|实验前顺序/安全方案|EXECUTION_PLAN.md|
|正式实验冻结计划与候选|experiments/stage6a/frozen_01/experiment_plan.json及7份proposal|
|D 完整结果|E0_E1_E2_RESULTS.md；summary_01/candidate_results.csv及8份完整候选JSON|
|反馈修复谱系|experiments/stage6a/repair_01/feedback.json、repair_metadata.json、repair_decision.json、research_M1_prediction.json|
|真实M2原始结果/日志|m2_01/runs、repair_01/runs；对应receipts及raw；无覆盖|
|条件捕获重复性|capture_repeat_01/request.json、receipt.json、pair；2次额外native|
|Baseline精确回归|m2_01/E0_baseline_comparison.json|
|Stage5强制反例|summary_01/Stage5_S3_random11_regression.json；tests/test_stage6a_joint.py|
|成本与复现|COST_AND_REPRODUCIBILITY.md；cost_summary.json、analysis_cost_ledger.json及逐项receipts|
|回归|pretests_01（364）、judgment_tests_01（12）、finaltests_01（376）|
|源保护与数据审计|audit_01/audit.json、最终audit_02/audit.json各191项通过|
|独立verifier结果|verifier_setup_01；verifier_measurement_summary_01；verifier_audit_01（88项）；report_audit_01（74项）|
|E 后续建议|NEXT_STAGE_RECOMMENDATIONS.md|
|最终研究收据|FINAL_RECEIPT.json|

上表中无完整前缀的实验路径均相对`experiments/stage6a/`。analysis_01是M2前草案且保留；analysis_02为正式候选分析。summary_01是权威数值结果；非统计总体样本。所有新完整M2候选为7首次+1修复，不把重复capture、测试或历史重判混入首次成功率。

状态语义：M1_PREDICTED_FEASIBLE仅理想连续模型；M2_MEASURED_PASS仅明确测得子集；RESEARCH_JOINT_FEASIBLE结合测得BW/可选条件捕获与M1 PM/调谐；FULL_SYSTEMSPEC_CERTIFIED始终false。原可靠BW失败继续为FAIL；unsupported指标与完整认证缺口不能变PASS。
