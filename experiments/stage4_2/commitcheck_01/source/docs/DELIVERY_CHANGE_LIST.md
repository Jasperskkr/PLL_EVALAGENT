# 本轮文件与变更范围

旧项目修改：0；旧Git分支/worktree变更：0。本目录初始为空，因此交付内容全部为新建文件。

|类别|路径|内容|
|---|---|---|
|长期主线|PROJECT_CHARTER.md、AGENTS.md、README.md、docs/DECISIONS.md、docs/PROJECT_STATUS.md|用户原任务、今后约束、入口和阶段状态|
|P0|P0_EXISTING_SYSTEM_AUDIT.md、P0_MODULE_REUSE_MATRIX.md、P0_TARGET_ARCHITECTURE.md、P0_MIGRATION_PLAN.md|来源审计、取舍、架构和迁移|
|数据与接口|docs/DATA_INHERITANCE_CATALOG.md、docs/INTERFACE_CONTRACT.md|电路/行为/MATLAB数据角色、域和预留接口|
|实现|pll_allocation/contracts.py、behavioral.py、policies.py、runner.py、cli.py、llm_transport.py、__main__.py|统一合同、真实TB、策略/反馈、记录、单入口、真实外部调用|
|直接复用|pll_allocation/_legacy/、data/legacy/|10份原字节提取文件、完整来源SHA、回归期望|
|验证参考|data/verification_reference/|24组记录/CSV/语义，共96个验证侧文件及manifest|
|输入|examples/、configs/llm_env.json|六个冻结案例和无密钥LLM环境配置|
|测试|tests/|93项合同/真实积分/轨迹/Runner/外部进程/失败路径测试|
|可复现工具|tools/audit_sources.py、create_examples.py、inherit_matlab_reference.py、validate_delivery.py|只读审计、案例生成、参考继承和输出核查|
|阶段/交付|docs/P1_CONTRACT_VALIDATION.md、docs/P2_BEHAVIORAL_VERTICAL_ACCEPTANCE.md、MAINLINE_ARCHITECTURE.md、MODULE_REUSE_REPORT.md、BEHAVIORAL_ALLOCATION_WORKFLOW.md、POLICY_COMPARISON_REPORT.md、END_TO_END_ACCEPTANCE.md、LEGACY_ARCHIVE_PLAN.md|已落实能力、对照、验收及未完成项|
|机器证据|docs/audit/、docs/validation/、outputs/|来源清单/保护、JUnit、acceptance JSON、真实运行和失败日志|

报告没有将接口实现标记为真实LLM或MATLAB实机验收；未完成项在状态与验收中保留。
