# 新对话阅读顺序

1. 读取 [README.md](README.md)、[原始任务](PROJECT_CHARTER.md)、[开发约束](AGENTS.md)。
2. 读取 [版本来源与发布覆盖](docs/github_sync/SOURCE_SNAPSHOTS.json)、[主线状态](docs/PROJECT_STATUS.md) 和 [决策记录](docs/DECISIONS.md)。
3. 阅读 [研究知识总览](docs/handoff/PACKAGE_START_HERE.md)、[核心算法](docs/handoff/CORE_ALGORITHMS.md)、[行为模型与验证](docs/handoff/BEHAVIORAL_MODEL_AND_VERIFIER.md)、[当前缺口](docs/handoff/CURRENT_STATUS_AND_RESEARCH_GAPS.md)。这些文档保留交接包语义；其中 repo/、source_variants/ 路径在 Release 包中，在线源码对应下面两个分支。
4. 查看 [Stage6A docs](https://github.com/Jasperskkr/PLL_EVALAGENT/tree/codex/stage6a-multispec-feasibility/docs/stage6a) 和 [Stage6B 最终报告](https://github.com/Jasperskkr/PLL_EVALAGENT/blob/codex/stage6b-sensitivity-allocation/docs/stage6b/FINAL_REPORT.md)，再读该分支的 allocation/multispec_constraints.py、allocation/multispec_search.py 与 pipeline.py。
5. 用各阶段结构化实验、manifest、trace 和真实原生请求核对结论；[Release](https://github.com/Jasperskkr/PLL_EVALAGENT/releases/tag/project-sync-20261110) 提供大型材料。

固定拓扑为 10MHz × 8 电荷泵 PLL，六个自由轴为 Icp、Rz、C1、C2、f0、Kvco。M1 是连续理想锁定点预测；M2 是独立原生事件 TB；Allocation 提议候选；Runner 冻结输入并控制预算和验收。

完整认证仍为零：周期 PM、±1µHz 频率 UNKNOWN；Jitter/Power/RUR 不支持。Stage6B 为已运行的确定性研究，不是未来计划，也不是已证明的 LLM 增益。原主线和两个扩展以独立分支保留，不隐式合并。
