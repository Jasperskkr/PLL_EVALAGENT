# Stage 7–10 开发前检查与本轮约束

日期：2026-11-10（Asia/Shanghai）。本次完成开发前审查和回归，尚未开始 Stage 7–10 功能实现。

## 工作区与 Git 基线

| 项目 | 实际检查结果 |
|---|---|
| 唯一工作区 | `F:/LJP/概伦AI/PLL_allocation` |
| 对应项目 | `https://github.com/Jasperskkr/PLL_EVALAGENT.git` |
| 当前分支 | `master` |
| HEAD | `e395f24859cdd81e3deb5ea83ba3f9598a27cd16` |
| 原有未提交修改 | `docs/physics_mapping_stage1.zip`、`docs/stage1_5.zip` 的未暂存删除 |
| 开发前指纹 | 14,868 个 Git 跟踪条目；原有缺失条目同样记录 |

原始审计保存在 `experiments/stage7_10_development_20261110_01/baseline_inventory.json`。仅记录 LLM 环境变量是否存在，未保存令牌值。模型、服务地址、令牌三个既有配置项均存在；这不代表服务可用性或本轮真实调用已验收。

本轮不创建各阶段分支、Worktree 或工程副本，不执行 reset/clean/强制覆盖/未经确认的合并，不自动 Push。后续各阶段继续在同一 F 盘工作区顺序推进；阶段验收后才考虑本地检查点提交。既有两个 ZIP 的删除保持原状。

## 已核查的复用位置

已阅读 `PROJECT_CHARTER.md`、`docs/PROJECT_STATUS.md`、P0 四份报告、D022/D023 和 `docs/research/ALLOCATION_STRATEGY_SCOPE.md`。早期 P0 的入口描述已由后续决策收敛；当前唯一正式入口是 `python -m pll_allocation pipeline`。

| 能力 | 当前正式实现 | 接入约束 |
|---|---|---|
| 总入口与单候选完整验证 | `pll_allocation/pipeline.py::run_pipeline` | 保留输入/版本绑定、候选先落盘、独立约束检查、预算和 M2 判决 |
| Stage 6B 多指标运行 | `pll_allocation/pipeline.py::run_multispec` | 现有 A/B/C 经同一 `run_pipeline` 执行完整 M2；新 Policy 接入这一边界 |
| 确定性多指标搜索 | `pll_allocation/allocation/multispec_search.py::SearchController` | 保留历史 A/B/C 定义和结果，不把其候选重标成 LLM 决策 |
| 研究约束判决 | `pll_allocation/allocation/multispec_constraints.py` | 保留 M2 BW/条件捕获和 M1 名义 PM/调谐各自来源 |
| M1 公式与域 | `pll_allocation/physics_mapping/`、`pll_allocation/block_space/` | 固定既有模型、17 输入、6 自由变量及有效域 |
| M2 与协议 | `pll_allocation/verification/`、`configs/verification/protocol_v1_1.json` | 复用完整行为级 TB；UNKNOWN/异常/超域不得判 PASS |
| 已有真实 LLM 工具决策 | `pll_allocation/allocation/agent.py::MessagesPolicy` | 当前是工具辅助首发，使用既有隔离 HTTP transport 和请求成本记录 |
| 策略接口与修复缺口 | `pll_allocation/allocation/__init__.py::AllocationStrategyPolicy` | 真实 LLM 历史反馈分支仍返回 `REAL_LLM_REPAIR_NOT_IMPLEMENTED` |
| Stage 6B 冻结问题 | `configs/stage6b/B1.json`、`B2.json` | 不覆盖或放宽原规格；新实验写新目录 |

新增 `agent/` 若确有需要，仅负责规划、策略接口与反馈解释。验证、约束、预算、缓存和最终判决仍由现有 Runner 控制。GUI 调用同一正式后端，不复制 M1/M2、优化器或验收公式。

## 本次实际回归

工作目录显式为 F 盘项目，`TMP`、`TEMP`、pytest 临时目录和 XML 均设在本轮 F 盘新实验目录。实际命令：

```powershell
$env:TMP = 'F:\LJP\概伦AI\PLL_allocation\experiments\stage7_10_development_20261110_01\tmp'
$env:TEMP = $env:TMP
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest -q --basetemp=experiments/stage7_10_development_20261110_01/baseline_pytest_tmp --junitxml=experiments/stage7_10_development_20261110_01/baseline_tests.xml
```

结果：**478 passed in 43.76s**，退出码 0。这是本轮重新执行，非引用历史测试成绩。轻量 XML 副本位于本目录 `BASELINE_TESTS.xml`。测试中的验证器活动归入测试成本，本轮没有启动新的研究 arm 或真实 LLM 网络请求。

## Stage 7–10 功能范围待明确

本轮用户给出了开发、Git、证据和最终验收约束，未给出各阶段具体功能清单、GUI 交互要求或正式实验方案。仓库历史 D019 中的 Stage 7 后来由 D020 更名为 Stage 6C，不能直接作为本轮新 Stage 7 的功能合同。

已向用户提出以下可选顺序，当前仅为建议，未作为已批准方案实施：

1. Stage 7：在既有多指标 Runner 接入真实 LLM 首次完整联合分配。
2. Stage 8：真实 LLM 消费结构化验证反馈并提交完整修复候选，独立复验。
3. Stage 9：冻结等预算实验和配对消融，保留请求失败、全部 M1/M2 与成本。
4. Stage 10：调用同一正式后端的 GUI，演示并提交完整 Diff、测试和实验对照，待用户最终验收。

无论采用何种阶段划分，都须先保存阶段方案再实施；首次候选必须在首次 TB 前写盘；回放、mock、确定性搜索不得冒充真实 LLM 成果。最终 GitHub 推送需要用户新的明确最终验收批准，历史同步授权不延续为本轮推送授权。
