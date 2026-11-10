# 新对话阅读顺序

当前统一实现已从Stage6A/B独立研究树归并到F盘主线，同时包含显式可选Stage6C。远端main和master同步后使用同一正式源码，历史阶段分支用于溯源。

1. 先读README.md、AGENTS.md、PROJECT_CHARTER.md和docs/PROJECT_STATUS.md；最新范围以docs/DECISIONS.md的D022/D023及docs/research/ALLOCATION_STRATEGY_SCOPE.md为准。
2. 正式入口只有python -m pll_allocation pipeline。M1在physics_mapping，分配/Agent在allocation，M2在verification，Runner控制完整检查、预算、独立判决与trace。
3. Stage6A能力与竞争分析见docs/stage6a；Stage6B确定性多指标/反馈搜索见docs/stage6b/FINAL_REPORT.md和ARCHITECTURE_AND_ALGORITHM.md；可选Stage6C见docs/stage6c/FINAL_RESEARCH_REPORT.md。旧报告“未合并”是当时状态，当前归并验收见docs/mainline_integration_20261110_01/FINAL_REPORT.md。
4. 当前研究聚焦固定可测spec下的Agent首次完整联合分配，以及验证反馈对有限预算修复的价值。真实LLM工具首发已接入，真实LLM反馈修复和多指标LLM Policy尚未完成；确定性A/B/C成果不等于LLM增益。
5. M2 BW/指定条件捕获与M1名义PM/调谐按来源分别判决；严格周期PM、微Hz频率完整认证等仍UNKNOWN，完整SystemSpec认证不得升级为PASS。Stage6C研究性噪声能力及其边界按专门报告解释。
6. 仅在F:/LJP/概伦AI/PLL_allocation开发、构建与运行；不在C盘创建工作区。旧C盘原始数据已获授权清理，历史路径可用性见docs/mainline_integration_20261110_01/EVIDENCE_INDEX.md。

此前docs/handoff、docs/github_sync/SOURCE_SNAPSHOTS.json、历史分支和Release是旧同步/交接证据，不能替代最新统一主线状态。此次同步过程见docs/github_sync/MAINLINE_SYNC_20261110.md。不要将回放、mock、旧原始记录或确定性修复描述成新LLM实验。
