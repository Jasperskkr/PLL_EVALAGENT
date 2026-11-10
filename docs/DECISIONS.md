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


## D011 · 2026-11-05 · Stage 4 独立UGF/PM研究

依据用户Stage4全文与docs/stage4/AUDIT_AND_METHOD_PLAN.md，在verification新增隔离相位端口注入/观测、返回比和数值诊断；冻结SystemSpec、域、M1、allocation、原kernel.cpp/DLL、协议1.1及历史测试不改。新扩展协议0.1只作显式可选研究结果，收敛不等于周期系统标量稳定性证明；不可信测量继续UNKNOWN。先Nominal，方法成立才扩展两例；不开发新修复策略。


D011补充：0.1实际发现开放端口低频DC频差超预设门限；原记录保留，新扩展0.2只用pilot测得DC恢复初始v/u，不改门限。Series/Clamp局部返回比数值收敛后，谐波探针显示反向混频近1，有限侧带不足以认证完整周期PM。最终extension把UGF/PM保持null/UNKNOWN，数值只存diagnostic；Pipeline仅在显式既有Proposal复验中读取，防止污染新FIRST_SHOT。


## D012 · 2026-11-05 · Stage4.2 Physics Mapping / Block Space Readiness Audit

依据用户Stage4.2任务，新增研究只读Mapping Registry、逐指标/逐式域审查、有限数值扫描与10个后续M2候选（含两个保留点）；不替换SystemSpec/Block Space/M1/M2协议/正式搜索策略。范围均保留人工声明性质，正向一致、条件逆解、行为支持、已覆盖点与未验证推广分层。UGF/PM周期认证、RUR定义、非理想静态偏置、噪声/功耗缺口不冒充已解决。

## D013 · 2026-11-05 · Stage4.1 工程映射验证

依据用户Stage4.1全文，先保护未提交Stage4与历史证据，再checkpoint到含Stage4.2 Registry的短期分支。仅新增隔离的平滑参考相位阶跃入口/观测/后处理与研究可信度合同，原物理更新、M1、六轴域、SystemSpec及draft元数据、Protocol1.1、Stage4方法和Agent不变。阈值在首轮M2前落盘，C01–C08开发，源码/协议/分析结果锁落盘后才跑C09/C10；局部映射标签不升级正式PM/频率或整体PASS。开发修正、失败和实测成本单独保留。完成后停止待Leader，不推进Stage4.3。

Stage3A.1为提交基线，Stage4未提交成果先备份/哈希保护，只读取其证据。当前工作区完整回归与干净基线导出验收分别记录实际结果，不混用。研究程序M2/LLM均0；测试内TB另计。独立Commit只含Stage4.2新增文件及本条/状态增量，不纳入此前脏改动。完成后停止等待Leader，不推进Stage4.1。

## D014 · 2026-11-05 · 暂停 Stage 5，先归并并验证主分支

用户明确暂停 Stage 5，要求核验 Stage4/4.1/4.2 提交、正式功能归属和合并后 Baseline，并明确选择 `master` 为统一主分支。三阶段原已同属 `cd70cf4` 祖先链，但旧 master 停在 acf49b8；本次经祖先及旧引用校验快进 master 到 cd70cf4，再切换相同文件树，保留历史分支及所有既有工作树改动。

M1 正式评价归属 physics_mapping，Agent/分配归属 allocation，M2 归属 verification；旧 Track A 核心仅兼容别名。唯一正式研究运行入口仍为 `python -m pll_allocation pipeline`。本次不改算法、物理公式、事件动力学、冻结输入或测量门限；仅新增审查回执及状态记录。合并后 Baseline 真实重跑与历史候选/M1/M2 语义结果一致，严格 PM 和频率精度保持 UNKNOWN。完整结果和实际命令见 `docs/mainline_consolidation_20261105_01/VERIFICATION_REPORT.md` 及其最终回执。Stage 5 场景/策略实验未继续，恢复需用户指示。

## D015 · 2026-11-05 · 用户恢复 Stage 5 端到端比较

用户授权继续完成Stage5。在master@cd70cf4和已真实复现Baseline基础上，先冻结S0–S4、Random seeds11/23/47、每arm最多3次M2、分离首发与确定性反馈修复。新增显式研究场景合同及正式Pipeline小接口，原冻结配置、M1公式、策略实现、M2事件方程和协议保持；M2场景适配独立重判实测BW并保留原验证器结果，不删除哈希检查。真实LLM依既有服务调用，无服务/失败如实报告。局部工程证据预先限定解析S0/S3，全域结论与完整PM/频率认证不升级。计划及合同见docs/stage5；完成后停止等待Leader，不进入5.1/6。

D015执行结果：25首发arm和12确定性修复arm全部留档，S4仅M1假设不可行；主实验31完整M2，局部490native，真实LLM10请求含1JSON失败。解析4/4首发BW通过，随机0/12首发、修复12/12 BW通过但1候选仍M1 PM失败；成功LLM与解析完全相同。原始M1/M2指标与逐约束UNKNOWN/FAIL不合并成完整PASS。351测试及297审计通过，源码/参数/协议保护成立。后处理错误与helper变动见DEVELOPMENT_AND_PROVENANCE；权威summary_02。Stage5完成待Leader审阅，未来先补研究问题3验证认证缺口，但本次不实施下一阶段。

## D016 · 2026-11-06 · Block 变量关系与条件可行域图谱

依据用户本轮表格参考请求，新增只读块级 Variables / Relations / Domains 总表与机器目录，覆盖原 41 项语义及六自由变量，推导声明域内调谐、PM 形状、BW/R/乘积及增益分摊的条件交集。先落盘方案 `block_relations_20261106_01/A0_SCOPE_AND_AUDIT.md`。图内 ADC 内容仅为呈现参考，不迁移其变量或数值；不改变原始研究主线、冻结输入、原公式/分配策略/验证器。新数值证据限 M1，局部历史 M2 支持和完整认证缺口分别列示，不扩域、不自动向 Agent 注入、不启动 Stage5.1/6。


## D017 · 2026-11-09 · Stage 6A 多指标可分配性研究

用户新授权Stage6A。原master工作树仍含Stage5及其他未提交成果；在独立managed worktree/codex/stage6a-multispec-feasibility分支复制并逐份SHA保护14,709个非忽略文件，保留原修改/删除/未跟踪状态，不擅自提交或stash。研究以cd70cf4加精确脏快照为基线，原F盘工作区只读。复用Registry、M1、已有Analytical/SLSQP/repair及唯一pipeline入口，不改核心公式/域/协议。先完成能力矩阵、4725点扫描及条件域分析，再冻结7个初始M2和最多1个反馈修复、40µs条件锁定上限和保守时间包络。只做混合证据RESEARCH_JOINT_FEASIBLE，不把BW/条件捕获和M1 PM升级完整SystemSpec认证。所有结果在Stage6A新目录；不自动合并master。

## D018 · 2026-11-09 · Stage 6B 确定性多指标反馈分配

按用户新任务在 codex/stage6b-sensitivity-allocation 隔离分支继承并逐份保护 Stage5/6A 未提交快照。新增研究约束与物理坐标 Pattern Search，原 pipeline 负责缓存、预算与完整 M2；保留原公式、域、内核及协议，不接 LLM/BO，不合并 master。B1/B2 先冻结96 M1/10000 cheap/6候选槽、40µs条件捕获和统一 A/B/C 顺序；缓存命中消耗候选槽、零新增M2。精确实现与数值验收以新目录 trace/报告为准。

D018交付验证：正式13槽/10新M2/3缓存/1060native，B1 C37→33µs与A持平；B2 24→23µs包络重叠、主裕量不变。原始失败/UNKNOWN及开发失败保留。完整407测试通过；独立候选包全六组重建复现156数值完全一致。归档发现旧Stage4.1工具强制Git元数据，隔离副本改为显式SOURCE_ARCHIVE_NO_GIT，源/协议锁不变；不改已冻结Stage6B算法。新结果全程trace与最终ZIP按独立manifest/CRC/SHA验收，未合并master。

## D019 · 2026-11-10 · Stage7 Noise/Nonideal 扩展

用户授权Stage7。先只读核对Stage6B与截断附件，在独立codex/stage7-noise-nonideal恢复哈希已验证基线并叠加当前源码，旧目录保持。实现方案docs/stage7/IMPLEMENTATION_DESIGN.md已落盘；附件实际止于4.3第4条，已请求补全，先执行明确P0–P3。旧理想封套/公式/内核/协议保持，新增显式版本化外置profile和同核可选扩展；M2波形不得由M1噪声公式生成，严格稳定性和完整认证不升级。

## D020 · 2026-11-10 · 用户完整Stage6C要求替换截断Stage7

以用户补充全文的Phase A–F顺序和最终验收为准。保留Stage7工作树名作为已完成保护审计标识，后续代码/配置/结果/报告采用stage6c；方案修订先落盘docs/stage6c/IMPLEMENTATION_DESIGN.md。独立重建原三核及原407测试通过。新增噪声/非理想是既有物理/验证模块的显式扩展，统一入口pipeline；用户希望收敛主线通过同一入口实现，仍遵守“不自动合并master”。冻结研究噪声、非理想、预算与统计协议；Phase A独立20项实测通过后方可进入B。旧理想核心/协议和旧实验不可覆盖，未建模门控等效关系、周期PM、统计未收敛不升级PASS。

## D021 · 2026-11-10 · 独立随机跟踪协议与冻结求解器兼容

PhaseC原noiseprotocol1.0错误复用确定性1us/100ppm频差门作随机失锁判据，VCO/allsources尽管方差/步长收敛仍UNKNOWN；原72native与UNKNOWN保留。独立40,000块逐项诊断及白频率方差积分证明其将正常随机频率波动当失锁。先记录修改依据与冻结protocol1.1：原160us捕获/200uswarmup门保持，noise-on100us建立后完整4ms，no_slip/clamp/rail、原5deg相位/5mV控制范围及半窗口meanfreq原100ppm，原逐1us门仅诊断；所有源系数/seed/dt/频带不变。独立guards/59pretests后72freshnative/60observations全部统计与有限跟踪通过。不是事后改判v1或调噪声制造通过。

PhaseE扩展problem1.1通过原pipeline.run_multispec/run_pipeline、原SearchController和同包verification，不创建新正式Pipeline。修改allocate.py会破坏Registry与Stage3A.1字节锁，因此恢复原字节；新增noise_optimization从原optimize源码受检查生成唯一extra-hard-margin插入，原函数/默认路径完全不变，记录两种SHA。检查source/compile/malformed/cacheprofile绑定，所有hardFAIL/UNKNOWN不得被其他指标改善抵偿。正式输出F盘新目录，旧checkout/实验均只读；不自动commit或合并master。


## D022 · 2026-11-10 · 归并F盘并聚焦Agent分配策略

用户明确授权将未进入F盘的Stage6B/6C及必要Stage6A研究成果归并、整理F盘项目。F:/LJP/概伦AI/PLL_allocation恢复为统一开发运行工作区；旧隔离工作区、冻结输入及历史实验只读保留。先保存原字节/状态和真实解析、随机失败修复基线，再在codex/f-mainline-consolidation归并；验收后提交并收敛master。原理想pipeline默认语义/预算不变，扩展显式启用；不引入另一正式入口。

用户将研究重心转向现有可测、可分配spec下的Agent首次联合分配与验证反馈。固定模型、规格域与测量协议；核心研究约束采用M2 BW/条件捕获和M1名义PM/调谐，Stage6C噪声/非理想作为可选固定环境。后续优先接入真实LLM反馈修复、等预算策略对照与反馈信息消融；不以M1/M2或SystemSpec进一步完善作为策略研究前置条件。详细范围见research/ALLOCATION_STRATEGY_SCOPE.md。完整认证缺口保持UNKNOWN，历史A/B/C和实验不改。


## D023 · 2026-11-10 · 清理C盘旧PLL数据、固定F盘与同步GitHub主干

用户明确授权“全部清理，只要保证F盘主线代码没被破坏，数据无所谓”，并要求后续不得在C盘建立工作区；随后授权将F盘含Stage6A/6B的主干同步到Jasperskkr/PLL_EVALAGENT。此授权覆盖此前保留五个C盘PLL工作副本/数据的要求，其他项目、Codex会话/凭据/插件不在清理范围。

清理前记录F盘master/e11a4b0及340个源码/配置/数据/构建身份指纹。删除两个bundlecheck完整副本及Stage6A/B/C的大型experiments/delivery，共增加C盘可用空间约11.897GiB；340指纹无变化，原两份ZIP未暂存删除保留。应用archive_worktree对两处返回“Another active task still uses this worktree.”、当前工作树返回“The task's primary checkout cannot be removed.”，故未绕过保护删除三处合计约132MiB工作树壳。后续开发和输出只用F盘。

GitHub已有main/master和Stage6A/B独立分支；本轮以F盘已验收实现为正式源码，保留远端历史与独立研究分支，使用普通可追溯合并同步main/master，不强推，不重跑或捏造历史实验。已有快照/Release继续是历史证据，当前能力以F盘README和研究边界为准。同步是否完成以远端SHA和源码树核验回执为准，不提前宣称成功。

## D024 · 2026-11-10 · Stage 7–10 同工作区开发与最终推送约束

用户要求Stage 7–10直接在现有PLL_EVALAGENT本地项目顺序开发，不为各阶段另建分支、Worktree或副本；唯一工作区仍为F:/LJP/概伦AI/PLL_allocation。保留全部用户文件、历史实验及现有未提交修改，禁止破坏性Git操作、强制覆盖与未经确认的合并。沿用现有正式pipeline、M1/M2和allocation；新增agent模块仅承担规划、策略接口与反馈解释，GUI调用同一正式后端。

每阶段运行相应回归并保存新增配置、Action/Observation/Decision、实验、M1/M2及成本；验收后可本地Commit，不自动Push。所有阶段完成先提供完整Diff、测试报告、实验对照和GUI演示，只有用户明确批准最终验收后才可推送GitHub。本轮优先真实LLM首发与反馈修复接入现有确定性优化/M2链；具体Stage 7–10功能划分尚待明确，不将历史已更名Stage6C的Stage7计划直接复用。

开发前已核对master/e395f24859cdd81e3deb5ea83ba3f9598a27cd16及两份原有ZIP未暂存删除，保存14,868个tracked条目指纹，实际完整回归478项通过（43.76s）。报告与待确认范围见stage7_10/DEVELOPMENT_PREFLIGHT.md。本次仅落盘约束与基线，没有新增Agent能力、研究LLM/M2成绩或GUI验收。

## D025 · 2026-11-10 · Stage7可配置连续域M1探索

用户明确Stage7目标为ResearchProblemV2→连续物理初筛→固定Seed Sobol及物理种子→原正式M1→样本支持的区域/六轴敏感度→PhysicsContext，本阶段不接LLM或M2反馈、不进入Stage8。直接在现有master工作区开发；旧docs/stage7为后来更名Stage6C的历史资料，本轮文档用docs/stage7_exploration，不覆盖历史。

先落盘BASELINE_AUDIT并保存14,868个tracked条目指纹，确认原model.evaluate支持连续C而旧block_space和分配器枚举C。新增独立pll-research-problem-2.0合同与exploration适配，直接复用原inverse_at_shape/raw_prediction/pm_ceiling及正式evaluate；不改原M1/M2、Stage6B合同、SLSQP、Sensitivity或搜索算法。唯一入口pipeline新增显式--explore-problem，未来GUI用同一run_exploration接口。用户定义域是数学行为声明域，不是旧数据或电路能力认证。

M1可行性只使用启用且来源受支持的指标；LockTime/Jitter保留PENDING/UNSUPPORTED和UNKNOWN，不发完整PASS。严格必要条件可给M1假设下不可行证书，未找到样本不能证明不可行；区域盒仅为样本支持的搜索建议。样本精确去重、正式M1与代数分别计数，预算不足/无效/数值失败全留证据；六轴敏感度不把空项填0。最终实跑、回归、保护审计及限制以stage7_exploration/PHYSICS_EXPLORATION_REPORT.md与独立回执为准；不自动Commit/Push或启动Stage8。

## D026 · 2026-11-10 · 用户授权Stage7提交与GitHub推送

用户在Stage7交付后明确要求将Stage7推进提交GitHub，授权本次本地Commit及推送。发布前核对本地master与远端main/master均为e395f248、默认分支main；Stage7验收源码和产物SHA一致，7份PhysicsContext校验通过，原513项回归证据保持。本次提交源码/配置/测试/轻量证据和必要预检文档，保留两份原有ZIP未暂存删除；大型实验仍在F盘。新增Stage7配置/证据保字节属性，避免checkout换行破坏SHA。原验收回执作为历史快照不改写，发布状态另记stage7_exploration/GITHUB_PUBLICATION.md及本地发布回执。普通提交、原子快进main/master，不force、不merge、不启动Stage8；成功与精确SHA以实际远端核验为准。
