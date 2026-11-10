# 数据继承目录与用途

完整绝对路径/字节数/扩展名统计见 `audit/source_inventory_before.json`。数据按模型与实验的身份继承，不凭文件夹名称拼装。历史训练/校准/独立留出角色不变。

|来源绝对路径|继承内容|新用途与限制|
|---|---|---|
|F:/LJP/概伦AI/PLL_SPEC_ALLOC_BASELINE/fixtures/public_initial/models.json|VCO L0_cal、公共工况、LF值、CP局部域|小型公开快照直接继承；VCO f0=79165465.36642776Hz，K=151136039.9333628Hz/V，V0=1.17V，电压域[1.13,1.21]V|
|F:/LJP/概伦AI/PLL_SPEC_ALLOC_BASELINE/fixtures/provenance.json|32个来源引用及提取语义|本轮全部SHA匹配；来源事实不是新的仿真|
|F:/LJP/概伦AI/PLL_SPEC_ALLOC_BASELINE/fixtures/feedback/provenance.json|65个来源引用，含CP加载校准和保留点|本轮全部SHA匹配；隐藏holdout不提供给Policy|
|F:/LJP/概伦AI/PLL_SPEC_ALLOC_BASELINE/tests/test_independent_evaluator.py|24个独立corrected MATLAB案例的期望数值、来源SHA|只用于验证侧回归；不作为候选答案输入|
|F:/LJP/概伦AI/PLL_SPEC_ALLOC_BASELINE/verifier-reports/independent_matlab_comparison.json|24组完整轨迹差异报告|保留历史回归证据；不冒充本轮新MATLAB执行|
|F:/LJP/概伦AI/PLL_AGENTV2/PLL_AGENT/results/m3a_characterization_final_20261027/|CP DC、短脉冲、加载校准与独立留出|模型误差来源；严格工况匹配，局部域不覆盖全部捕获|
|F:/LJP/概伦AI/PLL_AGENTV2/PLL_AGENT/results/feedback_allocation_20261029/verification/matlab_corrected_candidates/ 与 matlab_corrected_loaded/|24组纠正后MATLAB record、原生周期CSV与测量CSV|逐条record原冻结SHA匹配后，将96份小型参考文件复制到data/verification_reference；仅验证侧使用|
|F:/LJP/概伦AI/PLL_AGENTV2/PLL_AGENT/results/p1_block_space_20261028/model_space_release/|model_cards、module_registry、manifest|五Block能力/有效域/条件的参考；不把测量样本包络自动改成全局能力|
|F:/LJP/概伦AI/PLLngspice_vs_matlab/results/stage4/vco_model_validity.json|VCO简单/复杂模型系数、训练与验证信息|锚点来源；不同系数组合不构成不同已实现VCO|
|F:/LJP/概伦AI/PLLngspice_vs_matlab/matlab/stage4、stage5、stage6、stage7/|VCO拟合、CP电荷模型、LF、系统瞬态与小信号|MATLAB后端参考；须区分原stage7数值近似与corrected记录|
|F:/LJP/概伦AI/PLL_Physics_FactorGraph_MATLAB/PLL_Physics_FactorGraph_MATLAB/experiments/|Icp、Kvco、LF、divider扫参脚本|实验设计和敏感度架构参考；未逐组重算，不能作为新主线已验证数据|
|F:/LJP/概伦AI/PLLngspice_vs_matlab/spice/stage3/cp/cp_core.inc|6管CP、理想偏置、端口、W/L|电路设计参考保留；Generic MOS非PDK；新主线不运行它|
|F:/LJP/概伦AI/PLLngspice_vs_matlab/spice/vco_stage2/current_starved_ring.inc|三级电流饥饿环振及端口|VCO模型的电路来源；不新增sizing任务|
|F:/LJP/概伦AI/PLLngspice_vs_matlab/spice/stage8/pfd_core.inc、div8_core.inc|双DFF复位PFD、三级静态CMOS÷2组成÷8|真实可读电路参考；新行为后端仍为理想PFD/Divider；存在网表不代表相关历史资格均已通过|
|F:/LJP/概伦AI/PLL_SPEC_ALLOC_BASELINE/physical_g1、physical_g1_1、physical_g1_1b、runs/|混合闭环电路、RAW、数值资格与诊断|历史保留；不迁入Runtime，不将UNKNOWN/FAIL改为PASS|

每个新声明候选保存 `parameter_role=DECLARED_TARGET`；只有原校准锚点可引用其历史模型来源。共同条件至少绑定拓扑、fref/N/fout、VDD/温度、负载、初态、复位时间、相位符号及测量窗。电路数据不会丢弃，但不得从局部模块数据推导本轮未测的噪声/抖动/全系统实现资格。

FactorGraph MATLAB 的原模型明确是平均相位域PFD/CP、Euler积分，参数为Rz=30kΩ/C1=1nF/C2=100pF、Kvco=20MHz/V、Vctrl数值保护±20V、尾20%测量。它与本主线的周期电荷/精确RC/校准VCO/尾50周期协议不同，故只参考架构与物理关系，不继承其数值作为本主线验收数据。其model_inventory.m的声明也没有声称与外部Python实现逐行等价。
