# PLLAgent 行为级联合 BlockSpec 分配

本目录是新的唯一研究主线：给定冻结 SystemSpec、固定 PLL 拓扑和 Block Space，由可替换策略联合分配五Block规格，再通过真实完整窗口行为TB验收。研究重点是LLM首次分配与有限反馈修复的质量和成本。

用户原始任务全文保存在 [PROJECT_CHARTER.md](PROJECT_CHARTER.md)，后续推进由 [AGENTS.md](AGENTS.md) 和 [决策记录](docs/DECISIONS.md)约束；阶段状态以 [PROJECT_STATUS.md](docs/PROJECT_STATUS.md)为准。

当前：P0审计和P1/P2最小可运行链已完成；确定性策略与多规格实验可执行；真实LLM服务两次读取超时，尚未完成LLM策略验收。所有PASS仅属于声明行为模型。

针对完整 SystemSpec（动态、噪声、功耗）的后续缺口与推进顺序，见 [三个核心问题审查](docs/CORE_THREE_QUESTIONS_REVIEW.md)：模块公式/联合域、LLM与敏感度/BO、可信行为评估及反馈决策。

## 首先审阅P0

- [已有工程审计](P0_EXISTING_SYSTEM_AUDIT.md)：实际目录、Git/worktree、真实联合搜索与重分配、占位接口和缺口。
- [模块复用矩阵](P0_MODULE_REUSE_MATRIX.md)：哪些直接复用、适配、参考或隔离，以及依赖。
- [目标架构](P0_TARGET_ARCHITECTURE.md)与[迁移计划](P0_MIGRATION_PLAN.md)。
- [数据继承目录](docs/DATA_INHERITANCE_CATALOG.md)：电路、MATLAB、CP/VCO表征、训练/留出角色与模型适用域。
- [接口合同](docs/INTERFACE_CONTRACT.md)：Agent/Policy、Simulator、Verifier、JSON信封和预留边界。

审计清单覆盖11个实际工程、2425份源文件指纹；97/97历史来源引用SHA匹配。24份纠正后MATLAB记录原SHA匹配，96份小型参考数据字节继承。旧工程没有迁移、删除或改写。

## 运行

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

## 当前模型和结果

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
