# 实际复用报告

完整模块决策见P0_MODULE_REUSE_MATRIX.md，数据来源见docs/DATA_INHERITANCE_CATALOG.md。

实际原字节提取10份：PythonBehavioralEvaluator、cp.py、lf.py、schemas.py、units.py，以及公共models.json、三份冻结配置和独立MATLAB差异报告。原绝对路径、目标路径、SHA及复制方式在data/legacy/legacy_manifest.json。24例数值合同通过AST从旧验证测试提取，保留源文件SHA；另核对24份原record冻结SHA，继承96份只供验证的记录/CSV/语义文件。

实际适配：原CP/LF候选域、84MHz五轴CP/LF/VCO声明域、q0和VCO目标语义、40us/tail50/hold20协议、约束与多规格对照。没有复制旧整体搜索执行器，是为了避免它附带的证据购买、sizing和历史release依赖；原联合候选空间与积分公式均沿用，并在新合同下重新运行。

架构参考：AgentV2的控制器注入、有限反馈策略、source/trace/预算边界；M05的Guard/Executor/Runner职责；AgentV2命令后端的argv/独立目录/日志模式。LLM transport为新分配任务实现，未把Problem1 Formulator当作JointBlockSpec Allocator。

隔离：M06校准与模型发布、M07物理证据、G1/G1.1数值诊断、旧sizing与independent-system stub。全部原地保留，不成为新运行依赖。FactorGraph MATLAB采用另一套平均相位模型及参数，明确只参考架构，不混用数值。

旧源码保护：docs/audit/source_inventory_after.json比较2425个已审计源文件，无变化或丢失；97/97来源引用仍匹配。未声称对所有大型历史RAW逐字节重哈希。
