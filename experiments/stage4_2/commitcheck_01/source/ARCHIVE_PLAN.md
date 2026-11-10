# Stage 3A.1 历史保留与后续归档计划

本轮不删除目录、轨迹、嵌套Git或外部ZIP。静态审计、运行时import blocker及无历史目录的重新编译回归已证明正式依赖独立。归档须经Leader审查，本轮不自动执行。

|内容|本轮状态|后续处理及保留原因|
|---|---|---|
|track_a的core/physics/allocate/agent/repair/feedback_agent|allocation已正式替代，旧路径只转发|保留轻量别名兼容旧脚本；原件由父Commit/SHA/备份追溯|
|track_a的runner/benchmark/report/audit/experiments/CLI及configs/track_a|历史工具，Pipeline不导入|未来可独立归档；原Track A回归仍覆盖，不能直接删|
|track_b源码/.git/branch/outputs|只读，HEAD dc661f6f7694562444438410f39190571b51a398|可校验后归档离线介质；独立研究版本/原测试/原实验须保留，本轮不合并或删.git|
|根outputs的Stage1/1.5/Track A/Legacy记录|未改，正式测试不再要求该目录|保留原实验/审计/校准/失败证据，未来整组归档并留SHA索引|
|Stage3A/3A.1 experiments/raw|本地保留，与代码分离|可另行压缩和列SHA；小型候选/M1/M2/trace/成本入正式Commit|
|旧v1 runner/policies/behavioral/_legacy及examples/data|Legacy兼容和原回归|不能直接删；283项包含原93项/24组MATLAB参考，新核不能覆盖旧协议|
|tests/fixtures/verification及data小型参考|正式回归只读夹具|必须保留，只用于显式对照，不作运行计算真值|
|pipeline_stage3a及绑定模型/协议|唯一正式输入|必须保留，新版本必须显式换版本及Hash|
|pre_migration/working_tree_backup.zip|本地重要未提交工作备份|Leader审查及备份确认前不删；不入轻量包|
|两份原已删除ZIP、docs/track_a.zip、docs/stage3a.zip、stage3a_source_review.zip|保持初始状态，不提交|已有/可能外部改动，不恢复、不删、不覆盖|
|verification/build及隔离source/build/tmp|可再生构建/测试缓存|Leader确认后可清理明确目录；核源码、构建日志、identity、测试报告保留|

结构变化仅为实现所有权、资源路径、兼容别名、构建拒绝覆盖、审计、字节发布与记录。冻结模型/算法/协议未升级，没有完整Behavioral PASS。

下一阶段三个问题分别还缺：

1. Block Space/物理映射：误差、可信域、非理想/噪声/功耗联合模型与校准证据；当前六参理想域不是电路实现能力。
2. 搜索/Agent：真实M2失败后LLM自主修复、稳定合法输出、多seed/多目标同预算比较。解析/敏感度/SLSQP已有，本例LLM未证明数值增益。
3. 行为评估/反馈：独立PM/UGF与严格频率认证、跨初态/扰动/域可靠性、噪声/抖动/功耗测量及可行动反馈。BO/新模型另需Leader授权。
