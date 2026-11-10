# DOMAIN_VALIDATION_REPORT

2026-11-04 · Stage 1.5。输入/目标保持 Stage 1，不扩域、不调低门限。

## A. Declared Parameter Domain

六个可分配参数如下；其余固定系统条件或理想模型假设。均为人工定义的行为实验范围，未包装成已验证的器件实现能力。

|参数|范围或 choices|Nominal|单位|范围选择理由|
|---|---|---:|---|---|
|Icp|5e-05 … 0.0002|0.0001|A|Factor-of-two local gain exploration about 100uA; preserve Stage 1 declared bounds, not device evidence.|
|Rz|2000 … 8000|3820|Ohm|Probe zero/pole and damping tradeoff around 3820 Ohm without changing Stage 1 bounds.|
|C1|[5e-11, 1e-10, 2e-10]|1e-10|F|Three declared shunt capacitances, spanning 0.5x to 2x nominal.|
|C2|[5e-10, 1e-09, 2e-09]|1e-09|F|Three declared branch capacitances, spanning 0.5x to 2x nominal.|
|f0|60000000 … 76000000|72000000|Hz|Zero-volt intercept choices permit both interior tuning and unreachable cases.|
|Kvco|10000000 … 40000000|20000000|Hz/V|Positive frequency slope spanning 0.5x to 2x nominal; jointly constrained by tuning.|

PFD reset=0、CP mismatch/leakage/q0=0，VCO Kvco2=0，Cload=Gload=0。N=8，fref=10 MHz，Vctrl∈[0,1.2]V。

## B. Model Validity Domain

声明域 ∩ 正值 SI 参数 ∩ 理想假设 ∩ 正且单调 VCO ∩ 严格内部调谐点 ∩ 可解析稳定性 ∩ 数值上有效的交越。联合调谐限制为 `0 < (80e6-f0)/Kvco < 1.2`；不是单独验证 f0 与 Kvco 的范围就足够。

声明域未因事件采样结果被私自收缩或扩大。全域行为可信度另列为 NOT_ESTABLISHED；证据只针对被实际测量的点。距轨 1 mV 及更小裕量的区域已有不良捕获诊断，应作为后续 allocation 风险提示，不能因为 M1 有解而自动宣布捕获成功。

## C. SystemSpec Feasible Region

在 B 域中再要求 BW∈[150,300]kHz、PM≥50°及条件锁定频率 80 MHz。UGF 不参与通过判定。本轮找到 44 个 M1 通过点，证明存在可行候选；这些点不构成对整个高维可行域的精确求解，也不是均匀随机成功率估计。

## 扫描计划与全部成本

评估前已保存 `candidate_snapshots.json` 和 `validation_plan.json`。固定名义点、±2%局部扰动、单轴上下界及1%邻域、连续参数16角点、电容组合、48点Halton、Icp/Rz各17点固定切片、调谐轨附近点、增益乘积不变点及高低增益折中点；去除重复后按类别保留 alias。没有自适应逆向求解器或优化器。

共 139 点：声明域内 134 点 + 域外异常 5 点；124 点有效 M1，44 点 M1_SPEC_PASS、80 点 M1_SPEC_FAIL、15 点 UNKNOWN。域内有10点无内部调谐点；另5点是域外符号/非理想异常。

|采样类别|唯一点数|
|---|---:|
|nominal|1|
|local_sensitivity|8|
|single_parameter_boundary|16|
|discrete_sensitivity|4|
|coupled_boundary|16|
|capacitor_coupling|4|
|low_discrepancy|48|
|system_boundary_slice|31|
|tuning_boundary|3|
|explicit_coupling|3|
|out_of_declared_domain_anomaly|5|

每个候选在任何计算前写盘；每点保存参数、联合域检查、预测、独立参考、误差、事件结果及失败原因。机器表格：`outputs/block_space_v1_20261104_01/FORWARD_MODEL_VALIDATION.csv`。

本轮域扫描：124次M1、124次独立多项式参考、64次Python事件仿真（32点×两步长），36,943,353个积分点。另做边界诊断4次事件仿真；MATLAB Runtime=0，LLM=0。测试中的2µs稳态不变量是额外短仿真，不混入32点统计。

## 第一类：数值与公式验证

|误差|最大值|门限|
|---|---:|---:|
|UGF 相对误差|1.112e-12|0.005|
|BW 相对误差|1.109e-12|0.005|
|PM 绝对误差|1.700e-11°|0.2°|
|Vreq 绝对误差|0 V|1e-6 V|

124个有效点全部通过独立数值门限。正值理想网络连续稳定已解析证明；域外负R/负增益拒绝。无交越、多交越、非有限数值测试明确拒绝。

## 第二类：事件行为交叉验证

原 MATLAB 工程中已有 `verification/python_crosscheck.py::simulate` 被按字节快照到新数据目录，SHA=f6f55027622840cb62090e3870c29b75c23824b27fa786689605b7c6196706e2。通过 AST 仅提取 simulate，原文件和 check() 的写盘流程未执行。该模型为固定步长、边沿分数插值 PFD/CP、Euler KCL、VCO相位积分、0..1.2V控制限幅；不是纯平均线性模型，也不是精确事件求解器。

预设初值0.15V、160µs窗口、最后20%统计；粗步长1/(25*fmax)，再减半。门限提前落盘：步长频率差≤1ppm、控制端点差≤0.1mV、相位RMS差≤0.1°；条件频率预测误差≤100ppm、控制端点差≤1mV。**这些是交叉验证门限，不是替换冻结SystemSpec的1e-6Hz频率允差。**

32点全部完成且满足两档步长比较门限。26个有内部锁点且尾窗有跟踪观测的点获得条件频率/控制一致性证据；6点不一致/不可比较，均保留：

|点|标签|M1结论|事件尾均频率 / Hz|Vctrl末值 / V|原因|
|---|---|---:|---:|---|
|C029|continuous_corner_00|UNKNOWN|71999999.999999|1.200000000|调谐无内部点或近轨捕获未建立；存在近轨样点|
|C041|continuous_corner_12|UNKNOWN|71999999.992801|1.200000000|调谐无内部点或近轨捕获未建立；存在近轨样点|
|C049|halton_01|UNKNOWN|76223776.223775|1.200000000|调谐无内部点或近轨捕获未建立；存在近轨样点|
|C128|tuning_rail_67990000.0|UNKNOWN|79989999.999999|1.200000000|调谐无内部点或近轨捕获未建立；存在近轨样点|
|C129|tuning_rail_68000000.0|UNKNOWN|80000000.000000|1.200000000|调谐无内部点或近轨捕获未建立；存在近轨样点|
|C130|tuning_rail_68010000.0|M1_SPEC_FAIL|80010000.000000|1.200000000|调谐无内部点或近轨捕获未建立；存在近轨样点|

这26点的最大条件频率误差为 1.96966 ppm，控制端点误差最大 1.81227e-05 V。

C130：f0=68.01MHz、Kvco=10MHz/V，Vreq=1.199V。160µs冷启动停在上轨，频差约+125ppm；延长到640µs、两步长仍约+125ppm，尾窗相位RMS约53.77°。这不能证明永久无法捕获。将同一参数从Vreq启动后，160µs尾频差约 -2.99329e-05 ppm，Vctrl≈1.198999999732V且无近轨样点。说明本点具备局部锁定点一致性，但冷启动捕获受限幅/初值/有限窗口影响；不得把已锁定M1外推到捕获。

长窗口和暖启动是新的诊断记录，位于 `outputs/block_space_boundary_diagnostic_20261104_01/` 和 `outputs/block_space_warmstart_diagnostic_20261104_01/`。原失败结果未覆盖。参考simulate在“窗口中从未超2%频差”时返回settle_us=NaN，已显式转换为null并记录缺失，未将其当作锁定时间。

事件模型只返回摘要，无原始轨迹/持锁协议；无BW/PM注入。不能宣称全M2系统验收、完整Lock Time或Static Phase Error支持。

## 敏感度与耦合

|参数|方法|BW log弹性|UGF log弹性|PM变化/1%参数|Vreq log弹性|
|---|---|---:|---:|---:|---:|
|Icp|局部±2%|0.9274|0.8571|0.000049°|0.0000|
|Rz|局部±2%|0.8546|0.7141|0.000175°|0.0000|
|C1|离散端点割线|-0.0380|-0.1485|-0.140673°|0.0000|
|C2|离散端点割线|-0.0587|-0.0103|0.145153°|0.0000|
|f0|局部±2%|0.0000|0.0000|0.000000°|-9.0979|
|Kvco|局部±2%|0.9274|0.8571|0.000049°|-1.0000|

在名义点附近，Icp和Kvco对BW的弹性均约0.927，Rz约0.855；两者Icp×Kvco/N共同决定环路增益。名义点附近PM对Icp/Rz一阶变化很小，不能外推到整个域。C1/C2比值显著改变最大可达PM；电容行是离散端点割线，不应当作连续局部导数。f0不改变理想线性环路，却显著改变调谐裕量。

解析上PM峰值为 atan(sqrt(C2/C1+1))−atan(1/sqrt(C2/C1+1))，对应ω=sqrt(ωzωp)。因此PM≥50°的必要条件为 C2/C1≥约6.55；这不是充分条件，因为UGF必须落在合适的频率位置，且BW还有边界。

## 典型参考、违例与边界

推荐点固定为本轮之前的Stage1名义点：Icp=100µA、Rz=3820Ω、C1=100pF、C2=1nF、f0=72MHz、Kvco=20MHz/V、Vctrl∈[0,1.2]V。Vreq=0.4V，UGF≈138176.441Hz，BW≈222379.183Hz，PM≈56.442690°。BW下界/上界裕量分别72.379/77.621kHz，PM裕量6.443°，电压裕量0.4V。保存为M1_VALIDATED；没有全M2签发。

|点|BW / kHz|PM / deg|结论|
|---|---:|---:|---|
|C000 nominal|222.379183|56.442690|M1_SPEC_PASS|
|C009 boundary_Rz_0.0|145.702552|43.660717|M1_SPEC_FAIL|
|C013 choice_C1_5e-11|215.236953|64.685804|M1_SPEC_PASS|
|C014 choice_C1_2e-10|204.198260|45.184347|M1_SPEC_FAIL|
|C122 Rz_spec_slice_10|300.760119|50.585098|M1_SPEC_FAIL|
|C123 Rz_spec_slice_11|310.694261|48.881549|M1_SPEC_FAIL|
|C132 high_gain_tradeoff|757.856626|22.122816|M1_SPEC_FAIL|
|C133 low_gain_tradeoff|62.290206|24.134738|M1_SPEC_FAIL|

Rz切片在C121与C122附近跨过BW上限；C122的BW=300.760kHz、PM=50.585°，体现BW先失败。C123 PM=48.882°且BW=310.694kHz。上下界和PM边界没有被重设以制造成功。BW下限附近也可能PM不足，因此单项满足不代表联合通过。

本轮样本最高UGF/fref≈0.0517、BW/fref≈0.0841；这些高比值区域的BW/PM采样效应仍未被验证，不把该最大值当作全域理论界。

## 未解决区域与下一步最小验证

优先保留M1为已支持BW/PM的评估器；补可重用事件波形与相位调制注入，对名义点、BW/PM边界、高UGF/fref和近轨点建立收敛的闭环响应测量。先测BW与T频响；PM若无独立开环注入/闭环辨识协议继续标未验证。捕获另需多初值、较长窗口、无cycle-slip持锁协议。非理想CP、reset、负载、曲率、噪声与功耗均不属于当前支持域。
