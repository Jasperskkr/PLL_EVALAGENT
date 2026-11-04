# Stage 1 模型审查与语义合同

2026-11-04。已审查六份指定 MATLAB 文件及其 VCO、PFD/CP、LF、参数检查、历史交叉校验依赖；也已审查 Python contracts、behavioral 及两份 legacy physics 和 evaluation 实现。实际绝对路径、SHA256、复用方式、适用域见 `audit/source_manifest.json`。4835 个既有文件已写入 `audit/protected_before.json`。MATLAB 工程保持只读，本次不执行 MATLAB Runtime。

## 统一约定

新模块独立使用 `pll-physics-mapping-2.0` 参数信封，SystemSpec 使用研究草案 v0。输入必须显式带规范 SI 单位；Hz/V 与 rad/s/V 不自动混用。仅在明确公式处将 Kvco 乘 2π。变量详表见 `variable_mapping.csv`（随实现补齐，含默认值、实验域、角色、来源和冲突）。范围均是行为研究域，不声明器件能力。

|检查点|MATLAB v3.4 源码|Python v1 源码|Stage 1 选择及影响|
|---|---|---|---|
|Kvco|`vco_model`: Hz/V；相位导数为 rad/s|`de=Kvco/N*integral` 使用 cycles；PHYSICS 标明 Hz/V|保留 Hz/V，`omega_gain=2π*Kvco_local`|
|f0|`f=f0+Kvco*V+Kvco2*V²`，0 V 截距|`f=f0+Kvco*(V-V0)`，V0 处锚点|v2 f0 专指 0 V 截距。线性转换为 `f0_v2=f0_v1-Kvco*V0`，不得直接复制 f0。无隐式 v1 adapter|
|CP 电流|Iup=Icp(1+m/2)，Idown=Icp(1-m/2)，m=(Iup-Idown)/Icp；泄漏向 LF 注入为正|I_up、I_down 是带符号 timing 的正斜率；`q=q0+I(direction)*timing`|M1 仅 m=0；Iup=Idown=Icp，Kpfd=Icp/(2π)，对 ref-div 的弧度相位误差|
|q0/leakage|leakage 为独立有符号 A，无 q0|q0 单位 C，已含局部负载 DC 需求，严禁再扣漏电|M1 要求二者均为零；`Ileak/fref` 只是在纯恒定泄漏单项时的每周期电荷，不能替代一般 v1 q0|
|LF|CP/VCO 节点并联 C1，对地串联支路 Rz→C2；中间节点 vc2|同一连接，但 C1eff=C1+Cload；有限 Rload 的增量导纳省略，DC 需求在 q0|本阶段 Cload=Gload=0；有负载时 UNSUPPORTED，避免把 v1 的局部代理当成实测 VCO 输入导纳|
|reset|事件模型实际处理异步复位延迟；characterize 的 valid 标记仅 reset=0|reset 仅用作 timing 饱和上限，不能等价于事件模型|M1 仅 reset=0；任何非零延迟 UNSUPPORTED，不宣称小延迟可忽略|
|phase error|wrap(phi_ref-phi_div)，内部 rad，显示 deg|feedback-reference，内部 cycles，输出 deg|语义转换 `e_v2_rad=-e_v1_deg*π/180`；M1 采用负反馈，L 为正向通路环路增益，T=L/(1+L)|
|闭环 T|T=L/(1+L)，H_ref=N*T|v1 未验收连续频域指标|BW 定义为归一化 T（DC=1）首次下降到 1/√2；不能用 H_ref 绝对幅度 -3 dB，也不能用 UGF 代替 BW|

## 本阶段公式与前提

固定 Integer-N CPPLL；N 为正整数，fref>0。`f_target=N*fref`。支持线性、全电压域频率为正且单调增加的 VCO：`Vreq=(f_target-f0)/Kvco`，`Kvco_local=Kvco`；曲率 Kvco2 非零暂不支持，不代入理想线性近似。范围外无锁定点为 OUT_OF_DOMAIN；端点可满足静态调谐，但电压裕量为零，不存在双侧小信号邻域，因此不验收 M1 环路指标。

理想正值 Rz、C1、C2：

`Zlf(s)=(1+s*Rz*C2)/(s*(C1+C2)+s²*Rz*C1*C2)`，单位 Ω。

`fz=1/(2π*Rz*C2)`；极点在 s=0 和 `s=-(C1+C2)/(Rz*C1*C2)`，fp 为该非零极点频率的正值。

`L=Kpfd*(2π*Kvco_local)*Zlf/(N*s)`；`T=L/(1+L)`。连续时间、已锁定、小信号、对称理想 CP、无 reset/leakage/q0/负载是必要前提。M1 不证明捕获、时间域锁定、采样环路、噪声、功耗或器件实现。频率扫点为正有限值；没有被包围的有效交越点时 NUMERICAL_FAILURE，不能返回 PASS。

闭环特征式为 `Rz*C1*C2*s³+(C1+C2)*s²+(Icp*Kvco/N)*Rz*C2*s+Icp*Kvco/N`。实现使用三阶 Routh 条件检查稳定性，交越使用 log-frequency 扫描加二分收敛，不依赖 MATLAB 或 SciPy。扫频边界沿用 MATLAB characterize 的默认尺度；边界可显式收紧以验证缺失交越的错误路径。M1 数值 OK 仅表示该连续模型计算完成。

## 原模型潜在风险（只记录，不改原件）

1. `characterize_loop.m` 的 `valid_locked_linearization` 检查 tuning、mismatch、reset，但未检查 `cp_leakage_A`；`pll_linear_kernel.m` 始终使用理想 Icp/(2π)，未解带泄漏静态偏移。本模块非零 leakage 返回 UNSUPPORTED，避免把偏置工作点不明的结果当成有效 PM/BW。
2. 同一 MATLAB 函数在 valid 标记为 false 时仍能输出非理想条件下的理想数值；其调用者必须主动看标记。新模块在这种情况下不给系统指标数值。
3. MATLAB tuning solver 可返回电压边界点；characterize 仍标 tuning feasible。对硬限幅 VCO，边界缺乏双侧线性邻域，本阶段比该标记更严格。
4. `pll_linear_kernel` 只算连续时间线性化；即使交越接近 fref，也不能由数学计算自动推定采样事件模型等价。新接口在结果中固定标注连续模型的适用范围，并报告 UGF/fref、BW/fref，不扩展为 M2 验收。
5. 历史 `python_crosscheck_results.json` 明写 MATLAB_RUNTIME_NOT_EXECUTED。参考点 PM=56.44269021253223°、UGF=138176.4411317168 Hz、BW=222379.18349260243 Hz 仅作为历史 Python 数值锚点。

## 审查后的实施边界

只适配 F_FREQ_PLAN、F_TUNING、F_KPFD、F_LF_TF、F_LOOP 的公式；不复制 MATLAB 文件为运行依赖，不导入 v1 合同或行为内核。独立 v2 配置支持 range/fixed/choices、单位、角色、来源；选中的候选仍须经过有效域检查，范围内不保证有锁点。M0/M2 接口保留但执行返回 UNSUPPORTED。此次没有 LLM 调用、搜索策略或完整行为 TB；以后 M2 接入后才可能形成 Verified JointBlockSpec。
