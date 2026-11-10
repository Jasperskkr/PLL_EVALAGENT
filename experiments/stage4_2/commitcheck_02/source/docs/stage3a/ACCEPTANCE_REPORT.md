# Stage 3A 集成验收报告

2026-11-04。工程集成完成，等待技术Leader审查。冻结的模型、域、SystemSpec与测量协议保持；当前没有完整Behavioral PASS或Verified JointBlockSpec。

## 交付和真实结果

先完成[集成审计与方案](INTEGRATION_AUDIT_AND_PLAN.md)，再建立[统一架构及接口](ARCHITECTURE_AND_INTERFACE.md)。正式入口：

```powershell
python -m pll_allocation pipeline --strategy analytical --out experiments/new_run
```

以下均为新执行的真实M2，不是mock或历史回放测量。单位BW为kHz。

|策略/阶段|M1 BW|M2 BW|M2相对偏差|BW判决|原M2整体|原生调用|
|---|---:|---:|---:|---|---|---:|
|解析 FIRST_SHOT|225.000000|226.403934|+0.623971%|PASS|UNKNOWN|106|
|优化 FIRST_SHOT|204.356651|205.385568|+0.503491%|PASS|UNKNOWN|106|
|真实LLM FIRST_SHOT|225.000000|226.403934|+0.623971%|PASS|UNKNOWN|106|
|随机 FIRST_SHOT|709.216566|713.783792|+0.643982%|FAIL|FAIL|114|
|原确定性repair FEEDBACK_REPAIR|204.356651|205.385568|+0.503491%|PASS|UNKNOWN|106|
|原Track A候选显式复验|225.000000|226.403934|+0.623971%|PASS|UNKNOWN|106|

五组主实验共六次完整M2、644次原生事件仿真。每个候选均执行双步长冷启动捕获与四组频响扫描，记录真实点数、积分点数、耗时与失败成本；不存在隐形M2预测替代。所有运行完整源身份、协议、依赖、首次候选、M1/M2、偏差、Agent决策和反馈记录均在experiments的对应目录；全部raw文件hash见最终审计索引。

实际解析/优化单轮总耗时约10.09s/12.99s，LLM轮48.32s，确定性修复两次验证22.15s，既有候选复验9.88s。耗时是单次实测，部分运行并发，不作为策略速度统计结论。每次M1设计查询、正式评估和Track B测量后重算分别记账，原生调用与完整M2次数分开。

真实deepseek-v4-pro本轮3次HTTP200响应，选择SolveInverseAllocation → EvaluateM1 → SubmitCandidateForM2；首次候选先写盘，之后由Runner实际完成M2。三个原始请求/响应、实际模型、usage、耗时和工具轨迹均保留。LLM选择的候选与解析相同，本例没有证明数值增益。真实LLM反馈修复未执行；随机失败后的修复是原有确定性算法，未称LLM学习。

## 判决边界和回归

- 通过的首发为M1_PASS / M2_PARTIAL_PASS；M2_PARTIAL_PASS保留原overall_status=UNKNOWN，不升级为全行为通过。
- 所有实验PM_deg=null、PM_M2_UNKNOWN；UGF无独立注入为UNKNOWN；频率诊断有实测值，但冻结1e-6Hz精度无法认证，因此必需频率约束仍UNKNOWN。
- 捕获、窗口条件锁定时间和控制电压保存为实测诊断，不偷换原SystemSpec或扩充验收门限。BW观测仍是既有连续divided-phase，边沿观测等价性未知。
- 原Track A正式Proposal的M1逐字段完全相同；在项目外CWD通过统一Runner复验后，M2所有metrics、constraints、prediction_errors与原Track B逐字段相同，BW差0Hz，满足既有2%数值收敛尺度。候选、协议、核和DLL相同，因此这里证明工程迁移一致性，不能外推物理真值准确度。
- 修改前原项目+Track B共247测试通过；最终完整273项通过，包括原219、Track B28、新26。最终XML为 `experiments/stage3a_regression_final_20261104_02/tests.xml`。一次命令因未创建basetemp父目录产生47项setup错误，记录完整保留，后续新目录重跑通过。
- 版本/hash不符、结果漏指标、PM/频率伪PASS、错误候选、DLL缺失/身份变化、预算错误、服务不可用、执行异常均不能被接受为PASS；故障调用和成本落盘。缺后端的真实验证器错误路径已测试为M2_UNKNOWN并回传反馈。

## 已整合、未实现及保护范围

正式整合：原M1/域加载；解析与敏感度SLSQP；真实LLM首发工具接口；统一完整Proposal；Track B事件模型/测量/判决；版本绑定；相同Runner三策略；逐轮输入/成本/决策/失败记录；反馈进入原Agent层及已有确定性repair完整复验。没有新增物理模型、搜索算法或学习规则。

尚未实现/验收：独立PM/UGF、微Hz频率精度、噪声/抖动/功耗、边沿BW等价性、全域/近轨可靠性、真实LLM修复、多目标多seedAgent收益、跨平台后端、安装/wheel测试。当前Python无setuptools；运行基于本机已具备的NumPy/SciPy与审查过的原DLL。

保护清单覆盖15,245个已有文件；允许修改的既有文件仅为CLI五行分派、pyproject依赖/资源声明、gitignore、README及状态/决策文档。Track A算法、原Track B源码/仓库/历史输出、Stage1/1.5模型/配置、所有已有实验不得改变。最终比对结果、代码/测量保真与原始文件hash在 `audit_final_01/acceptance.json` 等文件中；初始Git状态已明确记录两份历史ZIP的既有删除，本轮未改写或恢复它们。

结构变化、可归档模块、暂不能删除的研发目录及下一阶段三个核心问题逐项缺口见[迁移审计与归档计划](MIGRATION_AND_ARCHIVE.md)。实际命令、失败记录及测试口径见[运行记录](RUN_COMMANDS.md)。本阶段到此停止，等待技术Leader审查，不继续扩展模型或算法。
