# PLL Spec Allocation：新对话从这里开始

交接日期：2026-11-09，Asia/Shanghai。建议阅读顺序：本页 → CORE_ALGORITHMS → BEHAVIORAL_MODEL_AND_VERIFIER → EXPERIMENT_HISTORY → 复现说明。路径均相对压缩包根目录；源码在 `repo/`。原仓库根 README 和早期报告是历史原件，可能落后于本交接说明。

## 1. 最终目标与三个研究问题

项目研究固定整数 N 电荷泵 PLL，在给定 SystemSpec、固定拓扑和声明 Block Space 下，如何联合分配模块行为规格，并用独立行为 Testbench 验证。交付链是 **SystemSpec → JointBlockSpec → 真实行为 TB → Verified JointBlockSpec**。初次失败后允许有限反馈修复；首次候选必须在首次 M2 前落盘，探测、失败、重试和调用成本必须可追溯。

三个问题贯穿各阶段：

1. **模型空间**：哪些 Block 参数可以独立分配，范围依据是什么，哪些系统指标能通过物理映射预测或反解？声明域、数学有效域、证据支持域必须分开。
2. **分配策略**：物理反解、Sensitivity、数值优化和 LLM 各自贡献什么；首次分配与有限反馈能否改善可行性、裕量或成本？
3. **行为验证**：如何快速而可信地测量动态、捕获和稳态指标，把可靠违例与模型/数值/定义不确定性分开？

本阶段不做 PDK、MOS、sizing、ngspice 或晶体管可实现性认证。原任务见 `repo/PROJECT_CHARTER.md`；阶段范围以 `repo/docs/DECISIONS.md` 为准。

## 2. 正在研究的 PLL 与输入

拓扑固定为 `Reference → PFD → CP → LF → VCO → Divider → PFD`，fref=10 MHz，N=8，目标80 MHz。LF 是 C1 对地、Rz 串 C2 对地的两状态无源滤波器，f(V)=f0+Kvco·V。f0 是 **0 V 截距**，不是中心频率。

|六个自由轴|声明范围|
|---|---|
|Icp|50–200 µA|
|Rz|2–8 kΩ|
|C1|50 / 100 / 200 pF|
|C2|0.5 / 1 / 2 nF|
|f0|60–76 MHz|
|Kvco|10–40 MHz/V|

其余11个输入固定：fref、N、0–1.2 V rails，Kvco2、CP mismatch/leakage、q0、PFD reset delay、Cload、Gload 均为零。完整候选有17项含单位值，语义目录有41项；“五个 Block 的完整分配”不表示每个 Block 都有自由变量。原域为人工声明行为研究域，不是经器件证明的联合能力表。

基准 SystemSpec 为输出80 MHz（±1e-6 Hz）、闭环 BW150–300 kHz、PM≥50°。JSON 的 `draft:true` 仍保留；“冻结”是该次实验的输入和哈希固定，并不取消草案标志。研究场景仅版本化覆写 BW/PM 阈值，不覆盖基准文件。Stage6A 的40 µs捕获 deadline 是额外研究条件。

## 3. M1、M2、Allocation Agent 的分工

- **M1**：`physics_mapping/model.py`，理想锁定点连续小信号预测 BW、UGF、PM、调谐点；不执行捕获瞬态，不签发行为 PASS。
- **Allocation**：`allocation/physics.py`、`allocate.py`、`repair.py`，执行电容枚举、条件反解、敏感度、SLSQP 和确定性修复。`agent.py` 中真实 LLM 选择工具与候选句柄；高精度数值由确定性工具计算。
- **M2**：`verification/`，原生 C++ 边沿事件处理加固定步长 Euler 积分，独立注入/测量闭环 BW 与条件捕获；正式判决由 Python 层控制。
- **Runner**：`pipeline.py`，冻结输入/候选、检查约束、控制 M2/repair 预算、收反馈与保存所有证据。Policy 无权更改规格、跳过验收或宣布 PASS。

真正生产所有权已在 Stage3A.1 收敛到这三个目录。`track_a/` 主要为兼容入口/实验脚本；早期 `runner.py`/`behavioral.py` 是旧周期模型主线，不应与现在的原生 M2 混称。

## 4. Stage1–6A 已经走到哪里

|阶段|实际完成的关键工作|
|---|---|
|1 / 1.5|连续 M1、统一单位/变量、六参数声明域、联合约束、数值一致性与稀疏事件检查|
|Track A / B|物理逆向、Sensitivity/SLSQP、真实工具型 LLM；事件 TB 的 BW/条件捕获测量|
|3A / 3A.1|统一 pipeline、正式模块归属、真实 M2、失败成本、修复复验和独立源码发布检查|
|4|独立相位端口 Series/Clamp 与谐波诊断，得到局部 UGF/PM 工程证据，未完成周期稳定性认证|
|4.2|Mapping Registry、指标到方程/求解器/证据映射、1728点有限网格；没有新 M2|
|4.1|10个固定候选的局部频响/阶跃验证，原模型/协议不变，328项历史正式回归|
|5|五种 BW/PM 场景，解析/随机/真实 LLM 首发对照，12次确定性修复；仍无完整 SystemSpec PASS|
|6A|4725点公式网格与条件反解，8次完整 M2，E1真实边界失败与修复，E2同小信号指标不同捕获；376项历史回归|

可信发现：当前域具有很强的降维结构；固定 C 时动态仅依赖 Rz 与 Icp·Kvco，f0 不影响理想小信号环路。解析工具足以找到多组可行候选。Stage5成功 LLM 都选择解析工具，未显示额外数值收益。M1内点与M2局部BW接近，窄边界却可能改变判决。Stage6A边界299.5 kHz预测对应301.454 kHz实测，反馈后294.926 kHz通过研究带宽；所有联合约束必须重查。

同一 BW/PM/UGF 下，条件捕获可为33/36/38 µs。它们均通过冻结40 µs deadline；没有取得捕获失败或捕获修复证据。Stage5另有“BW修好但M1 PM仍失败”反例，不能把单项改善计为联合成功。以上都是有限选点证据，不是全域误差界或统计成功率。

## 5. 能验证什么，缺什么

可以分配和预测：频率规划、严格内部调谐、连续 M1 BW/PM/UGF。可以独立测量：指定归一化可观测量的局部闭环 BW、固定初态/窗口下的 capture/lock time、终端频率与控制电压诊断。局部返回比/阶跃提供工程支持。

**严格周期 PM/UGF、±1 µHz频率精度未认证；Static Phase Error没有本主线正式分配/认证闭环；Jitter、Power、RUR没有可用正式模型。UNKNOWN不能改成PASS。Stage1–6A完整SystemSpec认证数为0。M1/M2均理想化，二者一致不能证明真实电路保真度。**

下一步的两个方向是：一方面研究快仿真、非线性捕获、模型适用域和更高保真参考；另一方面在统一证据/约束合同下比较物理反解、敏感度、SLSQP和M2反馈搜索，最后再判断LLM的策略选择是否有价值。当前六维表面空间很简单，不能预设双层Agent或BO必需。

## 6. 真实 Git 状态与开始方式

三个工作树 HEAD 均为 `cd70cf445d2ac6789550b7df2da6736221262045`。master已包含Stage3A.1、4、4.2、4.1提交，但 **Stage5/6A成果依赖未提交工作树**。本包 `repo/` 是Stage6A工作树的字节快照，正式运行源码与原主目录一致；阶段新增研究文件有独立来源清单，未合并、提交或清理原工作树。

现场还发现 Stage6B **已经实际实现并运行**：独立分支含多规格约束/搜索、pipeline路由和B1/B2实验，正式研究时404项测试；增加归档兼容测试后，本包实跑407项通过。它不是Stage1–6A基线的一部分，保存在 `source_variants/stage6b/`；详细边界见 CURRENT_STATUS_AND_RESEARCH_GAPS。不要再把“Stage6B尚未开始”当现状，也不要把6B成果追溯为6A已有。

先读 `docs/handoff/REPRODUCIBILITY.md`，运行纯 Python 证据审查或 M1，再在Windows/MSVC环境构建原生核并执行最小pipeline。`docs/handoff/SOURCE_INDEX.md`提供精确函数行号。实际本次复现结果以 `reproduction_validation/` 为准，历史测试数不是本次测试承诺。

本次严格无Git补验：5关键M2全部精确复现；完整回归375通过/1项历史Git元数据依赖失败。另两份新副本各376通过，Stage6B独立物化407通过。详见reproduction_validation/FINAL_VALIDATION_REPORT.md。早期/raw结构化侧文件以evidence_metadata.tar.xz无损存储，必要时按REPRODUCIBILITY展开；主要源码/配置/测试与Stage5/6A核心判决仍直接可读。
