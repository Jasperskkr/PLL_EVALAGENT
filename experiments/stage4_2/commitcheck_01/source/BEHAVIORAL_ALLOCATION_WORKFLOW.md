# 行为级联合分配流程

1. 读取并规范化版本化Problem，检查固定拓扑、SI单位、N·fref关系、模型域及测量协议；冻结输入与BlockSpace/Topology快照。
2. 策略接收Problem、已有真实尝试及剩余预算。首次提议看不到后续反馈。完整五Block候选与理由写proposal.json；第一次候选立即写initial_joint_block_spec.json。
3. 独立检查完整性、单位、声明域、共同条件、CP斜率耦合、复位时间和VCO调谐/初值域。非法候选记录失败，不运行TB；提议预算仍消耗。
4. 解析计算平衡相位/Veq，只作screen prediction。独立调用完整40us行为TB，记录所有400/420周期；失败调用也消耗一次评价。
5. Verifier核对Backend身份、problem/candidate SHA、完整窗口/协议、实际单位与模型域，再对原SystemSpec逐项判决。没有可靠支持的指标为UNSUPPORTED→UNKNOWN。
6. 保存每项测量、裕量、归一化违例、预测误差和成本；写SHA链。PASS停止；FAIL可由策略提出完整新候选；预算耗尽、Policy停止、工具失败或未支持指标如实报告。
7. 输出input_system_spec、block_space_snapshot、topology_snapshot、initial/final_joint_block_spec、constraint_checks、behavioral_tb_results、system_metrics、allocation_trace、run_manifest、report及逐轮cycles。

复现命令和已执行结果见END_TO_END_ACCEPTANCE.md。相同确定性输入的decision_sha256忽略机器时间但包含完整候选、测量和判决；run_manifest另外保留环境、运行源码SHA和耗时。saved_proposal_replay明确标记回放，任何真实LLM结果都必须另有调用元数据。

锁定时间沿用旧协议的首次连续hold窗口诊断，不能自动解释为最后一次违例后的严格settling time。今后若引入新的锁定时间SystemSpec，必须先冻结其测量语义并扩展Backend，不能直接把诊断值套进不同定义。
