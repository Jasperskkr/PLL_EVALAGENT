# Stage 7 PhysicsExplorationReport

2026-11-10。Stage7实现与本地验收已完成，等待用户审阅；未启动Stage8。当前工作区仍为 `F:/LJP/概伦AI/PLL_allocation`，master/HEAD `e395f24859cdd81e3deb5ea83ba3f9598a27cd16` 未移动；本轮改动未Commit，未Push/Merge/Reset/Clean，未创建分支、Worktree或工程副本。

## 交付结果

实现了用户可修改的 `ResearchProblemV2` → 连续物理初筛 → 固定Seed Sobol及物理种子 → 原正式M1 → 可行样本/代表点/区域建议 → 六轴敏感度 → PhysicsContext。唯一正式入口新增显式 `pipeline --explore-problem`；GUI和下一阶段可调用同一Python接口。

完整Baseline Audit见 [BASELINE_AUDIT.md](BASELINE_AUDIT.md)，配置、设计边界、运行与Stage8接口见 [INTERFACE_AND_REPRODUCE.md](INTERFACE_AND_REPRODUCE.md)。本轮没有新增第二套M1公式、优化器或M2；直接复用原 `evaluate`、`inverse_at_shape`、`raw_prediction` 和 `pm_ceiling`。新源文件/复用源的指纹随每次运行保存。

最终权威运行在 `experiments/stage7_exploration_20261110_03/`，此前 `_01`、`_02` 是保留的开发验收，不能当作独立统计样本或隐藏成本。固定Seed复验也只算复验成本。

## 实际探索对照

所有正常探索使用256个Sobol样本、16个物理种子，正式M1预算320，代数预算512；敏感度最多3个代表点，预算与探索共用。每条M1调用均执行原默认8000点频率扫描，而非仅用代数根代替。下表可行点只指启用且受支持的M1 BW/PM约束，LockTime和Jitter均未评价通过。

| 最终运行 | 实际结论 | 探索M1可行点 | 区域 | 正式M1调用 | 代数调用 |
|---|---|---:|---:|---:|---:|
| global | M1_FEASIBLE_SAMPLES_FOUND | 24 | 3 | 151 | 166 |
| tight | M1_FEASIBLE_SAMPLES_FOUND | 2 | 2 | 85 | 100 |
| impossible | PROVEN_M1_INFEASIBLE | 0 | 0 | 0 | 0 |
| reproducibility | 与global样本逐字节相同 | 24 | 3 | 151 | 166 |
| budget_one | 默认点M1可行；其余预算不足保留 | 1 | 1 | 1 | 16 |
| numerical_failure | 正式M1数值失败，未找到可行样本 | 0 | 0 | 1 | 1 |
| not_found | 未找到可行样本，无不可行证书 | 0 | 0 | 1 | 1 |

完整机器可读成本、wall/CPU和科学摘要见 [EXPERIMENT_COMPARISON.json](EXPERIMENT_COMPARISON.json)。全局与收紧问题的紧凑代表证据分别在 [GLOBAL_EVIDENCE.json](GLOBAL_EVIDENCE.json)、[TIGHT_EVIDENCE.json](TIGHT_EVIDENCE.json)。全量样本和可直接读取的PhysicsContext保存在权威运行目录，各文件名见接口文档。

global六轴范围：Icp20–400µA，Rz500–15000Ω，C1 20–300pF，C2 0.2–4nF，f0 40–79MHz，Kvco5–80MHz/V；目标BW150–300kHz、PM≥50°。global共308提议（含36敏感度扰动），306个精确不同候选，2重复引用，155个初筛拒绝；151正式M1，24探索可行点。非枚举电容既在Sobol中连续采样，也用于敏感度扰动。

tight明确修改全部六个范围：Icp40–250µA，Rz1800–9000Ω，C1 30–150pF，C2 0.6–3nF，f0 55–77MHz，Kvco12–50MHz/V；目标BW290–300kHz、PM≥70°。296提议、211初筛拒绝、85正式M1；两个代表点BW均约295000Hz，PM分别73.969672901°和70.675951511°。证明用户配置变化真正影响候选与判决，未改Stage6B冻结门限。

global第一代表点的BW约225000Hz、PM81.731722108°，其高相位裕度来自用户新声明连续域的更大电容比，不能升级为旧Stage6B域或电路能力。其归一化BW敏感度（列为Icp/Rz/C1/C2/f0/Kvco）约为 `[8.798292, 9.774838, 0.431271, -0.667852, 0, 8.142873]`。这些矩阵用各参数范围归一化，故Icp/Kvco列数值不必相等；其共同环路增益作用由log elasticity描述。全部三个global、两个tight代表点的六列敏感度均OK，所有扰动Evidence IDs可追溯。

impossible把PM下限设为95°，严格超过给定域理想LF的全域相位必要上界，因而在M1假设下出证书，不消耗M1。not_found只评价默认点并把BW设为1–2GHz，因此只报未找到。numerical_failure使用极小正Icp，快速代数及原正式M1均发生可追踪数值失败，保留成本、reason和UNKNOWN，不用快速预测或其他样本替代通过。

budget_one正式M1只调用1次，随后124个候选明确记为 `NOT_EVALUATED_M1_BUDGET_EXHAUSTED`，6列敏感度为受限且矩阵空值；程序没有额外评价来填矩阵。invalid_input把C1最小值设为0，CLI返回2、输出原因，未创建运行目录。

## 可复现性与成本

global/reproducibility的完整 `m1_samples.jsonl` 逐字节一致，科学摘要SHA相同；运行耗时不要求相同。所有7个最终PhysicsContext通过公开loader的自身digest、模型和引用证据校验；所有正式M1次数均未超过配置上限。详细SHA见每个result和最终回执。

最终 `_03` 运行总计 **390正式M1 / 450代数调用 / 0研究M2 / 0LLM**，包含151次M1的独立复验成本。开发 `_01` 为236M1/266代数、`_02` 为390M1/450代数，全部保留；三轮合计1016M1/1166代数。测试内计算另列，不混入研究样本；完整旧回归包含原有M2测试，这是回归活动，不是Stage7探索路径调用M2，也不是新的研究验证成绩。

## 验收测试与保护

最终实际命令见 [RUN_COMMANDS.md](RUN_COMMANDS.md)。完整回归 **513 passed in 48.30s**，0失败、0错误、0跳过：原478项全部保留通过，新增35项Stage7测试。原Stage6B多指标测试28项通过。证据：[TESTS_FINAL.xml](TESTS_FINAL.xml)、[TEST_SUMMARY.json](TEST_SUMMARY.json)。此前30项新增测试首轮/二轮以及513项中间全回归也保留，未覆盖记录。

新增测试覆盖原M1典型工作点不变、非枚举连续C、Spec启用/改界/来源、改变N/f_ref的数学M1、PM必要条件、调谐证书、非法单位/参数/固定项、已知可行/不可行与未找到区分、数值失败、精确去重、固定Seed、预算、六轴敏感度、产物绑定与禁止覆盖，以及唯一pipeline路由。刻意无效/失败案例均按预期被识别，不代表测试失败。

开发前14,868个Git跟踪条目的保护核验只允许本轮pipeline入口与README/DECISIONS/PROJECT_STATUS变更；正式M1、M2、Stage6B合同/代码、原SLSQP/Sensitivity、配置和Git跟踪的历史证据字节保持。原有两ZIP未暂存删除仍保持；D024/预检文档保留。此前未跟踪历史实验未逐文件纳入该Git指纹声明，本轮所有实验、临时目录和新输出限定在新Stage7目录，未对旧实验执行写入或清理。最终精确指纹、Diff、清单与保护结果见本目录 `FINAL_RECEIPT.json` 和其指向的本地审计文件。

## 修改清单与剩余边界

新增 `pll_allocation/exploration/__init__.py`、`contracts.py`、`engine.py`、`regions.py`；新增三个 `configs/stage7/*.json`、`tests/test_stage7_exploration.py` 和本目录文档/轻量证据。修改原 `pipeline.py` 仅新增显式参数与路由；README、D025及状态追加说明。完整当前清单见 `CHANGE_MANIFEST.json`，本轮Diff包括新增文件，未把之前两份ZIP删除或D024记作本次功能变化。

尚不提供：整个区域认证、全局可行域证明、最优性或可行体积估计、周期PM、捕获/LockTime、Jitter/功耗、晶体管实现保证、Stage8 Agent或GUI。宽连续域只有原理想M1数学评价，未新增实验校准。启用的LockTime/Jitter仍UNKNOWN；所有输出 `FULL_SYSTEMSPEC_CERTIFIED=false`。这些是明确的研究能力边界，不是被隐藏的通过项。

Stage7已在此停止，等待用户验收；没有自动启动Stage8或推送GitHub。
