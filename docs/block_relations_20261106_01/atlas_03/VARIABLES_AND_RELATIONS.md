# PLL Block Variables and Relations

2026-11-06 · 当前冻结快照的只读研究图谱

|层级 / Block|Variables（原 ID）|Relations|范围 / 条件可行域|证据 / 适用边界|
|---|---|---|---|---|
|System-level|f_ref, N, f_target, spec_output_frequency_Hz, spec_BW_Hz, spec_PM_deg|F = N·f_ref = 80 MHz; 150 ≤ BW ≤ 300 kHz; PM ≥ 50°|f_ref = 10 MHz；N = 8；频率容差 1 µHz。SystemSpec 原 draft 元数据保留；Stage5 研究场景另有显式绑定。|输入快照 / 正式判决仅三项|
|固定模型假设|Kvco2, CP_mismatch, CP_leakage, q0, PFD_reset_delay, Cload, Gload|Kvco2 = CP_mismatch = CP_leakage = q0 = PFD_reset_delay = Cload = Gload = 0|各量分别按原单位等于零；非零为 UNSUPPORTED。无器件、噪声、延时和动态负载能力承诺。|原 M1 parser / J_IDEAL|
|PFD|phase_err, PFD_reset_delay, f_ref|φe = wrap(φref − φdiv); Δt = φe / (2π·f_ref)|phase_err 约定 [−π, π) rad；关系用于理想局部平均化；reset = 0。φe 不是新的分配轴。|语义约定 / 小信号推导|
|Charge Pump|Icp, Iup, Idown, Kpfd|Iup = Idown = Icp; Kpfd = Icp/(2π); īCP = Kpfd·φe<br>逆向：Icp = 2π·Kpfd；与 Kvco 必须按乘积联合分配。|Icp ∈ [50, 200] µA；Kpfd ∈ [7.957747, 31.830989] µA/rad。|已实现 M1 / 公式注册|
|Loop Filter|Rz, C1, C2, Zlf, Cload, Gload|Z(s) = (1+s·Rz·C2) / [s·(C1+C2)+s²·Rz·C1·C2]|Rz ∈ [2, 8] kΩ；C1 ∈ {50,100,200} pF；C2 ∈ {0.5,1,2} nF。C1 对地，并联串联 Rz–C2 支路。|已实现 M1 / KCL 数值核验|
|LF 零极点|Rz, C1, C2, fz, fp|fz = 1/(2π·Rz·C2); fp = (C1+C2)/(2π·Rz·C1·C2); q = fp/fz = 1+C2/C1<br>逆向：给定 C1,C2 及 fz 或形状 x、ωu，可反解 Rz；不得独立选 fz 和 fp。|s 平面极点为 0 与 −2π·fp；fz、fp 是正的频率幅值。离散电容对决定 q。|已实现 M1 / 精确代数|
|VCO|f0, Kvco, Vctrl_min, Vctrl_max, Vctrl_required, tuning_feasible, Kvco_local, Kvco_angular|f(V) = f0+Kvco·V; Vreq = (F−f0)/Kvco; Kvco_angular = 2π·Kvco<br>逆向：f0 ∈ [60,76] MHz ∩ (F−1.2·Kvco, F)；Kvco_local = Kvco。开端点必须保留。|f0 ∈ [60,76] MHz；Kvco ∈ [10,40] MHz/V；0 < Vreq < 1.2 V。f0 为零伏截距，非中心电压频率。|条件调谐解析 / 有限事件点支持|
|Divider|N, f_ref, f_target|f_div = f_out/N; H_div = 1/N; N = 8|理想整数分频、无分配自由度；无 delay/jitter/power 模型。|固定拓扑 / 已实现模型|
|Loop 动态|Kpfd, Kvco_angular, Zlf, L, T|P = Icp·Kvco; K = P/N; L(s) = K·Z(s)/s; T(s) = L(s)/(1+L(s)); Href = N·T<br>逆向：同 RC 和相同 P 保持理想动态；f0/Kvco 仍需满足调谐。|s = j2πf；2π 在 CP 与 VCO 增益间相消。P ∈ [500,8000] A·Hz/V 为声明轴乘积范围。|已实现 M1；历史局部 M2 支持|
|Bandwidth|BW, T|\|T(j2π·BW)\| = 1/√2; BW = β(q,x)·UGF<br>逆向：电容枚举 + x 形状 + β 数值根，再反解 Rz 与 P 并求交。|归一化 T 唯一向下半功率交越；BW ∈ [150,300] kHz。β 需要数值正根，BW 不等于 UGF。|M1 可解 / Protocol1.1 独立事件 BW|
|Phase Margin|PM, UGF, L|x = ωu·Rz·C2; PM = atan(x)−atan(x/q); PMmax = asin((q−1)/(q+1))<br>逆向：tanφ·x² − (q−1)·x + q·tanφ ≤ 0；判别式与 x 根区间给出必要形状域。|ωu = 2π·UGF；x>0；相位最终转为度。PM≥50° ⇒ C2/C1≥6.548632。全域理想上界72.247210°。|M1 精确形状 / M2 正式 PM UNKNOWN|
|Unity-gain 诊断|UGF, L|\|L(j·ωu)\| = 1; P = N·(C1+C2)·ωu²·h; h = √[(1+(x/q)²)/(1+x²)]<br>逆向：Rz = x/(ωu·C2)；正式周期 UGF/PM 尚未认证。|UGF 是诊断量，当前没有 UGF/RUR 硬目标。存在一个有限向下交越；数值失败不判通过。|M1 正向 / 条件代数逆解|
|连续稳定性|Icp, Kvco, Rz, C1, C2|a·s³+b·s²+c·s+d = 0; b·c−a·d = K·Rz·C2² > 0|a=Rz·C1·C2，b=C1+C2，c=K·Rz·C2，d=K。原正值域下 Routh 恒成立，仍须满足 PM/BW。|E_STABILITY / 非事件捕获证明|
|联合条件可行域|Icp, Rz, C1, C2, f0, Kvco, BW, PM|D_M1 = D_declared ∩ D_ideal ∩ D_tuning ∩ {150≤BW≤300 kHz, PM≥50°}<br>逆向：aR=x·β/(2π·C2)，aP=N·(C1+C2)·(2π/β)²·h；Rz=aR/B，P=aP·B²。见推导。|给定 C1,C2,x：B ∈ [Bmin,Bmax] ∩ [aR/Rmax,aR/Rmin] ∩ [√(Pmin/aP),√(Pmax/aP)]。|本轮条件域推导 / 正式 M1 核验|
|CP ↔ VCO 分摊|Icp, Kvco, f0, Vctrl_required|Kvco ∈ [Kvco_min,Kvco_max] ∩ [P/Icp_max,P/Icp_min]; Icp = P/Kvco<br>逆向：本声明域任一合法 Kvco 均可选到至少一个调谐 f0；不表示给定 f0 总合法。|若 f0 已定，再交 Kvco > (F−f0)/1.2 V；若 Kvco 已定，再交严格 f0 调谐区间。|条件解析 / 同产品局部 M2 支持|
|上下文 / 非执行量|V0, f_offset, Vctrl0, Rload|s = j2π·f_offset; f0 使用 V=0 截距；V0 仅旧上下文; Gload = 0|f_offset>0 为测量扫描；Vctrl0 为事件初值上下文；旧 V0/Rload 不能变成当前自由轴。|原 41 项目录 / 语义兼容边界|
|行为验收|BW, PM, UGF, Vctrl0, phase_err|D_verified ⊆ {逐个完整候选按冻结协议全部必需指标 PASS}|捕获/lock time 是初值与160µs窗口条件测量。正式PM、1µHz频率认证仍 UNKNOWN；完整已认证域未建立。|Stage4.1 十个局部点 / Stage5 当前结论|
|尚缺映射|—|Jitter / Phase Noise / Power / RUR：当前无可信数值可行域|补噪声源与频带、功耗定义与模块模型、RUR定义及协议后才能版本化扩展。Icp 不能当总电源电流。|UNSUPPORTED / 未增设 SystemSpec|

## 九个电容对的形状与联合区间

最后一列只是在 x=√q 这条峰值形状切片上的条件交集，不是每个电容对的全部可行域。三组空集不从原声明域删除。

|C1 / pF|C2 / nF|PM 上界 / °|PM≥50° 的 x 区间|x=√q 时联合 BW / kHz|
|---|---|---|---|---|
|50|0.5|56.442690|[1.626023, 6.764974]|[212.382, 300.000]|
|50|1|65.380023|[1.361856, 15.420137]|[150.000, 300.000]|
|50|2|72.247210|[1.269569, 32.294416]|[150.000, 300.000]|
|100|0.5|45.584691|空集|空集|
|100|1|56.442690|[1.626023, 6.764974]|[150.000, 300.000]|
|100|2|65.380023|[1.361856, 15.420137]|[150.000, 269.483]|
|200|0.5|33.748989|空集|空集|
|200|1|45.584691|空集|空集|
|200|2|56.442690|[1.626023, 6.764974]|[150.000, 212.382]|

## 怎样读这张表

六个独立分配变量是 **Icp、Rz、C1、C2、f0、Kvco**。f_ref、N、Vctrl_min/max 是固定输入，另七项是零非理想假设；BW、PM、UGF、Kpfd、fz/fp 等是计算或测量结果。表中的范围来自人工声明行为实验，不代表已表征电路能力。所有机器文件保留 SI 单位；展示表按 µA/kΩ/pF/nF/MHz 换算。

范围分四层：**声明域**是原轴的笛卡尔积；**模型有效域**还需零非理想、正值与严格内部调谐；**M1 规格可行域**再交 BW/PM 目标；**完整 TB 验证域**必须逐候选独立判决。历史有限局部点不构成连续验证区域，尚未签发满足全部正式 SystemSpec 的 Verified JointBlockSpec。

## 条件域推导与使用

取 P=Icp·Kvco，CΣ=C1+C2，q=1+C2/C1，x=ωu·Rz·C2。先从九个合法电容对枚举，不能在电容最小/最大之间连续插值。

1. **调谐**：f0 ∈ [60,76] MHz ∩ (F−Kvco·1.2V, F)，F=80 MHz。给定 f0 时，Kvco ∈ [10,40] MHz/V ∩ ((F−f0)/1.2V, ∞)。例如 Kvco=10 MHz/V 必须 f0>68 MHz；f0=68 MHz 与 Kvco=10 MHz/V 恰在 rail，不能进入 M1。Kvco=20 MHz/V 时，全部声明 f0 均可调谐。这里的 1.2 V 是控制轨，不作为供电规格。

2. **PM 形状**：PM(x)=atan(x)−atan(x/q)。令 φ=50°、t=tanφ，D=(q−1)²−4qt²。D<0 则这个电容对没有满足 PM 的点；否则 x ∈ [x−,x+]，x−=2qt/(q−1+√D)、x+=q/x−。这是以形状变量 x 表达的准确 PM 条件，单独看电容比只是必要筛选。PMmax 在 x=√q 取得；此峰值与其它约束是否相交还需核验。

3. **BW 与形状**：h=√[(1+(x/q)²)/(1+x²)]，y=(BW/UGF)²。β=√y，由唯一正根确定：

   (x/q)²·y³ + (1−2h·x²/q)·y² − (2h+h²·x²)·y − h² = 0。

   本工具复用已有 bandwidth_ratio 数值根，保留“数值”属性；没有把它写成经验常数或闭式公式。给定 B=BW 时，ωu=2πB/β。

4. **R 与增益交集**：令 aR=xβ/(2πC2)，aP=N·CΣ·(2π/β)²·h，则 Rz=aR/B，P=aP·B²。给定 C1,C2,x 时允许的 B 恰为：

   [150,300] kHz ∩ [aR/8000Ω,aR/2000Ω] ∩ [√(Pmin/aP),√(Pmax/aP)]，Pmin=500、Pmax=8000 A·Hz/V。

   交集为空就排除此形状。非空才可选 B、重建 Rz/P、再分摊 CP/VCO。这个条件表述覆盖连续 x，不等同于一次有限网格证明。本次在各电容对的 PM 峰值给出一条可读切片；切片边界不能称该电容对的全局 BW 边界。

5. **产品分摊与调谐**：Kvco ∈ [10,40] MHz/V ∩ [P/200µA,P/50µA]，Icp=P/Kvco；选 f0 前再套第1条。当前域任一合法 Kvco 的 f0 调谐交集都非空，因为最不利 Kvco=10 MHz/V 时 80−10×1.2=68<76 MHz。因此用 Pmin/Pmax 传播存在性是成立的；未来改变频率计划、控制轨或 f0 域，必须重新证明这一简化。若 f0 已固定，Kvco 的严格下界也要交进去。

这给出了当前理想 M1 的条件参数化：合法电容对 → 合法 x → 联合 B 区间 → P 与 R → Kvco/f0 交集 → 完整17量候选 → 原约束检查与正式 M1。所有等价关系限定于当前正值、无延时、无非理想的连续模型，不证明捕获、周期稳定性或实现能力。

## 证据边界和待补映射

- Stage4.1 十个完整参数点支持局部调谐/频响/阶跃映射，最大观测 BW 误差约0.624%；该值是有限样本观测，不作为全域误差界或新增 guard。C01/C08 同产品拆分提供局部等价例子。相关报告保留正式 PM/严格频率 UNKNOWN。
- Stage5 研究场景明确覆盖 BW/PM 阈值变体，不能把某个场景的结果或范围写回原 SystemSpec；本表默认列原 Stage1.5 快照。
- PFD/Divider 目前没有独立可分配性能轴。CP mismatch/leakage、VCO 曲率、LF 动态负载当前固定零；加宽这些范围需要新模型及验证。
- 静态相位偏置只可使用旧符号电荷平衡作条件初筛，当前不支持非零参数分配。锁定时间/捕获必须依照初值、窗口和事件协议测量；不使用 1/BW 或二阶 PM 经验式代替。
- Jitter/phase noise 缺少 PSD、积分频带、源传递与协议；Power 缺供电及各块损耗模型；RUR 未正式定义。这些项目列为缺口，不填写任意经验范围。

## 使用与后续

HTML 为独立离线表格，可直接打开/打印；Markdown 可评审与版本管理；JSON/CSV 保留41项变量、18条展示关系、原 Equation ID、域层级、来源与真实计数。JSON 是只读研究图谱，不自动接入 Agent，不授予 PASS 权限。

查看表中条件域后，仍用正式 pipeline 对完整候选运行原 TB。要覆盖新增非理想、噪声/功耗或扩大轴范围，另建版本并先定义测量合同；这张表本身不改变任何输入、策略或判决。

## 派生量的边际范围

这些是原声明域的投影极值或离散集合；不同量的端点不能任意拼成联合可行点。P/K/C_sum/q 是辅助派生符号，不是新增自由输入。

|派生量|单位|边际范围 / 离散集合|关系与适用层级|
|---|---|---|---|
|Kpfd|A/rad|[7.957747154594767e-06, 3.183098861837907e-05]|Icp/(2π)；declared projection|
|Kvco_angular|rad/s/V|[62831853.071795866, 251327412.28718346]|2π·Kvco；declared projection|
|P|A*Hz/V|[500.0, 8000.0]|Icp·Kvco；declared projection; supplementary derived symbol|
|K|A*Hz/V|[62.5, 1000.0]|P/N；declared projection; supplementary derived symbol|
|C_sum|F|[5.500000000000001e-10, 6e-10, 7.000000000000001e-10, 1.05e-09, 1.1000000000000001e-09, 1.2e-09, 2.05e-09, 2.1e-09, 2.2000000000000003e-09]|C1+C2；discrete derived choices; supplementary symbol|
|q|1|[3.5, 6.0, 11.0, 21.0, 41.0]|1+C2/C1；discrete derived choices; supplementary symbol|
|fz|Hz|[9947.183943243459, 159154.94309189534]|1/(2π·Rz·C2)；declared marginal extrema; coupled to fp|
|fp|Hz|[109419.02337567805, 1750704.3740108488]|(1/C1+1/C2)/(2π·Rz)；declared marginal extrema; coupled to fz|
|Vctrl_required|V|[0.1, 2.0]|(F−f0)/Kvco；declared [0.1,2] V; model-valid projection [0.1,1.2) V|
## 17项输入（SI 原值）

|变量|Block|单位|原声明范围 / 固定值|参与类型|
|---|---|---|---|---|
|f_ref|Reference|Hz|10000000|fixed_condition|
|N|Divider|1|8|fixed_condition|
|Icp|CP|A|{"min": 5e-05, "max": 0.0002}|free_allocation_parameter|
|Rz|LF|Ohm|{"min": 2000, "max": 8000}|free_allocation_parameter|
|C1|LF|F|[5e-11, 1e-10, 2e-10]|free_allocation_parameter|
|C2|LF|F|[5e-10, 1e-09, 2e-09]|free_allocation_parameter|
|f0|VCO|Hz|{"min": 60000000, "max": 76000000}|free_allocation_parameter|
|Kvco|VCO|Hz/V|{"min": 10000000, "max": 40000000}|free_allocation_parameter|
|Vctrl_min|VCO|V|0|fixed_condition|
|Vctrl_max|VCO|V|1.2|fixed_condition|
|Kvco2|VCO|Hz/V^2|0|model_assumption|
|CP_mismatch|CP|1|0|model_assumption|
|CP_leakage|CP|A|0|model_assumption|
|q0|CP|C|0|model_assumption|
|PFD_reset_delay|PFD|s|0|model_assumption|
|Cload|LF|F|0|model_assumption|
|Gload|LF|S|0|model_assumption|

## 全部41项变量的映射索引

|变量|块 / 类型|单位|语义|关系 ID|
|---|---|---|---|---|
|f_ref|Reference / fixed_condition|Hz|values.f_ref|R_SYSTEM, R_PFD, R_DIVIDER|
|N|Divider / fixed_condition|1|values.N|R_SYSTEM, R_DIVIDER|
|Icp|CP / free_allocation_parameter|A|values.Icp|R_CP, R_STABILITY, R_JOINT, R_SPLIT|
|Rz|LF / free_allocation_parameter|Ohm|values.Rz|R_LF, R_LF_SHAPE, R_STABILITY, R_JOINT|
|C1|LF / free_allocation_parameter|F|values.C1|R_LF, R_LF_SHAPE, R_STABILITY, R_JOINT|
|C2|LF / free_allocation_parameter|F|values.C2|R_LF, R_LF_SHAPE, R_STABILITY, R_JOINT|
|f0|VCO / free_allocation_parameter|Hz|values.f0|R_VCO, R_JOINT, R_SPLIT|
|Kvco|VCO / free_allocation_parameter|Hz/V|values.Kvco|R_VCO, R_STABILITY, R_JOINT, R_SPLIT|
|Vctrl_min|VCO / fixed_condition|V|values.Vctrl_min|R_VCO|
|Vctrl_max|VCO / fixed_condition|V|values.Vctrl_max|R_VCO|
|Kvco2|VCO / model_assumption|Hz/V^2|values.Kvco2|R_ASSUMPTIONS|
|CP_mismatch|CP / model_assumption|1|values.CP_mismatch|R_ASSUMPTIONS|
|CP_leakage|CP / model_assumption|A|values.CP_leakage|R_ASSUMPTIONS|
|q0|CP / model_assumption|C|values.q0|R_ASSUMPTIONS|
|PFD_reset_delay|PFD / model_assumption|s|values.PFD_reset_delay|R_ASSUMPTIONS, R_PFD|
|Cload|LF / model_assumption|F|values.Cload|R_ASSUMPTIONS, R_LF|
|Gload|LF / model_assumption|S|values.Gload|R_ASSUMPTIONS, R_LF|
|f_target|System / derived_parameter|Hz|F_FREQ_PLAN.f_target_Hz|R_SYSTEM, R_DIVIDER|
|Vctrl_required|VCO / derived_parameter|V|F_TUNING.Vctrl_required_V=(N*fref-f0)/Kvco|R_VCO, R_SPLIT|
|tuning_feasible|VCO / derived_parameter|1|F_TUNING.feasible|R_VCO|
|Kvco_local|VCO / derived_parameter|Hz/V|F_TUNING.Kvco_local_Hz_per_V|R_VCO|
|Kvco_angular|VCO / derived_parameter|rad/s/V|explicit internal 2*pi*Kvco|R_VCO, R_LOOP|
|Iup|CP / derived_parameter|A|F_KPFD.Iup_A|R_CP|
|Idown|CP / derived_parameter|A|F_KPFD.Idown_A|R_CP|
|Kpfd|PFD/CP / derived_parameter|A/rad|F_KPFD.Kpfd_A_per_rad|R_CP, R_LOOP|
|Zlf|LF / derived_parameter|Ohm|response.Zlf_Ohm [real,imag]|R_LF, R_LOOP|
|fz|LF / derived_parameter|Hz|F_LF_TF.zero_Hz|R_LF_SHAPE|
|fp|LF / derived_parameter|Hz|F_LF_TF.nonzero_pole_Hz|R_LF_SHAPE|
|L|Loop / derived_parameter|1|response.L [real,imag]|R_LOOP, R_PM, R_UGF|
|T|Loop / derived_parameter|1|response.T [real,imag]|R_LOOP, R_BW|
|UGF|Loop / system_measurement|Hz|metrics.UGF_Hz|R_PM, R_UGF, R_VERIFICATION|
|BW|Loop / system_measurement|Hz|metrics.BW_Hz|R_BW, R_JOINT, R_VERIFICATION|
|PM|Loop / system_measurement|deg|metrics.PM_deg|R_PM, R_JOINT, R_VERIFICATION|
|V0|VCO / context_not_executed|V|no v2 independent anchor|R_CONTEXT|
|phase_err|PFD / derived_parameter|rad|reference-minus-feedback radians|R_PFD, R_VERIFICATION|
|f_offset|Loop / context_not_executed|Hz|FrequencyScan; response_frequencies_Hz|R_CONTEXT|
|Vctrl0|VCO / context_not_executed|V|not executed in M1|R_CONTEXT, R_VERIFICATION|
|Rload|LF / context_not_executed|Ohm|no proxy resistance axis; Gload=0|R_CONTEXT|
|spec_output_frequency_Hz|System / system_requirement|Hz|conditional_locked_tuning_frequency|R_SYSTEM|
|spec_BW_Hz|System / system_requirement|Hz|continuous_normalized_T_first_downward_minus3dB|R_SYSTEM|
|spec_PM_deg|System / system_requirement|deg|180_plus_continuous_L_phase_at_UGF|R_SYSTEM|

实际数值调用和结果见 `validation.json`；来源路径/SHA/语义见 `source_manifest.json`。此轮未执行 M2/LLM。
