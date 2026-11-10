# PLLAgent 行为级联合规格分配主线

本目录是唯一新主线工作区。先读 `PROJECT_CHARTER.md`、`docs/PROJECT_STATUS.md` 和 P0 四份报告。

2026-11-10起：本F盘目录是统一开发/运行工作区，Stage6A/B/C隔离目录作为来源及历史证据保留。本轮用户授权归并；后续重点是现有可测、可分配规格下的Agent首次分配和验证反馈策略，研究边界见 `docs/research/ALLOCATION_STRATEGY_SCOPE.md`、D022。

- 唯一正式运行入口：`python -m pll_allocation pipeline`；默认理想链保持，Stage6B/6C经显式选项启用。
- 固定现有SystemSpec、Block Space、M1/M2及测量协议进行策略研究；模型完善不是后续策略实验前置条件。
- 核心研究使用M2 BW/指定条件捕获、M1名义PM/调谐，按来源分别判决；完整认证UNKNOWN不妨碍如实研究受支持指标。
- 新Agent接入沿用现有Policy/Runner边界，不创建第二套正式Pipeline。真实LLM反馈修复尚未实现，不得把确定性修复或mock当成真实LLM成果。
- 源码、轻量测试证据纳入Git；新运行写`experiments/<new>`，大型历史结果位置见`docs/mainline_integration_20261110_01/EVIDENCE_INDEX.md`，不迁移或覆盖旧记录。

- 研究问题：给定冻结 SystemSpec、固定拓扑及 Block Space，比较物理先验 LLM 的首次联合分配与有限反馈修复能力。
- 唯一交付链：SystemSpec → JointBlockSpec → 真实行为级 TB → Verified JointBlockSpec。
- `PROJECT_CHARTER.md` 保存用户原始任务全文；更新阶段方案时记录 `docs/DECISIONS.md`，不得隐式改变主线。
- 旧项目只读；不得修改旧源码、冻结输入、实验及运行记录。新结果写本目录的新建输出目录，拒绝覆盖。
- 不引入 ngspice、PDK、MOS、sizing、M07/G1/G2 作为运行依赖；电路数据只保留溯源与模型参考。
- 先审查、后复用；复用文件记录原路径、SHA256、适用域和语义。不能把声明域当作可实现电路能力。
- Policy 只提议完整候选；Runner 独立控制约束检查、完整 TB、预算、判决及输出。
- 快速预测与完整 TB 测量分开；UNSUPPORTED/异常/超域不能判 PASS。
- 第一次候选必须在首次 TB 前写盘；记录真实调用、失败成本、修改理由；回放不能冒充新 LLM 调用。
- 每阶段先落盘可检查产物，再推进；状态报告说明已完成、部分完成、待验收及实际执行命令。
