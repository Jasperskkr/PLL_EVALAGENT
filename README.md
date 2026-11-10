# PLLAgent：行为级联合 BlockSpec 分配研究

同步日期：**2026-11-10（Asia/Shanghai）**。本私有仓库保存可浏览的完整研究源码、配置、测试、报告和结构化实验；大型原始证据与便携交接包见 [Release 附件](https://github.com/Jasperskkr/PLL_EVALAGENT/releases/tag/project-sync-20261110)。

**新对话先读 [START_HERE.md](START_HERE.md)**；研究原始任务见 [PROJECT_CHARTER.md](PROJECT_CHARTER.md)，开发纪律见 [AGENTS.md](AGENTS.md)。

## 当前进度与分支

|入口|内容与状态|
|---|---|
|[main](https://github.com/Jasperskkr/PLL_EVALAGENT/tree/main)|原主工作树快照（含此前未提交的 Stage5、变量关系图谱）及本导航；研究状态见 [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)|
|[master](https://github.com/Jasperskkr/PLL_EVALAGENT/tree/master)|原主工作树源码及结果的独立字节快照，保留本地分支命名|
|[Stage6A](https://github.com/Jasperskkr/PLL_EVALAGENT/tree/codex/stage6a-multispec-feasibility)|独立多指标可分配性研究：4725 点 M1 扫描、真实边界 BW FAIL→修复、同小信号指标不同捕获；历史 376 项测试通过|
|[Stage6B](https://github.com/Jasperskkr/PLL_EVALAGENT/tree/codex/stage6b-sensitivity-allocation)|独立确定性多指标分配/敏感度/有限 M2 反馈：六组正式对照，10 次新完整 M2，历史 407 项回归及独立复现；[最终报告](https://github.com/Jasperskkr/PLL_EVALAGENT/blob/codex/stage6b-sensitivity-allocation/docs/stage6b/FINAL_REPORT.md)|
|[交接知识索引](docs/handoff/PACKAGE_START_HERE.md)|2026-11-09 跨阶段研究说明，算法、验证、证据、复现与已知缺口|
|[版本与逐文件 SHA](docs/github_sync/SOURCE_SNAPSHOTS.json)|三个工作树的来源、原 HEAD、发布快照、逐文件清单及覆盖范围|

**Stage6A/6B 已实际实施，分别保留，尚未合并回本地主线。** 历史报告中的“未提交”“尚未开始”等描述是当时记录；本次为各实际工作树创建了新的发布快照提交，原始工作树与历史实验未改。

当前完整 SystemSpec 认证数仍为 **0**。严格周期 PM 和 ±1µHz 频率认证保持 UNKNOWN；Jitter / Power / RUR 未支持。BW PASS、M2_PARTIAL_PASS、RESEARCH_JOINT_FEASIBLE 都不能等同于完整 Verified JointBlockSpec。Stage6B 未调用 LLM，不能宣称为 LLM 搜索收益。

## 新 LLM 对话的阅读入口

通过 GitHub 连接器授权访问本私有仓库后，可粘贴：

> 请读取 Jasperskkr/PLL_EVALAGENT 的 main 分支 START_HERE.md、PROJECT_CHARTER.md、AGENTS.md、docs/PROJECT_STATUS.md 和 docs/github_sync/SOURCE_SNAPSHOTS.json；再读取 codex/stage6a-multispec-feasibility、codex/stage6b-sensitivity-allocation 两个分支的阶段报告与源码。先概括三个研究问题、M1/Allocation/M2/Runner 边界、实际已完成的 Stage5/6A/6B 及认证缺口，再与我讨论下一步。不能仅凭 main 的旧 README 判断项目进度，不能把局部研究可行性改成完整系统 PASS。

仓库保持私有，未授权的网页访问无法读取内容。附件适合下载复现；源码、状态与结论均有可直接阅读的文本入口。

## 运行与证据

正式入口仍为 `python -m pll_allocation pipeline`；Windows 原生事件核按 `pll_allocation/verification/build_kernel.cmd` 从源码构建。精确运行命令及环境要求见各阶段报告和 [复现说明](docs/handoff/REPRODUCIBILITY.md)。输出必须写入新目录。

本次是内容同步与完整性校验，没有重跑研究 TB 或付费 LLM；以上测试数均引用已有真实验收记录。同步覆盖、Release 附件和验证命令见 [同步报告](docs/github_sync/SYNC_REPORT.md)。早期根 README 原文保存在 [ORIGINAL_README.md](docs/github_sync/ORIGINAL_README.md)。

大型 Release 附件按 32 MiB 分片传输；[下载与恢复说明](docs/github_sync/README_ASSET_TRANSFER.md) 提供 SHA256 校验和重组命令。
