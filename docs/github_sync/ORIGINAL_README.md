# PLLAgent 行为级联合 BlockSpec 分配

本目录是新的唯一研究主线：给定冻结 SystemSpec、固定 PLL 拓扑和 Block Space，由可替换策略联合分配五Block规格，再通过真实完整窗口行为TB验收。研究重点是LLM首次分配与有限反馈修复的质量和成本。

用户原始任务全文保存在 [PROJECT_CHARTER.md](PROJECT_CHARTER.md)，后续推进由 [AGENTS.md](AGENTS.md) 和 [决策记录](docs/DECISIONS.md)约束；阶段状态以 [PROJECT_STATUS.md](docs/PROJECT_STATUS.md)为准。

当前正式入口为Stage3A.1统一pipeline：Stage1.5 SystemSpec → 正式allocation解析/优化/真实LLM → AllocationProposal → 原M1 → 正式verification真实事件M2 → 结构化反馈。最终283项正式回归及原Track B 28项通过；真实LLM本轮先有一次JSON失败，同配置重试三次响应并完成M2。BW通过、PM/UGF与微Hz频率精度仍UNKNOWN，没有完整Verified JointBlockSpec。

Stage4新增独立相位端口与谐波探针研究，三例局部返回比数值收敛，但完整周期UGF/PM认证仍UNKNOWN；未改原协议1.1、M1、域或分配算法。当前新增后300项正式回归通过，研究证据、版本化可选Pipeline附件和限制见[测量方法](UGF_PM_MEASUREMENT_METHOD.md)、[验收报告](UGF_PM_VALIDATION_REPORT.md)。旧Stage3A.1冻结版本和发布包保留。

Stage4.1已完成10个冻结候选的局部频响与独立平滑参考相位阶跃验证，研究映射获得有限点支持；C10 BW正式FAIL，其余整体UNKNOWN，完整周期PM仍未认证。最终328项回归、原TrackB独立28项及无DLL源码重建328项通过，未改正式Agent/规格/方程。报告、可信度JSON、80条时域结果、holdout锁及复现入口见[Stage4.1报告](docs/stage4_1/M1_M2_MAPPING_VALIDATION_REPORT.md)和[运行说明](docs/stage4_1/RUN_AND_REPRODUCE.md)。

```powershell
python -m pll_allocation pipeline --strategy analytical --out experiments/my_unified_run
```

统一流程需要NumPy、SciPy及Windows原生事件核；新机器先构建`pll_allocation/verification/build_kernel.cmd`，构建目录必须不存在。当前架构/接口见[MAINLINE_ARCHITECTURE.md](MAINLINE_ARCHITECTURE.md)，本轮实测与失败见[INTEGRATION_VALIDATION.md](INTEGRATION_VALIDATION.md)，历史保留见[ARCHIVE_PLAN.md](ARCHIVE_PLAN.md)。Git冻结及轻量审查包由外部发布资产RELEASE_MANIFEST.json绑定。以下v1章节和P0/P1/P2报告保留原协议历史范围，不能与Stage1.5混用。

针对完整 SystemSpec（动态、噪声、功耗）的后续缺口与推进顺序，见 [三个核心问题审查](docs/CORE_THREE_QUESTIONS_REVIEW.md)：模块公式/联合域、LLM与敏感度/BO、可信行为评估及反馈决策。

## 首先审阅P0

- [已有工程审计](P0_EXISTING_SYSTEM_AUDIT.md)：实际目录、Git/worktree、真实联合搜索与重分配、占位接口和缺口。
- [模块复用矩阵](P0_MODULE_REUSE_MATRIX.md)：哪些直接复用、适配、参考或隔离，以及依赖。
- [目标架构](P0_TARGET_ARCHITECTURE.md)与[迁移计划](P0_MIGRATION_PLAN.md)。
- [数据继承目录](docs/DATA_INHERITANCE_CATALOG.md)：电路、MATLAB、CP/VCO表征、训练/留出角色与模型适用域。
- [接口合同](docs/INTERFACE_CONTRACT.md)：Agent/Policy、Simulator、Verifier、JSON信封和预留边界。

审计清单覆盖11个实际工程、2425份源文件指纹；97/97历史来源引用SHA匹配。24份纠正后MATLAB记录原SHA匹配，96份小型参考数据字节继承。旧工程没有迁移、删除或改写。

## 原v1兼容入口

在本目录运行；Python≥3.11，生产流程不需要额外依赖。测试需pytest。

```powershell
python -B -m pll_allocation run --problem examples/regular80.json --policy rule --out outputs/my_run --budget 30
python -B -m pll_allocation run --problem examples/regular80.json --policy feedback --out outputs/my_feedback --budget 3
python -B -m pll_allocation suite --out outputs/my_comparison --budget 30 --policies rule grid random feedback
python -B -m pytest -q -p no:cacheprovider
```

输出目录必须不存在。运行保存首次与最终候选、完整周期轨迹、预测与测量、逐轮违例、预算、SHA链和报告。可选 `python -m pip install -e .` 安装入口 `pll-allocation`；核心运行不读取旧工程。

真实LLM使用显式环境配置；`configs/llm_env.json`只保存变量名和限额，不含密钥：

```powershell
python -B -m pll_allocation run --problem examples/regular80.json --policy llm_initial --out outputs/my_llm_first
python -B -m pll_allocation run --problem examples/tight80.json --policy llm_feedback --out outputs/my_llm_repair --budget 3
```

llm_initial严格一次提议/一次评价；llm_feedback可读取真实违例后有限修复。配置缺失、网络失败、返回不合法会明确失败，不切换到规则候选。`replay --replay <proposal.json>`仅回放已有完整提议，标记不是新LLM调用。

## 原v1冻结模型和历史结果

直接提取原Python周期电荷、精确两状态RC与线性VCO内核；不重写MATLAB模型。80MHz运行400周期，84MHz运行420周期，观察时长40µs，尾50周期测量。CP电流/q0、LF Rz、VCO f0/Kvco在声明域联合选择；PFD/Divider及其余参数显式固定。

常规80MHz、0.19°收紧80MHz、84MHz联合目标均已通过。反馈基线真实经历相位0.27009° FAIL → 新联合规格 → 0.19644° PASS。0.1°离散域没有可行点；抖动缺模型返回UNSUPPORTED。频域BW/PM、噪声、抖动、真实电路能力仍待相应验证器，不能从现有结果推断。

正式结果见 [端到端验收](END_TO_END_ACCEPTANCE.md)、[策略对照](POLICY_COMPARISON_REPORT.md)和 [机器可读验收](docs/validation/acceptance.json)。93项测试通过，包含24组完整9600周期MATLAB历史轨迹对照。测试中断/异常数据仅用于错误路径，不作为正式LLM或行为实验。

## 目录

```text
PROJECT_CHARTER.md / AGENTS.md        原始任务与长期开发纪律
P0_*.md                             四份审计产物
pll_allocation/                     唯一运行包：合同、策略、TB适配、Runner、CLI
  _legacy/                          有来源SHA的原字节行为内核
examples/                           原80MHz、非零q0/收紧/域内未找到、84MHz、未支持指标
configs/                            LLM环境变量配置
data/legacy/                        模型锚点、冻结旧配置、数值回归定义
data/verification_reference/        仅验证侧历史MATLAB记录和轨迹
tests/                              合同、真实TB、Runner、外部进程和回归
tools/                              来源审计、提取、数据生成和交付核查
docs/                               接口/数据目录/状态/审计指纹/测试证据
outputs/                            不覆盖的逐运行结果（忽略Git）
```

下一阶段先接通可稳定返回的LLM端点，用同一输入/后端/预算完成首次与修复策略验收，再增加多seed、多SystemSpec实验和更强的非LLM搜索；MATLAB实机后端按既定JSON/Protocol接口接入并回归。当前外部命令桥已通过真实子进程TB测试，MATLAB许可证及桥接函数尚未执行验收。
