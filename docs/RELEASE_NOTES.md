# 共享研究源码整理

## 2026-11-24 集成代码提交与独立检出审核

- 提交后的独立克隆从源码重建四个后端：完整回归958通过、10项历史档案依赖跳过、零失败/错误（`-W error`）；13组真实Spec/N流程、230项检查通过，151次M1/36次M2/3844个原生子运行，无LLM/TEST。此前N10、lock下限60µs以实测72µs交付1/1。
- 12组VCO导出与原文件绑定校验通过，附加父/子进程轨迹无旧业务函数调用；wheel构建/安装及新增配置核对通过，运行后304个维护文件字节不变、检出干净。细节见发布审核，原始证据不提交。

- 按用户要求发布完整维护源码，包含既有噪声/M2、条件物理分配、VCO开发合同、输入输出与交接清洗、整数N适配；实验数据及一次性N10追踪不提交。
- README补充噪声/启动配置、VCO导出、权威产物及验收边界；章程、架构、代码导读和审查指南同步当前合同能力。提交后的独立检出、原生重建与完整链路审核见 `PUBLISH_AUDIT_20261124.md`。
- 独立检出发现6个旧 `track_a` 转发文件的CRLF与通用LF属性冲突，导致克隆后显示虚假修改；为该兼容目录保留原字节，不改转发源码或数值来源。

## 2026-11-24 多规格全链路验收与发布交接

- 固定源码快照上运行12组输入，覆盖N=4/8/10/16、不同BW/PM/lock、失败重分配、预算耗尽、M1不可行、非法N、Auto确定性分支与条件物理增强；实际146次M1、35次M2、3738个原生子运行，211项独立边界/产物检查通过。部分交付、空交付及UNKNOWN保持原义，未使用付费API或TEST M2。
- 另以真实N8流程记录父进程及M2子进程函数轨迹：正式主线调用清晰，旧业务函数未执行；旧模块提前导入仍列为后续结构债务。本轮无生产代码变更。
- 实时查询/fetch核对远端默认main与本地未推送提交；新增 `SPEC_MATRIX_AND_REMOTE_20261124.md`，更新 `CODE_STATE_20261124.md`，建议功能分支集成提交后通过PR更新main。本轮未commit/push，实验产物继续只保留本地。

## 2026-11-24 标准连续域 M2 按 Spec 分频比参数化

- 标准 M2 请求和原生适配读取候选的正整数 N，统一按 N×f_ref 计算调谐启动点、捕获频率/ppm 和双步长收敛误差；观测保存显式频率计划。参考频率仍为10MHz、电压轨仍为0–1.2V，原步长/边沿分辨率门槛继续执行。
- 连续请求使用 `integer_n_metrics_1.0` / `pll-continuous-m2-1.1`，由原协议派生并绑定当前 N、目标频率、Spec 和源码身份。捕获初态0.15V、160µs窗口及幅度/步长/窗口收敛阈值保持；locktime上下限继续由原区间判决处理，不保证任意规格有解。
- 原 C++ 内核、旧冻结验证门禁及 `m2_protocol.json` 字节保持；旧无频率元数据的历史观测明确标为 `LEGACY_FIXED_N8_TRACE`。`configs/provenance/integer_n_m2.json` 保留五个适配/测量文件的旧新哈希；物理Registry只更新simulator当前绑定，历史N=8证据不推广到其他N。
- 新增 `tests/verification/test_frequency_plan.py`，覆盖N变化的频率提取、ppm归一化、100MHz调谐启动、协议绑定/篡改拒绝、非法N及N=4/8/10/16原生观测。完整M2 PM/jitter和器件可实现性仍不认证。
- 定向验收去重141通过、1可选历史档案跳过；真实N8/N10均完成标准M2，各106个原生子运行、零LLM/TEST。N10原Spec的BW为229.004908kHz，locktime72µs、区间71–73µs，满足>60µs，最终交付1点；N8原nominal首点54µs超过40µs上限，正确FAIL。新实验分别保存在 `experiments/20261124_integer_n_m2_n8_native` 和 `experiments/20261124_integer_n_m2_n10_native`，不覆盖此前门禁/M1-only记录。

## 2026-11-24 结构审核与输入输出边界清洗

- 梳理当前默认连续域多点调用链、可选开发能力、共享冻结来源及旧兼容入口；结论见 `STRUCTURE_AUDIT_20261124.md`。保留用户原有未提交改动，没有删除历史代码或实验。
- 新增严格外部 JSON 输入与 `run_manifest.json` 权威产物索引；pipeline 的文件错误返回结构化输入/输出错误，非对象 allocator 在执行前拒绝。
- 多点交付校验迁到共享 `delivery.py`，生产端与 VCO 消费端使用同一门禁，补摘要状态/数量/推荐一致性；原 `validate_source` 接口和可选 VCO 辅助入口保留。
- 按用户要求合并当前频率规划一起验收：交付门禁分别识别旧N=8适配与新整数N适配，不依赖原DLL读取记录。独立源码快照上默认N=8交付3点、N=10交付1点，二者保留PM/jitter UNKNOWN。
- M1 Handoff 补 READY 状态一致性和相对 context 引用，支持完整运行目录迁移，并保留旧绝对路径合同；迁移后不回退原目录绕过坏证据。
- 新增接口边界回归；清洗前后默认原生运行的候选六参数、M1/M2数值与判决、交付集合、真实调用计数逐项一致。六份冻结分配源码仍字节相同。完整测试与本地验收证据见结构审核。

## 2026-11-24 VCO Handoff V1 正确性与追溯冻结修复

- 局部截距改用实测频率锚定，区分近似测量、插值根估计与带独立精度门槛的复测确认；未确认目标点禁止准备正式回填参数。保留非零测量残差和证据，不用反馈自报大容差授权确认。
- `validate_guidance/assess_feedback/prepare_revalidation` 由独立原策略重建合同；assess/prepare增加`--options`。自定义硬约束缺失或被放宽时拒绝，不从Guidance自身反推可信策略。
- Guidance与Feedback的可比较CP证据取交集，分别记录；候选/Icp或工况不匹配明确报错，无证据UNKNOWN，不支持普通反馈隐式替换。
- CLI实际校验原Handoff文件字节SHA256；解析JSON的API明确标记字节检查未执行。所有哈希仅表示一致性，不认证实验真实性。
- 附加合同修订标记1.1，保留原schema 1.0及合法旧精确数据的兼容解析。仅回填f0/Kvco，不新增Icp物理回填；P1仍默认关闭，原求解/M1/M2/Noise/Jitter和默认入口无修改。
- 冻结验收：最终VCO定向58 passed；全量884 passed / 10项既有历史档案依赖skipped（262.66秒）。nominal/tight各5候选参数哈希、正式结果、状态与原基线一致，各6次M1；导出前后原Handoff字节一致；架构/原分配源码字节审计通过，原工作区32个未提交/未跟踪源码文件字节未变。四项旧缺陷已用修复前快照复现并保存前后证据。

## 2026-11-23 独立 VCO Sizing Contract

- 从稳定提交 `e2d4dfa2d1d68247df11ede477a5d28df693078e` 隔离开发；只新增显式 VCO 导出/反馈接口及对应测试、说明，不带入原工作区未提交实验。
- 通过独立 `vco_sizing_guidance.json` 关联全部已交付候选、原 Handoff、SystemSpec、CP/LF 和模型身份。nominal f0/Kvco 保留，精确匹配降为偏差记录；显式 Block 硬约束仍执行。
- 定义实测调谐点、局部 Kvco/切线截距、网表/工况/证据与失败反馈合同。共同电压范围/余量无证据时保持 UNKNOWN；回填转换要求新合法 Problem、原 SystemSpec 和独立实验身份，原生 M1/M2 拥有正式判定权。
- 导出是分配完成后的显式命令；默认分配器、原始 Handoff 字节、六变量反解、Noise/Jitter/M2 实现与默认行为保持基线。
- P1 仅显式调用：固定 CP/LF 的受限离散采样复用原 Runner、M1 和可选原生 M2，预留审计/posthoc预算，区分域拒绝、M1、已测 M2 和未验证区域，不插值认证连续区域。
- 验证：完整回归861 passed / 10项历史证据依赖 skipped；随后新增无测量失败反馈及CP候选绑定检查，最终VCO定向回归39 passed。nominal/tight各5个候选的关闭功能科学输出与修改前稳定基线一致，各6次M1；原始Handoff导出前后字节一致，架构/原分配源码字节审计通过。原生M2多点、单点和真实超时均已执行，四个新CLI子命令已实跑。
- 使用与限制见 [VCO Sizing Contract](VCO_SIZING_CONTRACT.md)。

## 2026-11-20 LLM Physics Tool 主动目标补充

- 在原 `physics_tool_policy.py` 的 State、Prompt、校验和动作适配中连接条件噪声/启动能力。`BUILD_PHYSICS_REGION` 可选使用请求1.1，只增有序 `physical_objectives` 与 `tool_options_sha256`；按已有noise/startup开关开放NOISE_AWARE、INITIAL_STATE_AWARE、FAST_LOCK，在原M1/条件噪声可行层内复用偏好选择器。未启用时原Prompt/State保持，1.0字段与校验语句原样保留。
- 新 `agent/conditional_observation.py` 生成最多24个候选的CPRED摘要，包含条件RMS jitter、四源贡献与主导源、裕量、初始频偏、近似阻尼、轨裕量及捕获风险；绑定候选/来源证据/问题/模型/工具配置及profile积分身份。预测不升级为正式M1/M2 PASS，缺失项UNKNOWN，捕获时间null。
- 保留原OPTIMIZE_LOCAL、PROBE_REGION和MEASURE_LOCAL_SENSITIVITY合同与求解器。定向验收发现PROBE小预算误入SLSQP预播种，已限定修复为直接调用原Sobol；没有重构Planner、Auto或反馈Runner。LLM只能选策略/合法目标/区域/预算，额外参数、PASS、阈值或profile覆盖被严格字段校验拒绝。
- 不新增Sizing Agent/完整Sizing接口、ngspice/PDK或跨层Orchestrator；沿用已有来源绑定的advisory反馈扩展位置。Auto决策方法与原Prompt逐项一致；六份冻结实现与107项补充前配置/来源/数值核心文件字节一致，架构审计通过。
- 离线独立Mock直接观察诊断并发起三个目标构造及原搜索工具；LLM/Auto实际M1分别38/46（上限96），每个目标构造实际2次M1；LLM与M2均0次，未调用付费服务。Auto仍先1轮确定性再6轮Mock。接口验证不证明真实LLM策略或搜索性能收益。
- 本轮定向回归96 passed（153.15秒）；最终完整回归859 passed / 10项历史档案依赖skipped（381.61秒），UTF-8、`-W error`下无失败/警告。全部请求、Planner State、构造前提案、M1账本、失败日志、审计和中文工程报告保留在新目录 `experiments/llm_physics_tools_20261120_01/`；前轮Phase 0–4对照结果不覆盖、不重做。

## 2026-11-20 条件噪声、启动构造与统一物理排序

- 按审计→预测→条件分配→启动构造→统一排序实施。新增四个默认关闭开关，保留三模式原决策/切换、六轴 SI、Policy/Runner、预算和正式判决。原 nominal/tight、默认配置、provenance、原六份分配实现、M1/noise 与全部原生核心逐字节保持。
- `physics_mapping/analytic_features.py` 增加自然频率、近似阻尼、精确三阶线性极点、初始频偏、轨裕量及启发式风险。没有可靠动态捕获估计时 Lock 预测为 null，不推断严格捕获不可行。
- `physics_mapping/predictors.py` 复用 `optimizer_noise_estimate`、原 PSD 与积分换算，默认 noise_all、10kHz–1MHz；与 `noise_mapping` 一致，带四源贡献和 profile 身份。没有额外隐藏的正式 M1 扫描。
- `exploration/conditional_physics.py` 新增版本化可选工具选项、预测缓存、条件门槛与归一化 jitter 裕量；`physics_region_builder.py` 保留原 inverse/请求，在构造预算内筛形状、电容、增益拆分，并生成启动偏移/中间调谐/低电流/低电容候选，保留原回退能力。
- `region_explorer/explorer.py` 继续同一 SLSQP/M1/预算；可选加入条件 jitter maximin 裕量及独立非负正式 M1 约束，已满足 jitter 时保持该层。`agent/candidates.py` 附条件证据，正式判断不变。
- `agent/candidate_pool.py` 先筛条件噪声再距离打包，避免合格邻点被更高 M1 裕量代表点遮蔽；`pool_search.py` 条件目标参与停止和质量观察，启用时首次推荐复用 `select_m2`。`initial_allocation.py` 只传工具配置、增加独立预测/廉价积分计数。
- `agent/physics_ranking.py` 新增统一归一化词典序；`search_loop.py` 加推荐选择钩子；`handoff.py` 附选择证据；`feedback.py` 继续原审计/M2、记录排序理由与缺失预测回退。条件噪声状态与正式联合支持项状态严格分开，M2 PM/jitter仍 UNKNOWN。
- `agent/spec_allocation.py` 增加配置、条件摘要、最佳正式候选、差距及停止原因；`configs/agent/noise_aware.json`、`physics_enhanced.json` 提供独立同预算输入，`pyproject.toml` 安装两配置。`tools/run_physics_comparison.py` 只编排正式 CLI，汇总 nominal/tight × Baseline/Noise-Aware/Enhanced；不新增求解器。
- 新增四份测试：`test_analytic_predictors.py`（单位/多项式/噪声一致性/f0不变性），`test_conditional_allocation.py`（真实分配/约束/SLSQP/配置阈值），`test_startup_construction.py`（边界/多样性/关闭兼容），`test_physics_ranking.py`（首次后续一致/未知回退/门槛/合格邻点）。更新 CODE_MAP、COMPATIBILITY、ARCHITECTURE、SPEC_ALLOCATION 和 configs README。
- 修改前完整基线826通过、10历史档案跳过；源码审计及原生构建身份校验通过。全关实跑两问题的候选、M1/M2数值/判决顺序、M1/M2/native计数与修改前精确相同。真实实验/原始失败日志保存在本地 `experiments/physics_enhancement_20261120_01/`；最终测试和快速对照见该目录中文工程报告，不上传波形或二进制。
- 初轮完整回归暴露8项旧 SimpleNamespace 档案测试兼容失败，已修复缺省访问；开发中一次边跑边改触发源码保护，保留失败日志后在稳定源码重跑。未改写来源哈希或绕过身份校验。
- 最终完整回归 **842 passed / 10历史档案 skipped，343.15秒**；最终架构/六冻结实现审计通过，额外47项原配置/来源/M1/noise/原生核心字节检查全部一致。最终全关两问题实跑与修改前精确一致，见 `legacy_numeric_regression_02.json`。
- 最终同预算实测（K5、M1≤96、M2≤3；实际各3次M2）：nominal 首次Lock Baseline/Noise-Aware/Enhanced=54/53/23µs，支持项FAIL/FAIL/PASS；tight=30/19/13µs，支持项FAIL/PASS/FAIL，Enhanced首点原生BW306.058kHz超300kHz。M1实际11/35/35，两问题均未降低M1开销；噪声条件达标数均0，nominal最佳54.654/54.644/54.644ps，tight最佳49.154/49.595/49.595ps，未达10ps且tight略恶化。停止原因及缺口如实保存，标准M2 jitter/PM仍UNKNOWN；不宣称统计或整体策略优越性。最终原始对照位于 `quick_comparison_02/`，上一轮保留不覆盖。

## 2026-11-19 多点交付同步与输入审核

- 将11月18日已实测的多联合点交付源码、配置、示例和文档同步为共享进度；默认M1池5、联合目标3、M2预算8，保留旧配置省略目标时的单点行为。不改变物理公式、验证标准或原生内核。
- 补充手工SystemSpec与六轴连续范围的输入位置、正式命令及仅解析校验方法；说明冻结block_space/参考Spec与新版problem的区别，以及保留单点配置的用途。
- 五类Spec×三策略压力测试已完成，包含真实LLM反馈与原生M2；失败、UNKNOWN和空交付均保留。文档披露M2近重复预算消耗、LLM意图/动作差异及终止分类问题，这些问题尚未修复，不把同步发布称为修复完成或策略优越性证明。
- 本次只共享维护源码/配置/测试/文档；原实验、原始API日志、波形、审计压缩包、凭据与编译产物继续保留本地。输入/路由定向审核33项通过；本次UTF-8、`-W error`完整回归826 passed / 10项历史档案依赖skipped，208.07秒，无失败/警告；架构/原物理实现字节审计通过。


## 2026-11-18 多个 M1＋原生 M2 支持项通过点交付

- 新增独立 `m2_target_count`；公开默认配置 M1池5、联合目标3、M2预算8。历史配置省略新字段仍为目标1，保持旧单点接口与状态。
- 原反馈控制器累计质量合格、六轴距离达标的支持项通过点，首个通过后继续；池耗尽时预算内修复/补点。先过滤通过子集再去重，防止未通过邻点遮蔽交付点；成功补点使用明确目的，不冒充失败或误触发 Auto 失败升级。
- 小池原生验收发现局部优化近邻被内层误算成新点，导致外层拒绝后提前停止；统一所有工具输出在补点计数前排除已交付近邻，并让成功补点优先 DIVERSITY。保留失败原始证据，新增针对 SLSQP 来源的停止条件回归。
- 新增 `joint_status`、目标达成标志、首点/目标到达时间；`sizing_handoff.json` 只含原生联合通过行为目标与 SystemSpec、单位、M1/M2 证据，TEST 不进入正式交付。部分找到、预算耗尽、UNKNOWN 如实保留。
- 增加 tight LLM/Auto、预算不足及小池补点复现输入；同步 README、工具、配置、运行及接口文档。未修改物理公式、M1/M2 算法/判决或原生内核，未集成管级 sizing。
- 两组 spec × 三种模式实跑均交付3个原生联合通过点；nominal 确定性/LLM/Auto 的 M1/M2/API 分别15/5/0、14/4/3、15/5/0，tight 分别13/4/0、13/4/2、13/4/0。共5次真实 API 均 HTTP200。样本量小，未证明策略优越性；六组未触发真实 LLM 的 M2 后重新搜索。
- 预算不足案例实际交付1/3并标 PARTIAL；小池补点修复后交付2/2，M1/M2/API=13/3/0。最终代码 nominal/tight 重跑的3点六参数及 M1/M2 数值与修复前逐项相同。标准 M2 PM/jitter 始终 UNKNOWN，不认证管级/PVT。
- 最终完整回归826 passed / 10档案依赖 skipped，203.44秒；UTF-8、-W error 下零警告/零失败。架构审计通过，六份原物理实现字节不变；不提交实验输出、API 原始记录或二进制。

## 2026-11-17 新版入口优先与模式边界

- CLI 默认进入连续域多候选分配，问题可显式指定，allocator 默认采用三模式配置；只有 `--out` 时使用并记录 nominal 示例。
- 旧冻结链改为显式 `--legacy-frozen`；旧 Python runner 与绑定合同保留。v1 `run/suite` 须显式 `--legacy-v1`。冻结的 `llm_agent` 未实现反馈修复这一限制明确记录，不借用新版能力。
- 在读输入/运行前统一检查路由互斥和所有参数的消费范围，消除 Planner/子区域/探索等分支静默忽略其他路径参数的情况，零值预算同样检查。新版预算使用 allocator JSON。
- CLI 启动打印实际路由，输出 `execution_route.json`；主结果补路由及实际执行来源。Auto 零 LLM、确定性与 TEST 注入分别标识；保留旧 schema/兼容标签。嵌套候选池模式与 policy 冲突会拒绝；有 Provider/控制器失败的部分结果仍保存，但 CLI 非零退出。
- 补充入口/误用回归；不改物理公式、M1/M2 测量和判决，不提交实验产物。
- 独立273文件源码副本重建四个原生后端，完整回归813通过、10项历史档案跳过，`-W error` 下零警告；架构/原算法哈希审计通过。裸默认、仅问题、新反馈/Auto、显式冻结和原单点均实跑；nominal/tight/feedback/Auto 的候选参数、M1指标/判决及推荐 M2 数值与上轮逐项相同。本轮零真实 API，LLM仅离线接口回归。

## 2026-11-17 多策略多候选 Spec Allocation

共享复现补充：新增 `configs/examples/spec_allocation.json` 八组输入及 `tools/run_allocation_examples.py`，仅生成配置并调用正式 Pipeline；真实 LLM 案例需显式授权与进程环境。更新 tools README、RUNNING、配置说明及多策略产物合同。原始实验、验收详表、波形、审计包与 API 日志保留本地，不随本次源码提交。

待提交源码的独立副本完成全新 venv 安装、四后端重建与八案例运行；完整回归786通过、10项档案跳过，架构审计通过。Windows GBK 解码警告在 UTF-8 环境下以 `-W error` 定向复验清除，运行说明已补 `PYTHONUTF8=1`；没有修改求解/测量算法。

用户后续明确授权真实 LLM 后，复用现有 Messages 环境配置补跑6次实际 API，均 HTTP 200 / RESPONDED。LLM nominal K5：5个 M1 点、1个原生 M2 支持项通过点，M1/M2=23/2、LLM=4、55.056s；Auto K10 触发真实 LLM 分支：10个 M1 点、M1=24、LLM=2、16.413s，M2未执行。未改正式源码或判决；结果保存于全新 `experiments/spec_allocation_llm_20261117_01/`。完整 M2 仍 UNKNOWN，真实 LLM M2反馈重分配尚未另行执行，不据此声称优于确定性方法。

- 原 Pipeline 增加 `pll-spec-allocation-1.0` 配置，选择 DETERMINISTIC / LLM_PHYSICS_GUIDED / AUTO_HYBRID，统一 K、M1/M2/LLM 总预算、质量与距离阈值。
- 原初始分配复用 V2 诚实空上下文 Cold Start，补多候选停止和原 Sobol 按需调用；无新物理求解器。保留旧配置与单点行为。
- V2 确定性反馈规则提取到 `agent/deterministic_feedback.py`；原反馈控制器支持确定性搜索、Cold Start 和优先验证池内其他点。真实 API 默认禁止，离线策略和 TEST M2 明确标记。
- 新增候选/证据/推荐/成本结果适配；正式 M1、原生 M2 测量及判决、物理公式和内核未修改。真实运行找到支持项通过点，完整 M2 PM/jitter 仍 UNKNOWN。
- 完整回归778 passed / 10 archive skipped；旧错误文案兼容修复后的相关与 V2 回归94 passed；最终反馈/Auto 分支回归46 passed。接口与复现命令见 [多策略分配说明](SPEC_ALLOCATION.md)。没有真实 LLM 效益结论，没有增加 sizing、服务化或部署范围。

2026-11-16 用户授权：重写 README，按职责整理核心源码，精简远端实验资料和历史文档，实际验证后同步 GitHub。

- 反馈控制/连续候选验证实现迁至 feedback.py、continuous.py；旧导入和 CLI 保留同一实现的兼容入口。
- 可选对照编排迁至 studies，测试按行为职责重命名。
- 配置主路径改为 problems/agent/providers，并提供中性 CLI 与结果文件名。
- 本地实验、原始文档、GUI 保留；共享源码只保留核心配置、测试夹具、来源合同、关键说明和原始章程。
- 不改物理/数值/测量算法，不扩大模型能力，不新增真实 LLM 研究运行，不把 TEST 当实际成果。

实际发布验收另在 RUNNING 中记录。

## 配置与维护工具清理

- 有效配置按职责迁移32份，移除17份重复/过期配置，新增两份来源收据；不更改冻结数值。
- 工具由76个减至5个：4个改为职责名称，1个计算窗口模块迁入 Agent，删除70个历史专用脚本。
- 同步更新正式源码、CLI 默认值、测试和安装资源目录。可选非理想构建使用全新 build_nonideal，旧构建不覆盖。
- 删除仅针对已移除实验驱动的测试，保留实际内核、测量、分配和反馈回归。
- 物理反解、M1/M2 数值公式、测量算法及判决语义保持；真实验证结果和测试数在 RUNNING 更新。

本轮验收：干净源码快照重建四个原生后端，750 passed / 10 archive skipped；本地 GUI 20 passed。实际 M1 → Handoff → M2、旧参数不可行例题、架构审计及物理关系图谱通过执行检查；保留真实 M2 FAIL/UNKNOWN。六参数和测量值与上一个共享版相同。本轮没有新增真实 LLM 调用，不声称策略性能改善。

按用户后续要求重写 PROJECT_CHARTER 为当前状态章程，原始全文本地留档；新增 CODE_MAP，逐项说明全部163个共享代码文件，并另列本地GUI/档案测试。明确旧冻结LLM修复与连续域真实反馈路径的区别。此追加修改只涉及文档和阅读指引。

## 仓库职责命名审查与迁移

2026-11-16，按用户要求审查整个仓库的阶段命名。完成21项文件迁移：非理想/噪声后端改为 `nonideal*`，相位阶跃改为 `phase_step*`，profile合同改为 `profiles.py`；旧基线工具按职责移入 allocation/studies，档案专用工具移入 _legacy；历史测试夹具使用职责文件名。

同步迁移活动导入、内部样本变量、CLI内部字段、原生构建目录和文档入口，清理已失效的Git路径规则。旧模块/命令保留薄兼容层，schema、协议/模型版本和历史证据标签保留原值。`nonideal_combined.json` 已按职责命名，保持原名及参数。

六份原分配算法、理想内核和profile数值载荷保持原字节；扩展C++仅更新首行职责说明，物理更新语句及ABI保持。新源码身份与迁移前后SHA记入 naming_migration.json，并在全新职责目录重建扩展后端。架构审计新增活动文件名与导入检查，接口回归覆盖兼容转发、旧关键字及新/旧环境变量优先级。实际验收见 RUNNING.md；未新增真实LLM研究调用。
