# 共享研究源码整理

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
