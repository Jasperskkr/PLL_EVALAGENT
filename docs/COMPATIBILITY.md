# 名称迁移、兼容与来源合同

主阅读路径按职责命名。核心物理公式、原反解/数值求解、测量算法和判决语义保持原实现。

|旧称|新路径/概念|
|---|---|
|Stage7|exploration：物理探索/PhysicsContext|
|Stage8A|region_explorer：预算化工具执行|
|Stage8B|agent：真实决策闭环|
|Stage9 / agent/stage9.py|agent/feedback.py → run_feedback|
|verification/research.py|verification/continuous.py|
|Track A / Track B|allocation / verification|
|阶段化例题/配置|configs/problems、agent、providers|
|A+ / 多区域 / 消融编排|studies/initial_allocation、multi_region、ablation|

旧导入仅转发同一实现，旧 run_stage9_feedback 参数保持可用。没有另写一套反馈算法。

|推荐 CLI|旧别名继续支持|
|---|---|
|--problem|--initial-allocation-problem|
|--allocator-config|--initial-allocation-config|
|--initial-context|--initial-allocation-context|
|--feedback-input|--initial-allocation-feedback|
|--handoff|--stage9-handoff|
|--verification-problem|--stage9-problem|
|--verification-config|--stage9-config|

新结果名为 verification_handoff.json、verification_result.json、cost_summary.json、feedback_report.md；相应旧文件名仍输出，已有本地 GUI/脚本继续工作。序列化 schema、ready_for_stage9 等键、来源标签和模型版本不做全局文字替换；交接优先查看 gate_status。

冻结配置、可选非理想内核及身份锁仍有少量旧路径/ID，例如 configs/stage6*、verification/stage6c*、track_a 兼容模块。它们不在新的主阅读路径；盲目删除或改写会破坏来源锁和旧回归。后续彻底迁移应单独升级合同版本并验证。

configs/provenance 保存原实现 SHA 和物理关系绑定。data/behavioral_space_v1/reference 仅保留参考数值代码与来源合同，供独立回归；这些不是新实验数据。

`data/legacy` 只保留旧内核来源清单、输入模型及小型 MATLAB 锚点，`tests/fixtures` 保存合同/判决回归输入。它们是明确标注的历史测试夹具，不是本次运行产生的成果；大型轨迹和实验目录均不发布。

此次精简通过普通快进提交完成：最新版目录移除实验数据、冗余文档、GUI 和构建产物，本地历史不删除，Git 历史不改写。历史对象仍可在旧提交找到；浅克隆或下载源码仅获取最新版工作目录。
