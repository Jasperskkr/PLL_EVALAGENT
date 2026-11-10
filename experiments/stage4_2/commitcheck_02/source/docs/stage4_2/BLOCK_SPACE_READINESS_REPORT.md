# PLL Physics Mapping & Block Space Readiness — Stage4.2

2026-11-05。**可用能力是理想连续锁定点的频率/调谐解析约束、BW/PM的公式引导数值分配和有限点BW/捕获行为评价。当前没有完整行为规格认证，也没有实测电路能力域。** 新增研究Registry可供查询与选择已有工具，不接管正式Agent或Runner。

## WHAT · 当前可分配能力

|验收问题|审查结论|
|---|---|
|1. Block Space可信支持哪些SystemSpec？|当前80MHz、BW150–300kHz、PM≥50°的**条件M1预测/分配**；BW有局部独立M2支持，频率1µHz容差和PM行为认证仍UNKNOWN，不能交付完整Verified JointBlockSpec|
|2. 哪些直接反推？|固定频率计划一致性、Vreq/f0/Kvco的条件代数关系，以及给定C/形状/UGF的R与增益乘积重建。后者不是完整多约束分配；固定N/fref不能被Agent改动|
|3. 哪些只能公式初筛后搜索？|PM的C比上界/x区间、调谐必要域、Routh、gain-product区间先筛，再由原BW比值数值根/有界SLSQP求交。UGF有正向与条件代数，但现有官方policy没有UGF目标合同|
|4. 哪些缺关键物理机制？|RUR缺正式定义；非零静态偏置缺经过统一的q0/leakage/reset/mismatch模型；捕获缺全局域/多初值界；jitter/power缺噪声/供电/损耗与协议|
|5. 范围有明确实验依据吗？|来源和研究意图明确，但六轴均为MANUALLY_DECLARED_BEHAVIORAL_EXPERIMENT，稀疏实验验证不等于范围来自实测电路或全域已验证|
|6. M1何时有证据支持？|固定理想拓扑、正RC/gain、内部线性VCO调谐、无非理想/加载、锁定小信号。数值实现一致证据多，行为误差支持仅局部工作点和指定测量条件|
|7. 哪些需M2补证？|相同UGF不同PM的动态比较、CP/VCO乘积分解、非锚点BW及冷启动捕获、周期UGF/PM定义与谐波稳定性；严格频率也需独立不确定度证明|
|8. Agent现在可安全用什么？|只读Registry，既有check_parameters、M1 evaluate、propagate/phase_interval/pm_ceiling、analytical/optimize及独立verify。所有输出带域/版本/证据边界，筛选不发PASS，不自动启用新约束|

正式SystemSpec只有三项。矩阵与逐式WHAT/INPUT/DOMAIN/INVERSE/EVIDENCE/LIMITATION详见[SYSTEM_SPEC_MAPPING_MATRIX](SYSTEM_SPEC_MAPPING_MATRIX.md)及[EQUATION_AND_DOMAIN_AUDIT](EQUATION_AND_DOMAIN_AUDIT.md)。旧草案元数据不变，运行快照哈希冻结不等于新产品规格批准。

## HOW · 声明域、数学域与约束传播

|变量|原声明范围 / default|来源与可信度|
|---|---|---|
|CP.Icp|50–200µA /100µA|围绕原MATLAB nominal的增益研究范围；理想对称电流，无输出电阻/功耗实测|
|LF.Rz|2000–8000Ω /3820Ω|人为探索zero/pole/damping；不是可实现电阻PVT能力证明|
|LF.C1|{50,100,200}pF /100pF|原声明的三个choice；不可连续优化或插值成新合法值|
|LF.C2|{0.5,1,2}nF /1nF|原声明三个choice；无面积/寄生/实现证据|
|VCO.f0|60–76MHz /72MHz|零伏截距；研究范围特意允许调谐不可达组合|
|VCO.Kvco|10–40MHz/V /20MHz/V|理想正斜率，非角频单位；非实测PVT/非线性能力|

三个域必须分开：

1. **声明域**：六轴原范围/choice，其他11个输入固定，完整17量SI信封。六变量还原为完整候选之后才可送M1/M2。
2. **数学有效域**：理想参数、positive f(V)、严格内部调谐以及有限唯一交越等。当前主要排除`Kvco≤(80MHz−f0)/1.2V`；所有正理想动态参数满足连续Routh，不等于捕获或PM达标。
3. **当前M1规格可行域**：数学有效且BW150–300kHz、PM≥50°。不能因规格失败删除原声明域。

在独立均匀的连续f0×Kvco矩形这个**人为测度**下，调谐必要域面积为17/18：排除f0<68MHz的低Kvco三角形；边界为零测度。该精确几何结果不是硅片成功概率。本次数值网格含216/1728不可调谐点，比例不同，不能当积分估计。

必要PM形状排除：

|C1 pF \ C2 nF|0.5|1|2|
|---|---:|---:|---:|
|50|56.442690°|65.380023°|72.247210°|
|100|45.584691°（不达50）|56.442690°|65.380023°|
|200|33.748989°（不达50）|45.584691°（不达50）|56.442690°|

表中为理想PM上界，不是每组实际PM。三个被排除组合仍保留为合法研究负对照；其余六组也必须检查R/gain/BW/tuning交集。优先候选可适当远离rail和离散PM上界，但这里只给排序建议，不增加电压裕量/UGF比等新硬约束。

边界风险：near-rail线性化/限幅/捕获；高UGF/fref时采样与谐波；R/C组合导致zero/pole形状和CP面积分辨率变化；Kvco/f0的调谐耦合；C ratio小导致PM上界不足。M2或显式数值域检查出现UNSUPPORTED/超域应停止可信推断，不通过收缩模型宣称全域可靠。

## EVIDENCE · 实际数值与历史行为证据

新主实验`experiments/stage4_2/readiness_05`按预声明轴扫描1728点：1512数学有效、216 OUT_OF_DOMAIN；有效点中212 M1_SPEC_PASS、1300 M1_SPEC_FAIL。cheap predictor对独立幅度多项式参考1512点全部一致；固定mod23抽样67点与正式M1一致，最大BW/UGF相对差约1.11e-12，PM绝对差2.44e-11°。该误差反映实现，不是行为模型误差。

网格有效点的UGF约29.982–655.957kHz、BW46.478–1042.512kHz、PM11.979–72.186°；它们是样本极值，不是连续域的全局界。全局PM形状上界72.247°则来自解析证明。

历史证据按原文件SHA保留本地小快照：

- Stage1.5：139个计划点，124有效M1点一致；32点/64次事件步长对比，26点频率/控制条件一致，6点有近轨/限幅/不可调谐风险。这批没有BW/PM/UGF认证。
- Stage4：Nominal、保存的真实Agent、PM边界三例，原BW的M1→M2分别222.379→222.853、225.000→226.404、161.619→161.896kHz。UGF/PM局部诊断收敛但正式值仍null/UNKNOWN；不是三例稳定性认证。上述数值是历史读取，未重复计为本阶段TB。
- Stage3A.1/Track A原算法及测试保持；旧的“只提供正向”或“尚无BW”字段是历史时点记录，新Registry用独立证据层说明现状，不覆盖旧内容。

阶段研究共执行五轮相同网格（每轮94次正式M1、1512次cheap、1512次多项式），合计470/7560/7560次。第一轮候选判决适配器漏传原M1 hash/units/protocols，被原判决器正确拒绝为UNKNOWN；第一轮完整保留并另记postprocessing_failure。第二轮修复后通过；第三轮增加显式换行等价哈希记录，第四轮补齐干净导出的证据回退与运行源码快照，第五轮补齐Registry规范单位拒绝检查，数值/候选保持一致。不是五个独立统计样本。最终权威为readiness_05。

研究程序新M2=0、LLM=0。完整回归中的原有TB另计；不把旧实验或测试当作本次新物理证据。实际命令/测试/成本详见[执行与提交记录](RUN_AND_RELEASE.md)。

## 未来M2候选：仅M1选定，未反向挑选

完整17量SI参数、固定工况、参数SHA、来源、M1原始结果与域/判决在[M2_VALIDATION_CANDIDATES.json](M2_VALIDATION_CANDIDATES.json)。10点全部声明/数学域合法，7点M1通过、3点M1失败，均`M2_status=NOT_RUN_STAGE4_2`。

|ID|UGF kHz|PM °|BW kHz|角色与验证假设|
|---|---:|---:|---:|---|
|C01 Nominal|138.176|56.443|222.379|历史锚点|
|C02 Real Agent|167.167|72.247|225.000|保存完整Proposal；高PM形状锚点，不算新LLM|
|C03 PM边界|104.265|50.000|161.619|旧合法边界锚点|
|C04 matched55|140.000|55.000|229.409|同C/Kvco/f0/UGF组|
|C05 matched60|140.000|60.000|225.707|同组，仅R/Icp必要协变|
|C06 matched65|140.000|65.000|211.363|同组，PM靠近该C比上界|
|C07 lowPM|140.000|35.000|224.504|合法PM失败负对照，保留|
|C08 gain split|138.176|56.443|222.379|与Nominal乘积/RC动态相同，CP/VCO分解及Vreq不同|
|C09 holdout|124.446|45.524|209.572|预声明保留；M1 PM失败仍保留|
|C10 holdout|219.228|48.488|363.794|预声明保留；M1 BW/PM失败仍保留|

C04–06固定140kHz、C1=100pF/C2=2nF/Kvco=20MHz/V/f0=68MHz，减少部分混杂；R/Icp必然随PM变化，不能解释为纯因果PM实验。C07电容不同，也不能单独归因于PM。保留点只登记M1，不参与本阶段导数/shape配对/方法调试；对已审查Stage1.5+Stage4锚点集无exact match，但没有宣称对全部历史搜索点“盲测独立”。下一阶段应先冻结协议再测，不能依据结果换掉失败点。

## Agent查询与现有工具选择

只读入口：

```powershell
python -m pll_allocation.physics_mapping.registry --registry docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json --metric Vctrl_required_V --route
python -m pll_allocation.physics_mapping.registry --registry docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json --metric BW_Hz --route
python -m pll_allocation.physics_mapping.registry --registry docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json --metric capture --route
```

1. `Vctrl_required_V`返回ANALYTICAL_INVERSE。例：Kvco=20MHz/V、Vreq=.4V，直接求f0=72MHz，再用`make_candidate/check_parameters/evaluate`独立检查，不把静态存在当捕获。
2. `BW_Hz`返回NUMERICAL_INVERSE。先`allocation.physics.propagate(model,spec)`，再原`allocation.allocate.analytical(model,spec,Meter())`或`optimize`；它们提出完整候选，Runner独立检查并执行M2。Registry没有替换solver或改目标。
3. `capture`返回BEHAVIORAL_ONLY。先内部调谐与rail必要筛选，再将完整Proposal交`verification.verify.verify`或同一个Pipeline，按原初值/窗口/预算测量。未捕获是窗口条件，不能由低PM先验给出绝对不可锁结论。

实际四个查询（含RUR拒绝）在`agent_query_examples.json`。Registry loader绑定14个冻结源/配置路径、模型版本/哈希及Equation IDs，拒绝错误模型、来源、单位合同和擅自启用约束。原字节SHA和CRLF→LF归一化SHA都保留；只有声明的换行等价可接受，返回EXPLICIT_CRLF_LF_EQUIVALENCE，其他内容变化拒绝。索引本身为`RESEARCH_REVIEW_ONLY`，没有自动注入生产Agent提示词。

## LIMITATIONS / NEXT

已完成：映射矩阵、逐式域审查、范围来源/层级、轻量可查询Registry、有限扫描/耦合实验、10点含2 holdout计划和原工作树保护。仍待Leader验收；没有升级M1可信域、系统规格或M2判决。

下一阶段缺口按依赖排列：

1. 周期UGF/PM：有截断误差控制的谐波返回矩阵与周期稳定性条件，并建立与冻结连续PM目标的定义桥接。这是认证缺口，不是调阈值问题。
2. 行为覆盖：对预声明同UGF/不同PM及gain-split组执行相同M2协议、多个批准初值/窗口；两个holdout保留到方法锁定后，失败不重选。需要原始复数响应/漂移/失真/成本记录。
3. 能力扩展前置：批准RUR定义、非零静态电荷模型、严格频率不确定度与噪声/功耗合同；没有这些信息不能可信分配新增指标。六轴范围若将来要改，须单独版本化与证据审查。

不开展Stage4.1，不设计新Agent算法。本阶段独立Commit只含Stage4.2新增产物及阶段记录增量；Stage4未提交成果、既存ZIP删除和历史目录完整保留。审查完成后停止，等待技术Leader。
