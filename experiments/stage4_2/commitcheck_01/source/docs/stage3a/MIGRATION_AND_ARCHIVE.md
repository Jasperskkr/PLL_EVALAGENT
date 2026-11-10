# Stage 3A 迁移审计、保留与下一阶段

先审查源码再提取；原路径、SHA、目标路径、适用域及语义见reuse_manifest.json（初次提取）和最终审计的reuse_manifest_final.json。核心结论不以ZIP名字或历史报告代替真实源码阅读。

## 与旧结构相比

- 原v1入口仍可复现旧周期电荷协议，新正式pipeline明确使用Stage1.5合同；不把80/84MHz旧域隐式塞进新频响协议。
- Track A原地复用，仅增加allocation策略边界。其run_first仍是历史M1-only入口，正式pipeline直接调用算法和Agent，不嵌套调用旧Runner，不重新实现公式。
- Track B正式运行闭包进入verification；顶层脚本导入改相对导入，配置从唯一configs读取；研究套件和报告生成器未搬入正式包。
- 不复制Track B baseline模型作为正式第二来源；正式SystemSpec文件与原模型嵌入快照按内容hash核对。原公式、参数域、原SystemSpec及draft=true全部保留。
- 原Track B convergence后处理隐式读取1.0的三项门限，提取后显式使用同次完整1.1文档；三项门限数值逐项相同，真实回归数值完全一致。捕获定义、BW二分宽度、扫描网格/幅度/步长/窗口未改。
- 本机DLL与kernel.cpp逐字节复用并双向绑定；正式包不借用track_b/build，未引入ngspice/PDK/MOS/sizing或物理证据资格链。
- 新实验在experiments，raw原始轨迹与代码及精简报告分离，拒绝覆盖。旧outputs和track_b/outputs原地保留。

## 保留、可归档及暂不能删除

|对象|建议|原因|
|---|---|---|
|track_b研究源码、嵌套.git、outputs、baseline|冻结后可整体归档；当前不能删除|原关键测试与独立来源复核仍读取它；含12点BW、37组捕获及协议修订证据|
|track_b.zip / docs/track_a.zip|可作为历史发布包另存并校验SHA|不是正式运行依赖；不是可替代原始运行证据的充分材料|
|Track A benchmark、反馈模拟、历史LLM outputs|可移交离线归档，当前不删|保留分配来源、非独立样本说明、真实LLM原始请求和失败成本|
|pll_allocation/track_a|继续维护，不归档删除|正式allocation仍直接调用它；其命名是来源身份，并非独立长期子项目|
|旧v1 runner/policies/_legacy/data验证参考|保留兼容、隔离使用|原全部回归和24组MATLAB历史轨迹仍依赖；本轮不重构删除|
|Stage1/1.5 configs、physics_mapping、block_space及冻结报告|不可删除|正式单一输入、公式、域和版本证据|
|verification/build|可重建的本地构建缓存|本机二进制SHA及来源由阶段审计保留；新机器须构建|
|experiments/.../raw|可外置归档，需连同hash索引保留|本次真实M2轨迹、逐点请求与失败证据；不能仅保留summary冒充完整溯源|
|历史两份ZIP删除|本轮不修复、不归因于本轮|本轮开始前父git已有删除；Track B已有只读恢复副本，初始git状态单独保存|

没有执行任何历史目录迁移、删除、git合并或提交。父分支和Track B独立仓库保持原身份。将来删研发目录前须先独立迁移旧测试/证据引用并确认归档可读；不属于本阶段授权范围。

## 三个核心问题的实际缺口

|问题|本阶段已有闭合|下一阶段仍缺|
|---|---|---|
|Block Space与物理映射|原Stage1.5域、M1公式、解析反解与版本绑定；真实M1/M2偏差可追溯|独立PM/UGF测量、模型误差可信域；噪声/抖动/功耗的模块模型与测量协议；声明目标不是电路能力|
|Agent搜索与反馈决策|解析/优化/真实LLM首发共用Runner；真实M2反馈接收；已有确定性repair实际FAIL后复验|真实LLM反馈决策/修复与复验；多目标多seed公平比较及Agent相对工具的独立增益；没有新学习算法/BO|
|可信行为评估与反馈|成对捕获、四组频响、BW及收敛包络、失败成本、结构化回传|PM独立认证、微Hz频率精度、边沿专用BW观测等价性、近轨/全域可靠性、噪声和功耗；完整Verified JointBlockSpec仍不能签发|

Stage3A是工程收敛验收，不升级历史P3/P4整体研究完成状态。真实LLM本轮已获得首发候选并完成M2，不能据单案例宣称统计增益或真实LLM修复成功率。完成本阶段报告后停止，等待技术Leader审查。
