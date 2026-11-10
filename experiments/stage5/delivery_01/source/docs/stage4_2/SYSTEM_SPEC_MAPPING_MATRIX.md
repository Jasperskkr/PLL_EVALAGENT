# SystemSpec → BlockSpec 映射能力矩阵

2026-11-05，Stage4.2研究审查版。权威输入为`configs/pipeline_stage3a.json`绑定的Stage1.5快照，未修改。独立文件`SYSTEM_SPEC_STAGE1_5.json`与模型内SystemSpec内容相同。其原始`draft=true/source=not frozen`元数据保留：这里“冻结”指Stage3A.1运行快照和哈希固定，不代表把原草案追认为最终产品规格。

当前正式判决仅含：输出频率80MHz，容差1e-6Hz；BW 150–300kHz；PM≥50°。UGF为诊断量。RUR、静态相位误差、锁定时间/捕获、jitter/power均未增设为SystemSpec硬约束。M2协议中的捕获阈值是测量可靠性条件，不能替换频率容差。

分类表示**当前完整映射能力**，不是只看有无正向公式。ANALYTICAL_INVERSE=有条件解析反推；NUMERICAL_INVERSE=需要公式和有界数值求解；PHYSICS_SCREENING=仅必要条件/简化筛选；BEHAVIORAL_ONLY=主要依靠行为测量；UNSUPPORTED=缺少定义、参数或可信机制。

|指标 / 单位 / 当前约束|定义与相关参数|正向公式及来源|逆向能力与方法|M1状态|M2状态与证据|适用条件、局限及缺口|
|---|---|---|---|---|---|---|
|output_frequency_Hz / Hz；80MHz±1µHz|锁定时fout=N·fref；N/fref固定，f0/Kvco决定可调谐性|E_FREQ_PLAN、E_TUNING；F=80MHz，Vreq=(F−f0)/Kvco|ANALYTICAL_INVERSE：检查固定频率计划；给定Vreq和Kvco可解f0。不能把固定N当可选参数|条件静态频率/电压支持|稀疏稳态跟踪支持；原Protocol1.1有限窗口无法认证1µHz，正式UNKNOWN|内部调谐是捕获必要条件；需要更严谨频率不确定度验证、PVT/曲率后才扩展|
|Vctrl_required_V / V；诊断及域检查|f0为零伏截距，Kvco为Hz/V；Vmin<Vreq<Vmax|E_TUNING|ANALYTICAL_INVERSE：f0=F−Kvco·V，或Kvco=(F−f0)/V，最后与原轴域求交|支持|Stage1.5 32点频率/控制检查，26点条件一致；Stage4三个点支持局部调谐|不新增“中心电压”规格；rail不具备双侧线性化邻域；VCO非线性未覆盖|
|BW_Hz / Hz；150–300kHz|归一化T=L/(1+L)唯一向下−3.0103dB交越；Icp/Kvco/Rz/C1/C2/N|E_KPFD、E_LF、E_OPEN、E_CLOSED、E_BW|NUMERICAL_INVERSE：枚举离散C，选择形状，求BW/UGF比根，再还原R和增益；或既有SLSQP|支持独立扫描/二分和等价多项式|Protocol1.1完整事件TB独立局部BW测量；Nominal/Agent/边界见证据快照|不是UGF；连续divider phase与edge-only观测并未证明等价；未获得全域误差界|
|PM_deg / °；≥50°|连续L单位交越处180°+argL；同上动态参数|E_PM/E_UGF；PM=atan x−atan(x/q)|NUMERICAL_INVERSE：解析PM上界/x区间只做必要传播，完整BW/R/gain/tuning交集数值求解|支持理想连续PM|Stage4三例局部Series/Clamp数值收敛；周期正式PM仍UNKNOWN|需要谐波返回矩阵截断误差、广义Nyquist/Floquet及与当前PM定义的桥接；正Routh不等于PM规格通过|
|UGF_Hz / Hz；未启用|唯一向下\|L\|=1；动态参数|E_UGF；给定C,x,ωu可条件还原R和Icp·Kvco|NUMERICAL_INVERSE（数学问题）；现有官方policy无UGF目标字段，条件重建仅研究工具。不能宣称已部署UGF分配策略|支持正向/条件代数|Stage4局部交越诊断有值，正式UNKNOWN|不以BW替换；有公式不等于完整约束求解接口；不新增UGF硬约束|
|RUR / 无量纲；未启用|配置/源码无正式定义，不能自行选fref/UGF或UGF/fref方向|无正式Equation ID|UNSUPPORTED：先批准定义、方向、边界与物理用途|仅有UGF_over_fref诊断字段，未称RUR|无认证|频率比不是采样误差/稳定性保证，不套用未经验证经验上限|
|Static Phase Error / °；未启用|稳态wrapped ref−feedback；Icp与q0/leakage/mismatch/reset有关|补充R_CHARGE_BALANCE：q0+Ibranch·Δt=0，φ=360frefΔt；源`_legacy/physics/cp.py`|PHYSICS_SCREENING：有批准相位预算时可换算允许符号电荷；当前q0/非理想固定0，无非零误差预算分配能力|正式M1无该metric；理想零偏置仅平衡关系|事件尾部相位可观测、用于捕获门；未独立启用静态误差判决|需一致电荷/泄漏符号、reset/mismatch/负载/死区模型；旧proxy-load q0不能静默混入当前M1|
|lock_time_s / s；未启用|Protocol1.1最早terminal连续有效block起点；依赖完整参数及初值/窗口|M1无锁定时间公式；E_TUNING/E_STABILITY仅筛选|BEHAVIORAL_ONLY：必要调谐检查后完整冷启动M2；不能由PM或1/BW保证时间|不支持可信锁定时间预测/逆解|已有条件测量，1µs记录分辨率、两步长比较，窗口160µs及指定初值|需多初值/失谐、cycle-slip和失败原因分类；无全局捕获域/时间界|
|Capture / 标签；未启用|CAPTURED_WITHIN_WINDOW等窗口条件事件；同上|必要调谐/rail条件，没有充分解析反解|BEHAVIORAL_ONLY|不预测全局捕获|原协议支持窗口内判别；NOT_CAPTURED不代表不可锁定|暖启动BW不证明冷启动捕获；不为得到PASS改窗口门限|
|Jitter / s；未启用|需积分频带与时间/相噪观测定义；参考/CP/LF/VCO/Divider噪声PSD|无可信噪声模型|UNSUPPORTED|无|无|缺少噪声源、传递、相关性和测量协议；理想无噪声轨迹不能当零抖动能力|
|Power / W；未启用|各块供电与静态/动态损耗|无|UNSUPPORTED|无|无|Icp是CP脉冲幅值，不是系统总电流；缺供电/占空/振荡器/Divider功耗模型|

证据分层：①数学推导和单位；②本次数值一致；③历史M2有限点；④已覆盖的具体点/窗口；⑤尚未验证的域外和非理想推广。不能把①②升级为③④。当前没有可签发全部冻结SystemSpec M2 PASS的能力。

Agent可通过`PHYSICS_MAPPING_REGISTRY.json`查询每行的Equation IDs、版本/源码SHA、工具路径与置信边界；示例和下一步见[Readiness报告](BLOCK_SPACE_READINESS_REPORT.md)。本矩阵不替代正式SystemSpec或旧Equation Registry。
