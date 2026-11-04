# EQUATION_MAPPING_REPORT

2026-11-04 · Stage 1.5。System Performance ← Physical Equations ← Block Variables。

唯一实验依据为 Stage 1 配置的哈希快照：10 MHz、N=8、80 MHz，BW 150–300 kHz、PM≥50°；UGF 为诊断。Stage 1 的 draft=true 保留，仅在本阶段固定输入；未把旧 MATLAB 的 100–400 kHz / 45° 混入本轮目标。

|系统量|方程链|共同变量|当前证据层级|
|---|---|---|---|
|条件输出频率、调谐电压|E_FREQ_PLAN → E_TUNING|N、fref、f0、Kvco、Vmin/Vmax|解析与数值；32 个事件点中的条件稳态检查|
|BW|E_KPFD → E_LF → E_OPEN → E_CLOSED → E_BW|Icp、Rz、C1、C2、Kvco、N|连续 M1 数值一致性；无事件注入测量|
|PM|E_KPFD → E_LF → E_OPEN → E_UGF → E_PM|同上|连续 M1 数值一致性；无事件注入测量|
|UGF（诊断）|E_OPEN → E_UGF|同上|连续 M1 数值一致性|

机器注册表为 `configs/PLL_EQUATION_REGISTRY_V1.json`，含每条公式的输入/输出、单位、层级、来源绝对路径/SHA、实现符号和证据。下面逐项给出 What / How / Domain / Evidence / Limitations。

## E_FREQ_PLAN · Frequency planning

**What**：PLL frequency target follows ideal integer divider relation.

**公式**：`f_target=N*f_ref`

**How**：Multiply fixed N and reference frequency; no acquisition assumption needed for the algebra. 输入：N, f_ref；输出：f_target。

**Domain**：N positive integer; f_ref>0。单位/转换：Hz; N dimensionless。

**Evidence**：来源 `F_FREQ_PLAN; model/solve_tuning_point.m`；实现 `pll_allocation/physics_mapping/model.py::M1Evaluator.evaluate`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：No claim the transient actually reaches target.

## E_TUNING · VCO lock point and local gain

**What**：Static control voltage necessary to produce the frequency plan.

**公式**：`f(V)=f0+Kvco*V; Vreq=(f_target-f0)/Kvco; Kvco_local=Kvco`

**How**：Solve linear VCO frequency law with f0 at zero volts, not the v1 V0 anchor. 输入：f_target, f0, Kvco, Vctrl_min, Vctrl_max；输出：Vctrl_required, Kvco_local。

**Domain**：Vmin<Vreq<Vmax for M1; positive f(V) throughout declared voltage domain。单位/转换：Hz; V; Hz/V; angular gain = 2*pi*Kvco_local rad/s/V。

**Evidence**：来源 `F_TUNING; model/vco_model.m; model/solve_tuning_point.m`；实现 `pll_allocation/physics_mapping/model.py::M1Evaluator.evaluate`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：No curvature; no voltage-dependent gain; rail point lacks two-sided small-signal neighborhood.

## E_KPFD · PFD/CP small signal slope

**What**：Average injected current derivative with respect to phase error about ideal lock.

**公式**：`Kpfd=Icp/(2*pi)`

**How**：A phase error delta_phi gives pulse width delta_phi/(2*pi*f_ref), so mean current is Icp*delta_phi/(2*pi). 输入：Icp；输出：Kpfd。

**Domain**：Iup=Idown=Icp>0; zero mismatch/leakage/reset/q0。单位/转换：A/rad; phase_error=reference-minus-feedback radians。

**Evidence**：来源 `F_KPFD; model/pll_linear_kernel.m`；实现 `pll_allocation/physics_mapping/model.py::M1Evaluator.evaluate`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：No nonideal CP bias equilibrium, switching spikes or one-sided mismatch linearization.

## E_LF · Loop filter impedance

**What**：Control-node voltage divided by injected CP current.

**公式**：`Z=(1+s*Rz*C2)/(s*(C1+C2)+s^2*Rz*C1*C2)`

**How**：Eliminate vc2 from C1*s*vctrl=i-(vctrl-vc2)/R and C2*s*vc2=(vctrl-vc2)/R. 输入：Rz, C1, C2, f_offset；输出：Zlf。

**Domain**：positive ideal Rz/C1/C2; Cload=Gload=0; finite f_offset>0。单位/转换：Ohm; s=j*2*pi*f_offset rad/s。

**Evidence**：来源 `F_LF_TF; model/loop_filter_model.m; model/pll_linear_kernel.m`；实现 `pll_allocation/physics_mapping/model.py::_response`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：No dynamic VCO input load, CP output resistance, dielectric loss or parasitics.

## E_LF_ZP · Loop filter zero and poles

**What**：Lead zero, integrator and extra high-frequency pole of the passive LF.

**公式**：`wz=1/(Rz*C2); wp=(C1+C2)/(Rz*C1*C2); poles={0,-wp}`

**How**：Factor impedance numerator and denominator; wp/wz=1+C2/C1>1. 输入：Rz, C1, C2；输出：fz, fp。

**Domain**：positive ideal RC。单位/转换：fz=wz/(2*pi) Hz; fp=wp/(2*pi) Hz; s poles rad/s。

**Evidence**：来源 `F_LF_TF; characterization/characterize_loop.m`；实现 `pll_allocation/physics_mapping/model.py::M1Evaluator.evaluate`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：Frequency labels are positive magnitudes, not signed s-plane pole values.

## E_OPEN · Open loop transfer

**What**：Phase-domain forward path with ideal divider feedback.

**公式**：`L=Kpfd*(2*pi*Kvco_local)*Zlf/(N*s)`

**How**：Multiply current/phase slope, current-to-voltage LF, integrating VCO angular gain and 1/N. 输入：Kpfd, Kvco_local, Zlf, N, f_offset；输出：L。

**Domain**：Integer-N CPPLL; symmetric ideal CP; no leakage/q0/reset delay; linear positive-frequency increasing VCO; C1 shunt || series Rz-C2; no extra load; interior feasible tuning; locked small signal; continuous-time linearization; no sampling equivalence claim。单位/转换：dimensionless; explicit Hz/V to rad/s/V conversion。

**Evidence**：来源 `F_LOOP; model/pll_linear_kernel.m`；实现 `pll_allocation/physics_mapping/model.py::_response`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：Continuous model does not include event sampling, acquisition or nonlinear saturation.

## E_CLOSED · Normalized closed loop

**What**：Closed-loop normalized reference phase response.

**公式**：`T=L/(1+L); H_ref=N*T; T(0)=1`

**How**：Use negative-feedback denominator 1+L; output phase response is N times normalized T. 输入：L；输出：T。

**Domain**：Integer-N CPPLL; symmetric ideal CP; no leakage/q0/reset delay; linear positive-frequency increasing VCO; C1 shunt || series Rz-C2; no extra load; interior feasible tuning; locked small signal; continuous-time linearization; no sampling equivalence claim。单位/转换：dimensionless; normalized output/divider phase response。

**Evidence**：来源 `F_LOOP; model/pll_linear_kernel.m`；实现 `pll_allocation/physics_mapping/model.py::_response`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：Do not threshold absolute H_ref at 1/sqrt(2); do not infer time-domain lock.

## E_UGF · Unity gain frequency

**What**：Diagnostic unity-gain frequency.

**公式**：`|L(j*2*pi*UGF)|=1; first downward crossing`

**How**：8000-point log scan brackets one downward crossing; log-frequency bisection refines the root. 输入：L, f_offset；输出：UGF。

**Domain**：Integer-N CPPLL; symmetric ideal CP; no leakage/q0/reset delay; linear positive-frequency increasing VCO; C1 shunt || series Rz-C2; no extra load; interior feasible tuning; locked small signal; continuous-time linearization; no sampling equivalence claim; finite unique bracketed crossing。单位/转换：Hz; scan in log10(f); no angular frequency output。

**Evidence**：来源 `F_LOOP; characterization/characterize_loop.m`；实现 `pll_allocation/physics_mapping/model.py::M1Evaluator.evaluate`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：No bracket or multiple downward brackets => NUMERICAL_FAILURE; generic multiple-crossing handling is not a phase-margin theorem.

## E_BW · Closed loop bandwidth

**What**：First high-frequency downward half-power amplitude crossing of normalized T.

**公式**：`|T(j*2*pi*BW)|=1/sqrt(2)`

**How**：Same log-frequency bracketing and bisection, with a separate T residual from unity-loop crossing. 输入：T, f_offset；输出：BW。

**Domain**：Integer-N CPPLL; symmetric ideal CP; no leakage/q0/reset delay; linear positive-frequency increasing VCO; C1 shunt || series Rz-C2; no extra load; interior feasible tuning; locked small signal; continuous-time linearization; no sampling equivalence claim; stable loop; unique finite bracket。单位/转换：Hz; normalized -3.0103 dB amplitude criterion。

**Evidence**：来源 `F_LOOP; characterization/characterize_loop.m`；实现 `pll_allocation/physics_mapping/model.py::M1Evaluator.evaluate`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：Not UGF, not sampled-loop bandwidth, not measured by available event TB.

## E_PM · Phase margin

**What**：Phase distance to -180 degrees at unity-loop crossing.

**公式**：`PM=180+arg(L(j*2*pi*UGF))*180/pi`

**How**：Evaluate complex L again at refined UGF; ideal network phase is -180+atan(w/wz)-atan(w/wp). 输入：L, UGF；输出：PM。

**Domain**：Integer-N CPPLL; symmetric ideal CP; no leakage/q0/reset delay; linear positive-frequency increasing VCO; C1 shunt || series Rz-C2; no extra load; interior feasible tuning; locked small signal; continuous-time linearization; no sampling equivalence claim; valid UGF; unique crossing。单位/转换：degrees; arg radians converted exactly once。

**Evidence**：来源 `F_LOOP; characterization/characterize_loop.m`；实现 `pll_allocation/physics_mapping/model.py::M1Evaluator.evaluate`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：No nonideal delay margin; low PM does not make this strictly stable continuous ideal loop mathematically unstable.

## E_STABILITY · Continuous stability and domain

**What**：Routh-Hurwitz stability of the third-order continuous linearization.

**公式**：`D(s)=a*s^3+b*s^2+c*s+d; bc-ad=(Icp*Kvco/N)*Rz*C2^2>0`

**How**：All a,b,c,d positive and bc>ad; difference simplifies to positive gain*R*C2^2. 输入：Icp, Kvco, N, Rz, C1, C2；输出：Routh_bc_minus_ad。

**Domain**：positive parameters; ideal subset。单位/转换：a=R*C1*C2; b=C1+C2; c=(Icp*Kvco/N)*R*C2; d=Icp*Kvco/N。

**Evidence**：来源 `F_LOOP; model/pll_linear_kernel.m; Stage 1 characteristic coefficients`；实现 `pll_allocation/physics_mapping/model.py::M1Evaluator.evaluate`。
本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。

**Limitations**：Does not prove event/sampled stability or global capture. Negative R/gain are outside the declared model.

## 语义、稳定性和交越专项审核

Kvco 输入是 Hz/V，进入相位积分增益时仅乘一次 2π。f0 是 0 V 截距；旧 v1 的 V0 锚点需要显式转换。LF 连接是 C1 并联 Rz-C2 串联支路，禁止交换 C1/C2。CP 的 q0、leakage、mismatch、reset 均显式为零，非零时不能借理想 Kpfd 验收。相位约定 ref-div rad，与旧 v1 符号相反。

正值理想网络中，|L|²=K0²(1+ω²/ωz²)/(ω⁴(1+ω²/ωp²))。对 logω 的导数为 2A−4−2B<−2，其中 0<A,B<1，因此 |L| 严格递减，正频轴仅一个单位增益交越。BW 的 x=ω² 多项式系数符号为 +、任意、−、−，恰有一次符号变化，因此仅一个正根。

三阶 Routh 差值 bc−ad=(Icp*Kvco/N)*Rz*C2²>0。声明的正值理想域不会产生连续模型不稳定点；低 PM 属于规格违例，不能贴“连续不稳定”标签。负 R 或负增益的扩展是域外反例，程序拒绝它们。该证明不能外推到采样/延迟/非理想系统。

数值测试对无交越、多个下降交越和非有限残差均要求 NUMERICAL_FAILURE。当前公式族中多交越由解析关系排除，泛化到别的拓扑必须重新处理相位展开、交越选择及稳定性判据。

独立数值路径验证的是方程实现正确性，不能把两个同源公式实现的吻合称为行为真实性。BW/PM 的外部行为误差目前为空值/NOT_ESTABLISHED，而不是零。
