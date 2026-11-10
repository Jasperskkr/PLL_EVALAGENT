# Track A：审计与预先固定的实验计划

2026-11-04。依据本轮用户授权继续 Stage 1/1.5，范围仅为行为级规格分配。

实查：本目录原无 `.git`，建立原内容基线提交，专用分支 `track-a/physics-guided-allocation`。不创建、切换或合并 Track B 分支。新增实现限 `pll_allocation/track_a/`、`tests/track_a/`、`configs/track_a/`、`docs/track_a/`；实验输出使用拒绝覆盖的新目录。

权威输入是 `configs/BLOCK_SPACE_MODEL_V1.json` 内的 `experiment`；与 `configs/physics_mapping_stage1_v2.json` 比对哈希。原 SystemSpec v0 的 draft=true 与 Stage 1.5 仅阶段冻结声明保留。本轮将该快照作为 Track A 官方比较目标，不将旧 `examples/frozen80.json` 的相位/锁定协议混入。

复用：`block_space.contracts.load_model/make_candidate/check_parameters`；`physics_mapping.model.evaluate`；`physics_mapping.experiment.judge_experiment`。完整候选沿用 `pll-physics-mapping-2.0`、17 个带单位输入、原 conventions；不另创 I_up/V0 等语义。旧 Policy/Runner 的职责分离原则沿用，数值合同不同，不直接调用旧离散搜索。逐文件原路径、SHA、适用域另存 `reuse_manifest.json`。

Stage 1.5 报告已知名义点及 44 个通过点的存在性。名义基线公开使用默认点；不加载 139 点数据、44 点集合或事件结果训练/选择。所有策略均为 prior-informed；不得宣称对官方目标完全盲测。当前任务没有 M2 反馈输入。

预先计划：名义、解析反推、归一化敏感度+约束优化、单次 seeded random、mock agent；真实 LLM 若环境存在则另记请求与失败成本。统一每目标一次正式提交，M2 预算 0，最多 2000 次廉价预测/数值模型调用、16 次完整 M1（含正式独立评估）。优化最多 9 个电容对，连续变量归一化，先求约束裕量，再考虑参数/调谐裕量及扰动。权重/裕量尺度是工程选择，写入配置，不是物理定律。BO 暂不增加：六变量含两个小离散轴且 M1 便宜，先检验确定性反推与优化是否已足够。

受控测试变体仅修改 SystemSpec BW/PM，频率计划、拓扑、域不变；全部提前写入配置并冻结，校准集为空。官方一次案例与变体集合描述分开，不报告统计意义成功率。不可行仅在必要条件构成证明时声明；局部优化失败为 NOT_FOUND。

A1 解析推导及实现 → A2 完整候选及成本 → A3 工具日志/模型接口 → A4 首次比较 → A5 模拟反馈/合同测试 → 完整旧测试回归及保护哈希审计。任何阶段候选最多为 M1_VALIDATED，Verified JointBlockSpec=false。M2 仅导出/预留注入，Track B 验证器不修改。

技能：analog-pipeline 只用于流程与独立 verifier 审查。拓扑已由用户冻结，既有授权覆盖架构门；本阶段无晶体管设计/EDA，因此不生成 spec.yml、不引入 servers.yml 或 L3 仿真。技能引用的 shared-references 文件缺失，以本任务边界为准。外部技术检索尝试遇工具 HTTP403，推导以已审计本地 M1 方程及独立数值检验为依据。
