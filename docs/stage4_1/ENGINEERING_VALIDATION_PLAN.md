# Stage 4.1 Engineering Validation Plan

2026-11-05。研究任务按原字节保存于 `USER_REQUEST.txt`。本计划在首次Stage4.1 M2调用前落盘。

## 审查与最小整合

起始HEAD `66c4ddb3a2cf075a03c21e19a1a0eccbf69462e3`，分支 `codex/stage4-2-readiness`；Stage3A.1基线 `47afcb72011636e838b03d81cf91bcec49744a77`。Stage4.2 Registry/候选已提交，Stage4测量源码/可选Pipeline附件仍未提交。历史ZIP删除和其他未跟踪成果存在，不属于本阶段提交范围。TrackB嵌套历史仓库HEAD `dc661f6f7694562444438410f39190571b51a398`、状态干净，只读保护。

源码核对：`kernel.cpp`执行边沿内插、PFD置位/复位、CP面积、双状态LF Euler、线性VCO相位积分；`simulator.py`只支持正幅度正弦参考调制。Stage4的`return_ratio_kernel.cpp`包含原核并隔离Series/Clamp端口；`return_ratio.py`执行真实正负注入、DC pilot和基波/侧带拟合；UGF/PM仅诊断。`verify.py`独立跑完整BW/Capture Protocol1.1，频率微Hz与PM仍UNKNOWN。`pipeline.py`已有显式旧候选附件防泄漏。Registry有14项源码/模型/规格绑定，不执行求解。候选原完整SI及哈希直接读取，不重建。

1. 保存现有源码/配置/历史文件SHA256和未提交Stage4源码副本，再创建短期分支。
2. 明确范围提交Stage4源码、配置、测试和方法记录，使Stage4与Stage4.2同一版本可运行；不吞入无关删除或旧实验。
3. 新增独立`closed_loop_kernel.cpp`及适配/分析入口。包含原核保留原导出，只扩展平滑参考相位阶跃与观测，不编辑原核或Stage4代码。原物理更新语句/顺序保持，零扰动逐元素回归。
4. 先新运行C01/C02 Stage4 Series/Clamp，核对历史锚点；随后C01–C08完整频域、原BW/Capture和独立阶跃。
5. 所有方法和阈值以`closed_loop_stage4_1_v0_1.json`为预声明版本。开发候选分析完成后，源码/协议/候选哈希写入holdout锁；此后才运行C09/C10，不据其结果改本轮方法。
6. 汇总、图表、保护审计、回归、精简包及阶段提交；待Leader审查，不推进其他阶段。

## 三层证据与研究判据

M1连续锁定点预测、Stage4事件端口局部返回比、新闭环时域观测分别保存。时域绝不反推或认证PM。原SystemSpec的draft元数据、六变量域、M1方程、M2更新、Protocol1.1和Agent保持。研究标签不接管正式PASS/FAIL/UNKNOWN。

数值有效性：零扰动工作点、正负、幅度2倍、dt减半、窗口2倍和拟合稳定性逐项检查，门限见协议。未经稳定拟合的振铃衰减/周期返回null/UNKNOWN。

工程映射支持要求：有效的Series和Clamp局部交越、原BW收敛，M1差异BW≤3%、两种UGF≤2%、两种PM≤1.5°；共同扫频点复差≤5%、相位差≤3°。时域采用实际平滑输入、相同时间网格与参考周期平均，归一化RMSE≤5%、最大差≤12%、超调差≤5个百分点、恢复时间差≤max(20%,0.5µs)。这些是本研究比较阈值，不是冻结SystemSpec约束或全域误差上界。

稳定观测要求：有效暖工作点、无滑移/限幅、尾段误差/漂移满足协议及恢复完成。持续增长/滑移才支持动态失稳观测；测量失败本身不能当作失稳。低PM负向对照不要求发散。PM相近UGF三点仍同时改变R/I，零极点影响必须报告。增益拆分只检验指定两个理想点。

正式UGF/PM始终null/UNKNOWN，严格80MHz微Hz精度UNKNOWN；C03两方法跨门限时保留歧义。完整周期系统标量PM未认证。有限10点、两幅度、两dt和窗口不外推六维全域，不宣称晶体管实现能力。

## 版本、成本与交付

每个请求先写盘；保存完整候选/协议、实际源码/DLL SHA、输入/输出轨迹SHA、执行时间、真实原生调用（含DC pilot和失败）。C02为历史真实Agent候选复验，本阶段新LLM调用0。原始NPZ本地保留，审查包排除NPZ/DLL/缓存/密钥。测试实际命令及JUnit保留，任何失败原地留档。
