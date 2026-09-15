# PLL 行为级建模原型报告

## 1. 当前结论

Python 和 MATLAB 都可以实现一个可运行的 Integer-N CPPLL 行为级模型。本次原型已经完成并通过执行验证。

当前模型适合：

- 系统级 PLL 闭环探索；
- VCO tuning curve、Kvco、phase noise、power 的行为建模；
- lock time、output frequency、integrated jitter 的快速计算；
- 后续 SystemSpec → VCO Required Spec 映射的 simulator backend 原型；
- Python 与 MATLAB 的交叉验证。

当前模型不等同于 transistor-level PLL 电路仿真，也不宣称替代 SpectreRF 的 PSS/PNOISE。

## 2. 文件

Python 模型：

[v1/model/pll_behavioral.py](F:/LJP/概伦AI/PLL_AGENT/v1/model/pll_behavioral.py)

Python 运行入口：

[run_pll_demo.py](F:/LJP/概伦AI/PLL_AGENT/run_pll_demo.py)

MATLAB 模型：

[matlab/pll_behavioral_demo.m](F:/LJP/概伦AI/PLL_AGENT/matlab/pll_behavioral_demo.m)

示例输出：

[results/python_pll_demo.json](F:/LJP/概伦AI/PLL_AGENT/results/python_pll_demo.json)

[results/matlab_pll_demo.json](F:/LJP/概伦AI/PLL_AGENT/results/matlab_pll_demo.json)

## 3. 模型结构

模型固定为 Integer-N CPPLL：

~~~text
Reference
   ↓
Averaged PFD/CP error
   ↓
Effective PI loop filter
   ↓
Nonlinear VCO
   ↓
Divider N
   └──────── feedback
~~~

仿真以 reference-clock cycle 为离散步长，不采样 GHz 级 RF waveform。每个 reference cycle 执行：

~~~text
fosc = VCO.frequency(Vctrl, temperature)
fdiv = fosc / N
error = (N·fref - fosc) / (N·fref)
integrator = integrator + error
Vctrl = Vctrl + kp·error + ki·integrator
~~~

这个模型是 averaged phase-domain CPPLL。cp_current、R 和 C 在参数中保留，当前 kp、ki 使用 normalized effective gains；后续可以再把它们替换为由真实 CP/loop-filter 方程推导的参数。

## 4. VCO 行为模型

VCO tuning curve 使用二阶非线性：

~~~text
fosc(Vctrl, T)
  = f0
  + K1·(Vctrl - V0)
  + K2·(Vctrl - V0)^2
  + temperature_shift
~~~

因此：

~~~text
Kvco(Vctrl)
  = K1 + 2·K2·(Vctrl - V0)
~~~

这使 Kvco 随 control voltage 变化，不是固定常数。

VCO phase noise 使用带 context 依赖的 synthetic model：

~~~text
PN = PN_1MHz
   + a_vctrl·(Vctrl - V0)
   + a_temp·(T - T0)
   + a_power·log10(P/P0)
   + offset_slope
~~~

它具有以下行为：

- Vctrl 改变时，phase noise 改变；
- temperature 改变时，phase noise 改变；
- power 改变时，phase noise 改变；
- offset 低于 1 MHz 和高于 1 MHz 时使用不同斜率。

这些 dependency 是为了后续验证 Contract vs Oracle 分离而设置的 synthetic ground truth。

## 5. 当前输出指标

模型返回：

~~~text
output_frequency_hz
integrated_jitter_s
lock_time_s
power_w
phase_noise_100khz_dbc_hz
phase_noise_1mhz_dbc_hz
phase_noise_10mhz_dbc_hz
kvco_hz_per_v
loop_bandwidth_hz
final_relative_frequency_error
final_vctrl_v
~~~

同时返回 SystemTB 后续需要的 context：

~~~text
vctrl_min_v
vctrl_max_v
fosc_min_hz
fosc_max_hz
temperature_c
vdd_v
divider_n
f_ref_hz
~~~

Integrated jitter 使用 VCO phase noise 通过一个简化的 PLL high-pass noise transfer 后进行频率积分：

~~~text
|H_vco(f)|² = f² / (f² + f_loop²)
~~~

再将积分得到的 phase variance 换算为 time jitter。这个结果适合 deterministic candidate comparison，不是 PSS/PNOISE 的 signoff 结果。

## 6. 执行方式

Python：

~~~powershell
python .\run_pll_demo.py --output .\results\python_pll_demo.json
~~~

MATLAB：

~~~powershell
$matlab = (Get-Command matlab).Source
& $matlab -batch "addpath('matlab'); r=pll_behavioral_demo('results/matlab_pll_demo.json'); fprintf('locked=%d fGHz=%.9f lock_us=%.6f jitter_fs=%.6f vctrl=%.9f\n', r.locked, r.simulation_cycles, r.metrics.output_frequency_hz/1e9, r.metrics.lock_time_s*1e6, r.metrics.integrated_jitter_s*1e15, r.metrics.final_vctrl_v);"
~~~

## 7. 本次运行结果

Python：

~~~text
Model: averaged_integer_n_cppll_v1
Mode: reference_cycle_phase_domain
Locked: True
Simulation cycles: 5000
Output frequency: 5.000000 GHz
Lock time: 36.52 us
Integrated jitter: 83.3673 fs
Final VCO control: 0.803461 V
~~~

MATLAB：

~~~text
Locked: True
Simulation cycles: 5000
Output frequency: 5.000000 GHz
Lock time: 36.52 us
Integrated jitter: 83.3673 fs
Final VCO control: 0.803461 V
~~~

Python 与 MATLAB 的比较：

~~~text
|output_frequency_python - output_frequency_matlab|
  ≈ 9.5e-7 Hz

|jitter_python - jitter_matlab|
  ≈ 1.3e-29 s

|lock_time_python - lock_time_matlab|
  = 0
~~~

这个差异来自 MATLAB 和 Python 的浮点运算顺序，远小于任何工程级容差。

## 8. 非线性和 context 验证

在 25 °C 下，VCO 局部行为为：

~~~text
Vctrl = 0.30 V → fosc = 4.158 GHz, Kvco = 1.32 GHz/V
Vctrl = 0.50 V → fosc = 4.450 GHz, Kvco = 1.60 GHz/V
Vctrl = 0.80 V → fosc = 4.993 GHz, Kvco = 2.02 GHz/V
Vctrl = 1.00 V → fosc = 5.425 GHz, Kvco = 2.30 GHz/V
~~~

这证明 tuning curve 和 Kvco 不是严格线性或常数。

在 1 MHz offset、25 °C 下，phase noise 随 Vctrl 变化：

~~~text
Vctrl = 0.30 V → PN ≈ -117.63 dBc/Hz
Vctrl = 0.80 V → PN ≈ -113.71 dBc/Hz
Vctrl = 1.00 V → PN ≈ -112.13 dBc/Hz
~~~

在不同温度下，PLL 仍然能够锁定，但 jitter 发生变化：

~~~text
T = -40 °C → lock time ≈ 36.60 us, jitter ≈ 73.82 fs
T = 125 °C  → lock time ≈ 36.42 us, jitter ≈ 100.65 fs
~~~

这些结果足以支持后续构造：

~~~text
Contract v0: PN = constant
Oracle:      PN = PN(Vctrl, foffset, temperature)
~~~

## 9. 这版模型与项目架构的对应关系

当前代码已经对应以下长期架构对象：

~~~text
VCOParams
  → VCO realized behavioral instance / oracle parameterization

CPPLLParams
  → fixed system architecture and loop configuration

simulate_cppll()
  → SystemTB-like deterministic evaluator

VCO methods
  → VCO characterization and behavior evaluation

integrated_vco_jitter_s()
  → system metric approximation

history + context
  → trajectory and operating-context evidence
~~~

后续需要再补上的模块：

~~~text
Contract Predictor
Spec Interpreter
VCO BlockTB
Residual engine
Finite-difference sensitivity engine
Required Spec Boundary search
Deterministic Spec Allocator
Optional Problem 1 / Problem 2 Agent hooks
~~~

## 10. 当前限制

1. PFD/CP 目前使用 averaged frequency-error representation，没有建模 UP/DOWN pulse width、dead zone、current mismatch 和 reference spur；
2. loop filter 使用 normalized effective PI update，R/C/Icp 尚未完整映射到连续时间或离散时间物理方程；
3. VCO phase noise 是 synthetic analytic curve，不是 transistor-level PNOISE；
4. integrated jitter 只包含 VCO noise，尚未加入 reference、PFD/CP、loop-filter 和 divider noise；
5. 没有建模 fractional-N、spur、cycle-slip、capture/pull-in range 和 nonlinear PFD state machine；
6. 没有 PVT Monte Carlo、yield 和 uncertainty propagation；
7. 当前还没有 Required Spec Boundary 搜索；
8. 当前还没有 Contract Predictor 与独立 Oracle 的自动 refinement loop；
9. 当前 MATLAB 与 Python 已验证同一方程，但尚未完成复杂模型的跨 backend 自动测试。

## 11. 下一步建议

建议按以下顺序把当前原型推进为 V1.0：

1. 固定 vco_mapping_01 的 SystemSpec；
2. 增加 VCO Spec Requirement 数据结构；
3. 增加 Spec Interpreter，把 PN、Kvco、tuning range 和 power requirement 编译成约束；
4. 增加 VCO BlockTB，在 SystemTB 抽取的 Vctrl/fosc envelope 上检查 requirement；
5. 增加 residual 和 finite-difference sensitivity；
6. 增加单变量或少量变量的 required-boundary search；
7. 用 realized VCO instance 重新运行 SystemTB；
8. 输出 required boundary、recommended spec、selected candidate 和 trajectory；
9. 用独立 Contract Predictor / Oracle 旁路验证 Contract deficiency；
10. 最后再把 Problem 1 / Problem 2 Agent 接入 action proposer。

当前原型已经证明：Python 和 MATLAB 足以支撑一个可运行的 PLL 行为级 simulator backend，下一阶段可以在这个基础上实现可信的 SystemSpec→VCO Spec 映射。
