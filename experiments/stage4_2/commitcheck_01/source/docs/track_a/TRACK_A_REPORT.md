# Track A — Physics-guided PLL Spec Allocation & Agent Strategy

2026-11-04。Track A行为级分配交付完成，待技术Leader审查；未修改Track B，未合并分支。当前最高证据为M1_VALIDATED，M2未执行。

## WHAT：实现的策略与交付

- 名义/规则、解析逆向、归一化敏感度+SLSQP约束优化、单次seeded random，及明确标记的mock工具工作流。
- 真实deepseek-v4-pro工具决策链；三次真实响应，选择解析求解→原M1评估→正式提交。
- 可加载的AllocationProposal、独立反馈/修复接口、七类模拟反馈、可复现的六目标×五策略首发比较。
- 主入口 `python -m pll_allocation.track_a`；实现/测试/配置/文档均在专用track_a目录，专用分支 `track-a/physics-guided-allocation`。

## HOW：物理、数值和Agent的分工

物理反解先枚举九种实际电容组合，用PM上界排除不可能比值。q=1+C2/C1，x=ωuRzC2；PM=atan(x)−atan(x/q)，峰值asin((q−1)/(q+1))。选形状x与BW后，Rz和IcpKvco乘积解析反解；BW/UGF比由唯一正根数值求解。产品分摊到合法Icp/Kvco交集，再选f0改善调谐裕量。完整推导见A1_INVERSE_RELATIONS.md。

敏感度使用9次原M1，包含中心及四连续参数±1%差分，区分PM曲率。Icp/Kvco的环路弹性相同，优化改用产品增益/Rz/Kvco/Vreq坐标并归一化至[0,1]；枚举电容，SLSQP最大化最小系统/连续域/调谐裕量。BW半区间、PM下限、电压半范围等归一化及1%一阶守护量是工程准则，不是物理定律或模型误差统计。全局最优未证明；BO因低维离散枚举与廉价模型尚无必要性证据，未实现。

LLM只决定下一工具和候选句柄，不做高精度浮点计算，也不提供PASS。执行器白名单和预算独立，正式候选先写盘，再由Runner调用原M1及原judge。SubmitCandidateForM2在本轮只暂存候选，明确延后Track B。结构化Action/Observation/Decision日志可追溯真实选择。

## RESULT：官方首发完整BlockSpec与M1

官方目标：10MHz×8=80MHz，BW150–300kHz、PM≥50°。原SystemSpec v0的draft=true保留，本轮授权固定使用阶段快照；未升级或改写旧文件。

|Block|参数|分配|选择理由|
|---|---|---:|---|
|CP|Icp|104.404300186 µA|由环路乘积与合法Kvco分摊反解|
|LF|Rz|3048.124920669 Ω|由峰值形状及225kHz频率尺度反解|
|LF|C1|50 pF|声明choices中最大相位上界的电容比|
|LF|C2|2 nF|C2/C1=40；q=41|
|VCO|f0|63.761604100 MHz|0V截距，令调谐电压居中|
|VCO|Kvco|27.063993167 MHz/V|增益分摊可行交集中心|
|Divider|N|8|冻结频率规划|
|Reference|f_ref|10 MHz|冻结工况|
|VCO|Vctrl_min/max|0 / 1.2 V|冻结功能域|
|PFD|PFD_reset_delay|0 s|理想M1支持子集|
|CP|CP_mismatch / CP_leakage / q0|0 / 0 A / 0 C|理想M1支持子集|
|LF|Cload / Gload|0 F / 0 S|冻结无增量负载假设|
|VCO|Kvco2|0 Hz/V²|冻结线性VCO|

原M1结果：条件输出80000000Hz，Vreq=0.600000V，UGF=167166.520425Hz，BW=225000.000000Hz，PM=72.247209838°。M1_SPEC_PASS；BW上下界各75kHz，PM裕量22.247209838°，调谐距轨0.6V。最小联合归一化裕量0.349374974。

完整17参数、单位、固定拓扑/工况、版本、哈希、原M1与Agent/策略信息见 [AllocationProposal](delivery/AllocationProposal.json)。真实LLM选择相同参数哈希：`74864b2e3b6a8cbb9aac7610632ae0d8c5428be38c8a7e1d1c85038526ff050b`。另附优化候选及真实LLM版本，原始输出来源见delivery/provenance.json。

## COMPARISON：质量、成本与Agent增量

|官方策略|首发M1|BW kHz|PM °|最小联合归一化裕量|分配秒|廉价调用|设计M1查询|
|---|---|---:|---:|---:|---:|---:|---:|
|nominal|M1_SPEC_PASS|222.379183|56.442690|0.128853804|0.000712|0|0|
|analytical|M1_SPEC_PASS|225.000000|72.247210|0.349374974|0.002106|11|0|
|sensitivity_optimization|M1_SPEC_PASS|204.356651|72.247210|0.444944197|2.133208|160|9|
|random|M1_SPEC_FAIL|709.216566|40.936788|-5.456220877|0.000723|0|0|
|mock_agent|M1_SPEC_PASS|204.356651|72.247210|0.444944197|0.347682|171|9|
|real_llm|M1_SPEC_PASS|225.000000|72.247210|0.349374974|51.295642|11|1|

每行正式独立M1另加1次；分配成本不含正式评估及选定后统一16角诊断，全部成本另存cost_events。wall time为单次实测，首次SciPy导入和缓存使耗时不能作为统计速度结论。

真实LLM使用3次网络调用，约51.296秒，usage记录input_tokens=6163、cache_read_input_tokens=1280、output_tokens=1989；货币费用未提供。它选用解析候选，数值质量与解析基线相同，最小裕量比优化低约0.095569223；没有可测量的数值质量增益。工具路径/避免不必要优化的决策已实际运行，但单案例不能证明一般化的Agent增益。mock只验证工作流，不算LLM成绩。

官方+四个可行变体中，解析与优化均逐案例M1通过；名义仅官方通过，随机seed23六目标均失败。PM≥75°案例由解析、优化、mock返回PROVEN_INFEASIBLE（全域PM上界72.247209838°）；名义/随机仅规格失败。30组共16个M1_PASS、11个M1_FAIL、3个不可行证书。这里只报告描述性案例结果，不报告统计first-shot成功率。

完整六目标比较见 [机器CSV](../../outputs/track_a_benchmark_20261104_02/comparison.csv) 及 [实验报告](../../outputs/track_a_benchmark_20261104_02/report.md)。受控变体与官方分开保存；校准集为空，策略未读取139点表或44-PASS集合。Stage1.5报告和已公开nominal已知，因此官方为prior-informed案例。

官方名义/解析/优化三者及mock都通过16个±1%连续参数角点的同方程诊断；随机0/16。此有限压力集不含连续电容扰动、不验证M2或模型误差，也不能证明连续不确定性盒内全通过。最紧的71°变体只剩1.247°相位裕量，提示模型差异可能主导。

## LIMITATIONS：未验收边界

- M2调用=0，条件锁频、连续BW/PM不等同事件捕获或实测频响；所有proposal verified_joint_block_spec=false。噪声、抖动、功耗、锁定时间及非理想CP仍未支持。
- 真实LLM只测官方一例；未对分布/多seed统计，未测真实LLM反馈修复。修复接口只完成七类模拟路由，无真实修复成功率。无变化修复拒绝重复提交。
- 逆向有限形状失败为NOT_FOUND，数值局部优化失败不能宣称不可行；仅解析必要条件给不可行证书。
- 敏感度守护量为名义局部一阶近似；预测行为误差/置信区间没有建立。电容choices属于声明行为域，未映射器件实现能力。
- 当前Agent候选库由确定性工具定义，未实现任意自主模型/目标函数或自学习；不把代码路由当作LLM收益。

## NEXT：下一轮优先实验

先将本Proposal交Track B独立测量BW/PM及冷启动，建立带协议/波形的预测误差。优先用可行但裕量较小的near_ceiling变体检验保守目标和模型差异诊断。再比较同M2预算下“解析直接提交 / 必要时优化 / LLM选择局部修复或重分配”，预先分离校准/测试目标，保存每次LLM与TB失败成本。暂不增加BO，除非反馈后评估显著昂贵且确定性模型不足。

## 验收与执行证据

- 最终完整回归：215项，failures=0、errors=0；含原179项。
- 5123份已有源码/配置/历史输出SHA未变；30个目标/策略决策两轮hash/判决一致；55份Proposal通过直接读取及合同核对。
- 每轮30组正式比较117次M1、3116次廉价预测（其中分配2684次、设计M1=90）；第二轮为审查修复后再现，不作为额外独立样本。真实LLM另2次M1、27次廉价预测；模拟修复、开发/测试成本分别保留，不并入首发统计。
- M2/MATLAB/ngspice/器件仿真=0；真实LLM网络请求=3。旧源码、冻结输入/历史测试未修改；只更新阶段状态/决策及新增Track A产物。
- 实际命令与全部运行目录见 [RUN_COMMANDS](RUN_COMMANDS.md)，审查修正见 [REVIEW_AND_DEVELOPMENT_RECORD](REVIEW_AND_DEVELOPMENT_RECORD.md)。

本阶段按用户停止条件收束，等待技术Leader审查，不自行接入或修改Track B，不合并分支。
