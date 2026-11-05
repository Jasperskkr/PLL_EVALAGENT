# 主线决策记录

## D001 · 2026-11-03 · 主线冻结

依据用户提供的原始任务，研究范围为行为级联合 BlockSpec 分配。本目录独立建设，历史目录只读。用户后续更新进入本记录，并同步阶段产物；原始任务保留在 PROJECT_CHARTER.md。

## D002 · 2026-11-03 · 审计优先且继续纵向实现

P0 同时审计源码、正式记录、Git/worktree、模型及数据。P0 交付后继续实现 P1/P2 最小纵向链。新主线从小型已回归 Python 行为内核提取，不整体继承 M07 物理证据控制器。MATLAB 原实现和纠正后的参考轨迹保留，接口预留外部模拟器。

## D003 · 2026-11-03 · 判决层级

新系统的 PASS 仅代表声明行为模型及冻结测量协议下通过；不会升级历史 independent_system_qualified_verdict。预测、真实行为积分后的测量、历史电路观测分别存储。带宽/相位裕度、噪声和抖动未通过可信测量适配前为 UNSUPPORTED。

## D004 · 2026-11-03 · 有界外部调用与未完成状态

首次真实LLM请求虽然配置socket超时60s，实际在HTTP200后约120.57s才超时；因此增加隔离子进程总期限，第二次真实请求在60.03s明确结束。两个失败均保留，未用规则代替。P3/P4真实LLM验收保持未完成。

## D005 · 2026-11-04 · 按三个核心问题审查后续推进

用户要求以更完整的 SystemSpec（含动态、噪声、功耗）和各 Block 变量域，厘清模块映射/范围、LLM 搜索策略、可信行为评估与反馈决策。审查与建议保存于 `CORE_THREE_QUESTIONS_REVIEW.md`。先明确模型合同和可验证指标，再扩充相应评估并接敏感度/搜索；LLM 服务稳定性可独立排查。BO 是待比较的方法，不是已实现能力。

本次仅形成代码/证据审查及阶段建议，没有改变原始研究问题、冻结输入、提取内核或历史结果。现有 P3/P4/P5 未完成状态保持；新增动态/噪声/功耗能力须分别实现验收后才能声明支持。后续模型扩展使用显式新版本，保留 v1 回归。

## D006 · 2026-11-04 · Physics Mapping Foundation Stage 1

依据用户本次 Task A–E，采用 Python 主实现、MATLAB v3.4 冻结参考路线。只建设五个最小物理 Factor、M1 锁定点连续线性模型、隔离的 SystemSpec v0 / Block Space v2 草案和可复现数值对照；本阶段不开发 LLM 搜索、不扩展 MATLAB/GUI、不引入器件实现依赖。详细语义、源文件 SHA 和原公式风险先落盘于 `docs/physics_mapping_stage1/`，再实施。

新研究点为 10 MHz × 8=80 MHz，BW 150–300 kHz、PM≥50°，明确为未冻结草案。保留 v1 合同和其 reset/电压/q0 条件，不通过放宽旧门限接入。M1 的计算完成与研究规格通过均单独标注，不升级为完整行为 TB PASS 或 Verified JointBlockSpec。M0/M2 留接口，未实现时返回 UNSUPPORTED。原始 PROJECT_CHARTER.md 不改。

## D007 · 2026-11-04 · Behavioral Block Space Model v1 / Stage 1.5

依据用户本次完整任务（原文另存 `docs/stage1_5/TASK_REQUEST.md`），在不变更 Stage 1 参数范围与目标的前提下建立可加载的正式行为域、Equation Registry、代表性正向扫描、事件模型交叉验证及校准记录合同。Stage 1 的 SystemSpec 仍为 draft；只冻结本阶段实验快照与哈希，不默认为已批准最终系统目标。优先采用 `configs/physics_mapping_stage1_v2.json`，旧 MATLAB 示例和旧 v1 指标不混入。

声明域、公式有效域、M1规格可行域三者分别处理。正值理想模型的 Routh 条件恒成立，不制造域内“不稳定”标签；低PM视为规格失败，调谐不可达/非理想条件分别明确状态。新增独立 `pll_allocation/block_space/` 层直接加载正式模型，旧Runner与Stage1模块不变；没有LLM/BO/逆向算法或GUI。

按字节复用已审查的既有 Python 边沿插值/Euler事件函数作稀疏交叉验证，范围/协议与结果明确标注；频率/控制比较不能升级为BW/PM/完整M2通过。近轨冷启动与暖启动差异保留为独立证据，不修改公式或放宽SystemSpec。阶段完成后停止等待Leader审查，不自行开展Stage2。

## D008 · 2026-11-04 · Track A Physics-guided Allocation

依据用户本轮 Track A Task A1–A5 授权推进逆向分配、确定性首次基线、工具型 Agent、独立首发比较与反馈接口。以 BLOCK_SPACE_MODEL_V1 内实验快照为本轮官方目标；保留 SystemSpec v0 draft 元数据及原阶段冻结边界，输入/公式/历史不改。实现与受控变体隔离，专用 track-a/physics-guided-allocation 分支，不修改 Track B 验证器、不合并分支。M1 与 M2 标签严格分离，真实 LLM 失败不由 mock 代替；mock 仅验证工作流。详细预先计划见 docs/track_a/A0_AUDIT_AND_PLAN.md。

## D009 · 2026-11-04 · Stage 3A Unified Pipeline Integration

依据用户本轮Stage3A授权整合既有能力。预先审计及方案见 `stage3a/INTEGRATION_AUDIT_AND_PLAN.md`。保留Stage1/1.5、Track A算法与原v1兼容入口，新增allocation薄接口、正式verification包与pipeline Runner；Track B原仓库和历史结果只读，不合并、不删除。正式唯一推荐入口为 `python -m pll_allocation pipeline`。配置绑定官方模型、同内容SystemSpec视图、方程注册表及原协议1.1，不扩大适用域，不改变测量/公式来争取PASS。

本轮真实解析/优化/LLM首发完成M2与反馈接收，另复用已有确定性repair验证FAIL后的完整复验；不开发新优化或学习算法。M2_PARTIAL_PASS只是BW等部分必需指标通过、整体UNKNOWN的显式标签，不能称Verified JointBlockSpec。真实LLM反馈修复、PM独立认证及微Hz频率认证仍未验收。既有Proposal复验标记EXISTING_PROPOSAL_REVERIFICATION，不能算新LLM调用。新运行一律写experiments独立目录，原始轨迹在raw/与正式代码分开，禁止覆盖。

## D010 · 2026-11-04 · Stage 3A.1 主线收敛与发布冻结

依据用户Stage3A.1全文（docs/stage3a1/TASK_REQUEST.md），先保存结构审计、工作树备份和真实迁移前273项回归/M1基线，再将六个原算法模块逐字节迁至allocation；旧Track A只向正式实现兼容转发。正式Verification测试迁入统一套件，历史Track B/Git/outputs只读保留。唯一新研究入口pipeline，旧v1及Track A CLI标Legacy。

模型/六参数域/SystemSpec/公式/策略/提示词/协议1.1/阈值不变；PM/UGF/微Hz认证继续UNKNOWN。仅修复构建工具覆盖风险并新增审计/回归/发布工具。因旧Git换行归一化破坏原字节SHA参考的可复现性，.gitattributes及暂存保留既有快照原字节，工作区历史数据不改。正式代码先提交，根RELEASE_MANIFEST及ZIP由该Commit生成外部资产避免自引用。两个原有ZIP删除和外部ZIP不进入提交。

本轮283项正式测试+原Track B 28项通过；无历史目录独立重新编译282项通过。四组候选/M1/M2指标与迁移前一致；真实LLM一次JSON失败后同配置三次真实决策完成M2。7次完整验收M2/758次原生仿真，修复只复用确定性算法。细节见根架构/验收/归档报告。完成发布后停止等待Leader，不自动启动新研究。


## D012 · 2026-11-05 · Stage4.2 Physics Mapping / Block Space Readiness Audit

依据用户Stage4.2任务，新增研究只读Mapping Registry、逐指标/逐式域审查、有限数值扫描与10个后续M2候选（含两个保留点）；不替换SystemSpec/Block Space/M1/M2协议/正式搜索策略。范围均保留人工声明性质，正向一致、条件逆解、行为支持、已覆盖点与未验证推广分层。UGF/PM周期认证、RUR定义、非理想静态偏置、噪声/功耗缺口不冒充已解决。

Stage3A.1为提交基线，Stage4未提交成果先备份/哈希保护，只读取其证据。当前工作区完整回归与干净基线导出验收分别记录实际结果，不混用。研究程序M2/LLM均0；测试内TB另计。独立Commit只含Stage4.2新增文件及本条/状态增量，不纳入此前脏改动。完成后停止等待Leader，不推进Stage4.1。
