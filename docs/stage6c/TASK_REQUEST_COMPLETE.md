# Stage 6C — Physics-Guided PLL Behavioral Noise & Nonideal Verification

以下为用户澄清回复的结构化任务转录，部分条款合并表述，不作为逐字原文。完整原文以本对话该条用户回复为准；它取代截断Stage7正文。文件名沿用完整任务标识，不能据此声称已导出完整对话。

## 0. 你的角色与本阶段研究目标

你是本项目的 PLL 行为级建模、噪声分析、数值仿真及优化算法开发工程师。

本项目的研究目标是：

**Physics-Guided Multi-Spec PLL Block Allocation with Behavioral Verification and Feedback**

本阶段希望在不依赖晶体管级仿真、PDK 或真实 PLL IP 的情况下，通过物理合理、数值可信的行为级模型，实现：

SystemSpec → M1 Physics Mapping → Deterministic Allocation → Nonideal M2 Verification → Feedback → Joint Reallocation。

当前优先考虑四类系统指标：

* BW：闭环 −3 dB 带宽。
* PM：连续时间小信号相位裕量。
* Stability：局部稳定性、指定条件下的非线性锁定与扰动恢复。
* Noise / Jitter：输出相位噪声谱与指定 Offset 积分频段内的 RMS Time Jitter。

**核心任务不是重新设计 Agent，也不是立即开展晶体管级 Sizing，而是完善 M1/M2 的物理建模与行为验证。**

必须保留 Stage 6B 已有的 Analytical Solver、SLSQP、Sensitivity、确定性局部搜索、M2 Feedback 和统一 Pipeline。

不要创建第二套长期并行的 Allocation/Pipeline。

## 1. 开发前必须完成的源码审计与工程保护

首先检查实际 Git 工作树和已有代码。

重点查看：

* `pll_allocation/physics_mapping/model.py`
* `pll_allocation/physics_mapping/registry.py`
* `pll_allocation/allocation/allocate.py`
* `pll_allocation/allocation/multispec_constraints.py`
* `pll_allocation/allocation/multispec_search.py`
* `pll_allocation/verification/kernel.cpp`
* `pll_allocation/verification/simulator.py`
* `pll_allocation/verification/measure.py`
* `pll_allocation/verification/verify.py`
* `pll_allocation/pipeline.py`
* 现有 Stage 6B 实验和测试。

注意：历史交接包中 Stage 6B 可能保存在 `source_variants/stage6b/`，而不是正式 `repo/` 主线。

必须先判断实际工作树的状态，不能假设 Stage 6B 已经合入 master。

执行要求：

1. 检查 HEAD、branch、dirty worktree、关键源码 SHA 和 Stage 6B 真实实现位置。
2. 在安全的隔离分支或工作树中开发，不破坏现有结果。
3. 不使用 `git reset --hard`、`git clean`、自动 stash 或强制覆盖。
4. 不覆盖 Stage 6A/6B 冻结实验、配置、波形和报告。
5. 新实验采用独立 Stage 6C 路径。
6. 不修改原有理想 M1/M2 的数值语义，除非发现明确 Bug，且能通过独立证据证明并提供兼容方案。
7. 原有 M2 的 native DLL 构建身份与 SHA 检查必须保留；新内核应有自己的构建和身份验证机制。

**第一项交付：** 简短的 `STAGE6C_BASELINE_AUDIT.md`，说明复用模块、新增模块、现有模型边界及工程风险。

完成审计后，按下面顺序逐步开发。每一阶段通过验收后再继续，不允许一次性大规模改写所有模块。

## 2. Phase A — M1 Noise Physics Mapping

### 2.1 保留原有连续时间模型

当前 PLL 为固定 Integer-N Charge-Pump PLL：

* Reference：10 MHz。
* N = 8。
* 输出频率：80 MHz。
* PFD/CP + Rz/C1/C2 Passive LF + VCO + Divider。
* 现有六参数 BlockSpec：Icp、Rz、C1、C2、f0、Kvco。

当前 M1 使用：

Kpd = Icp / (2π) [A/rad]

K0 = 2π Kvco [rad/(s·V)]

L(s) = Kpd K0 ZLF(s) / (N s)

继续复用原有 BW/PM/UGF 评价函数。

### 2.2 新增独立 Noise Mapping 模块

建议在 `physics_mapping/` 下新增 Noise Model，不直接破坏冻结的 `model.py`。

至少支持以下噪声源：

**Reference Phase Noise**

输入谱：S_phi_ref(f)，单位 rad²/Hz。

传递函数：H_ref(s) = N L(s) / (1+L(s))

**VCO Intrinsic Phase Noise**

输入谱：S_phi_vco(f)，单位 rad²/Hz。

传递函数：H_vco(s) = 1 / (1+L(s))

**CP Equivalent Current Noise**

输入谱：S_i_cp_eff(f)，单位 A²/Hz。

传递函数：H_cp(s) = [K0 ZLF(s) / s] / [1+L(s)]

必须明确这是连续时间、等效小信号 CP 电流噪声，不自动等于实际门控 UP/DOWN 噪声源强度。

**Loop Filter Resistor Thermal Noise**

Rz 的单边热噪声 PSD：S_v_R = 4 kB T Rz。

对于现有 LF：D_R(s) = C2 / [C1+C2+sRzC1C2]

H_R(s) = [K0/s] D_R(s) / [1+L(s)]

使用独立节点方程或电路网络解析参考检查这一传递函数。

不可直接把 4kBTRz 当作 LF 控制节点噪声谱。

### 2.3 Noise Profiles

新增版本化 Noise Profile 配置，明确提供：

* Reference Phase Noise PSD。
* VCO Intrinsic Phase Noise PSD。
* CP Effective Current Noise PSD。
* 电阻温度 T。
* Offset Frequency Grid。
* 积分下限和上限。
* PSD 单边约定及 SI 单位。
* 模型适用频段、来源、参数版本。
* 噪声源独立性或相关性假设。

第一版可支持：常量白噪声 PSD；以物理单位给出的分段对数频率 PSD；适用频段内的 VCO 1/f² 或 1/f³ 相位噪声模型。

严禁在未验证的情况下人为定义 Jitter_vco ∝ 1/Kvco 或 Jitter_cp ∝ 1/Icp。

初期将本征噪声谱作为冻结的研究性环境参数；改变 BlockSpec 通过闭环传递函数改变总 Jitter。

如需研究本征噪声随设计参数变化的情况，必须另建显式声明的参数化模型，并与固定源谱实验分开报告。

### 2.4 M1 输出指标

实现 S_phi_out(f) = Σ |Hi(j2πf)|² Si(f)，sigma_t = sqrt(∫ S_phi_out(f) df) / (2π f_out)。

返回各源输出相位噪声 PSD、总输出 PSD、Integrated RMS Jitter（s）、各源 Jitter 方差贡献、噪声占比及主导噪声源、Offset 频率/积分范围/单位/Profile ID、计算状态与有效域。

只在已声明的噪声源不相关时直接求和；相关源必须提供交叉谱模型，否则声明 UNSUPPORTED。

对于 SSB Phase Noise，使用约定 L(f) [dBc/Hz] ≈ 10log10[S_phi(f)/2]，仅在单边 PSD、小相位扰动等适用假设成立时使用。

### 2.5 Noise Sensitivity

实现无量纲归一化敏感度 ∂ln(Jitter)/∂ln(x)。对于 Icp、Rz、Kvco 等连续 BlockSpec 参数计算有限差分敏感度。C1、C2 采用离散候选对照，不伪造连续梯度。

区分 Transfer Sensitivity（固定本征 PSD 时改变环路）与 Intrinsic Noise Sensitivity（噪声谱自身对设计变量的依赖）。本阶段只要求第一项完整实现。

不得把没有物理依据的 Intrinsic Noise Sensitivity 默认为零并宣称已证明不存在耦合；应说明当前使用了冻结源谱假设。

### 2.6 M1 验收

至少包括：Noise=0 时积分 Jitter=0；独立噪声源功率谱按方差而非 RMS 幅度相加；PSD 强度扩大四倍单源 RMS Jitter 扩大两倍；参考低频传递接近 N 且 VCO 低频受抑制；VCO 高频趋近1；CP/LF 热噪声 SI 单位正确；网格加密积分收敛；参考解析或独立频域计算一致；原 BW/PM/UGF 回归无变化。输出 `M1_NOISE_MODEL_VALIDATION.md`。

## 3. Phase B — M2 非理想大信号模型

### 3.1 保留原有事件级闭环核心

现有 M2 包含 PFD/CP 边缘事件、两状态 LF、VCO 相位演化、理想 Divider、电压轨限、冷启动捕获、小信号频响测量。优先复用这些状态和事件机制。

现有 kernel 是固定时间网格加步内事件插值，不是严格自适应事件求解器。不得把它描述为精确事件求解器。

建议为新增非理想行为建立显式配置与受控仿真入口，关闭所有新增机制时必须保留原模型结果。

### 3.2 VCO 非线性调谐

支持研究级二次调谐模型，例如 f(V) = f0 + Kvco V + K2 V(V−V*)，其中 V* 是原线性模型的目标工作点。

要求 K2=0 退化原线性VCO、f(0)=f0、f(V*)=f_target、报告实际局部增益df/dV、全研究电压域频率为正、检查局部单调与调谐范围、限幅与频率模型一致。超域报 OUT_OF_DOMAIN 或 UNKNOWN，不静默裁剪冒充精确预测。

不要在 M1 中直接使用非零 K2 并绕过原有 UNSUPPORTED 检查。M1 可继续忽略 K2 的名义低保真模型，但记录忽略项。

### 3.3 CP 电流非理想

支持 Iup = Icp (1+δ/2)，Idown = Icp (1−δ/2)。优先实现 UP/DOWN 失配、电流随控制电压的可选一阶效应、可配置静态泄漏（若模型及测量可验证）、明确 PFD Reset Delay。

需要真实模拟 UP、DOWN 导通区间以及同时导通 Reset Pulse。不能简单在每步平均电流后加常量代替真实脉冲。检查总注入电荷、事件顺序及 LF 状态更新。

### 3.4 单机制消融

分别运行所有关闭、仅 VCO 非线性、仅 CP Mismatch、仅 Reset Delay、组合非理想。各项记录 BW、M1 PM、M2 捕获与恢复、LF Control Ripple、限幅、频率与稳态、事件和积分数值收敛。观察机制是否改变行为指标与排序，不事后挑参数让方法获胜。

## 4. Phase C — M2 随机噪声验证

### 4.1 随机噪声引擎

独立固定 RNG Seed，记录算法/生成器版本；每源独立随机序列；Enable/Disable、可重复仿真、谱参数/单位检查。不得用与dt无关的固定电压或相位扰动。

### 4.2 VCO White Frequency Noise

单边 S_f（Hz²/Hz）：Δphi_noise ~ N(0, (2π)² S_f Δt / 2)。相位具有积分累积性。验证自由VCO增量方差、方差随时间、PSD1/f²斜率、物理统计量dt收敛、同Seed重复。跨dt路径比较应共享布朗增量，不将两个独立轨迹差当确定性收敛。

### 4.3 CP Current Noise

单边白电流 S_i（A²/Hz）在有效导通τ内，Var(ΔQ)=S_i τ/2。优先实际UP/DOWN导通区间，源独立、同时导通处理正确、关闭不生门控噪声、记录各导通时长/注入电荷方差/设置，检查方差尺度。

M1等效CP PSD与M2门控噪声需要明确归一化/周期平均/独立校验。若未建立不调系数强行匹配，绝对一致性报告未完成。

### 4.4 LF Thermal Noise

由4kBTR开始，进入正确Rz/C1/C2支路并通过真实状态影响控制电压；不可直接在控制端叠加无网络关系的高斯噪声。

### 4.5 Reference Noise

至少一种明确谱定义的研究相位/时序噪声。说明边沿随机过程、相关性、单边谱转换和单调性；独立边沿抖动不能称任意连续相位谱。未验证1/f保持UNSUPPORTED。

### 4.6 噪声测量协议

独立于原160us捕获：确认锁定Warm-up、指定时长、Unwrapped Output Phase、残差定义、可信PSD估计、Frequency Resolution、积分Offset Band、Seed与聚合、Numeric Convergence、独立参考交叉检查。

随机Jitter与确定性Ripple/Spur分开；可同非理想Noise-Off基线辅助，说明适用条件，不任意删谱线。捕获相位RMS不作NoiseJitter，有限窗口不可分辨低Offset不认证。

### 4.7 随机验收

ReferenceOnly/VCOOnly/CPOnly/LFOnly/AllSources。先源谱/方差独立测试再完整PLL。小噪声理想条件比较M1/M2 PSD、各源趋势、积分Jitter、不同BW折中，解释偏差。CI使用独立随机实现样本，不能Welch重叠段当独立MonteCarlo。Jitter上限：CI上界满足PASS，下界违反FAIL，相交/不足UNKNOWN。统计区间不同于确定性BW包络。输出 `M2_NOISE_VALIDATION.md`。

## 5. Phase D — Stability 与 PM 证据

M1：连续PM、UGF、闭环极点与稳定诊断，必要Peaking。M2：指定初态捕获、扰动恢复、失锁/持续振荡、限幅/边界，必要多初态。有限时域PASS仅工程条件证据不等全局稳定。严格周期PM/Floquet未经独立数学数值验证继续UNKNOWN，M1PM不得标M2PM PASS。

## 6. Phase E — 接入 Stage 6B 联合分配

A–D通过后扩展原Multi-Spec Constraint Evaluator：增加 integrated_jitter_s、stability_diagnostic、nonlinear_recovery_status；保留 BW_Hz、PM_deg、Vctrl_required_V、lock_time_s。

每约束保存数值/单位、边界、M1/M2来源、模型版、NonidealityProfileID、NoiseProfileID、协议版、数值/统计不确定度、PASS/FAIL/UNKNOWN、原证据路径。

先全硬约束联合可行，再改善最小裕量或Jitter；不让某指标大改善补偿另项FAIL。M1给Analytical、BW/PM/Jitter预测、Sensitivity、SLSQPJoint；M2给行为BW、指定稳定、独立Jitter统计、误差反馈。反馈用现有DeterministicPatternSearch，可增Jitter物理方向；不得不可靠敏感度/单次随机决定方向。每调整重查全部约束；保留6B A/B/C，新版本不改历史。本轮不需真实LLM。

## 7. Phase F — 最小实验设计

开发前冻结场景/噪声/非理想/预算。

E0关闭新增机制，原M1/M2及6A/6B结果在定义容差内一致。E1四源M1/M2验证，单位/过程/频带/统计收敛。E2理想固定NoiseProfiles的BW/PM/Jitter联合分配，Analytical对SLSQP，解释选型变化。E3在E2候选加冻结VCO非线性/失配/Reset及组合，测偏差/稳定/Jitter，不事后调参数。E4比较A Analytical+M2，B Analytical+M1Sensitivity/SLSQP+M2，C B+FeedbackLocalSearch。

各实验记录首次/最终联合可行率、Jitter/裕量、M1/M2差、M2真实调用、seed/总时长、M1数、CPU/Wall成本、反馈前后参数、随机原测量/不确定度。同约束/Profiles/预算，不凭一个成功例证反馈价值，C没超过如实报。少量冻结场景每方法最多6新M2候选，SeedBundle/精度比较前确定；不足未完或UNKNOWN不降精度冒PASS。

## 8. 文献依据

优先公开原文：Kundert *Predicting the Phase Noise and Jitter of PLL-Based Frequency Synthesizers* https://designers-guide.org/analysis/PLLnoise%2Bjitter.pdf ；Kundert *Modeling Jitter in PLL-based Frequency Synthesizers* https://designers-guide.org/forum/Attachments/PLLjitter.pdf ；Hanumolu et al. *Analysis of Charge-Pump Phase-Locked Loops*,2004 https://doi.org/10.1109/TCSI.2004.834516 ；Homayoun/Razavi *On the Stability of Charge-Pump Phase-Locked Loops*,2016 https://doi.org/10.1109/TCSI.2016.2537823 ；Wang/Kennedy *A Random Pulse Modulation Approach to Modeling the Flicker and White Noise of the Charge Pump*,2022 https://doi.org/10.1002/cta.3211 ；Zou et al. *A CPPLL Hierarchical Optimization Methodology Considering Jitter, Power and Locking Time*,2006 https://doi.org/10.1145/1146909.1146919 。区分原文支持、工程近似、自主研究假设。

## 9. 最终交付

docs/stage6c：BASELINE_AUDIT、M1_NOISE_MODEL_SPEC、M1_NOISE_MODEL_VALIDATION、M2_NONIDEAL_MODEL_SPEC、M2_NOISE_VALIDATION、JOINT_ALLOCATION_EXPERIMENT、FINAL_RESEARCH_REPORT。

另源码、独立测试/数值/回归、VersionedConfig、复现脚本、原PSD/Jitter/波形/反馈、M2成本、GitDiff/文件清单。最终区分Implemented/NumericallyVerified/BehaviorallySupported/Unsupported/FutureWork。不要测试数量宣称物理成功。数值/统计/接口无法完成，停止最后可信阶段交成果/失败/建议，不填造数据。

## 10. 特别禁止

不晶体管/PDK，不人为造噪声关系，不优化器免费调源系数，不共享假设一致当器件精度，不M1PM当M2认证，不单次随机严格PASS，不固定方差忽略dt，不覆盖6A/6B，不平行Pipeline，不绕NativeIdentity/SHA，不自动merge master，不提前LLMAgent/BO/代理。

最终证明M1快速BW/PM/Jitter，独立M2发现物理行为差异，6B确定性反馈可据此审计JointReallocation。正确/解释/收敛/公平优先速度与增益。

用户补充：按这一版的要求，最好是这阶段任务完成后能收敛到主线内。
