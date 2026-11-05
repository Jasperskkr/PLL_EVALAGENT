# Stage 4 · UGF/PM独立测量验收报告

2026-11-05。结论：**独立事件端口注入、观测、复数返回比与局部交越原型已建立并完成三例数值验证；周期PLL的正式UGF/PM认证尚未建立。** 权威结构化结果保留`value=null/status=UNKNOWN`，科学状态为`UGF / PM M2 MEASUREMENT NOT YET VALIDATED`。不能把曲线接近M1或局部标量PM为正当作完整行为PASS。

方法、符号、DC恢复和周期系统障碍见[方法报告](UGF_PM_MEASUREMENT_METHOD.md)。本轮冻结M1、SystemSpec、Block Space六参数域、allocation算法/提示词、原事件核与协议1.1。原Stage3A.1发布资产保留，本阶段分支`codex/stage4-ugf-pm`供Leader审查，没有将旧发布Commit冒充本次新版本。

## 一、三个工作点及实际结果

真实Agent案例读取`experiments/stage3a1_llm_retry_20261104_01/AllocationProposal.json`原完整Proposal，不使用用户给出的近似值替代。本轮没有新LLM网络请求，使用保存Proposal明确属于复验。

边界案例固定Nominal其余参数，在原Rz范围内48次二分，使原M1 PM从下方接近既有50°下界；最终Rz=2482.028124785117Ω，M1 PM=50.00000000000804°，完整域检查通过。选择过程写`stage4_study_20261105_02/boundary_selection.json`；M1选择用于确定研究案例，不用于测量频率网格或返回比拟合。

|案例|BW M1→M2 (kHz)|UGF M1 / Series / Direct Port (kHz)|PM M1 / Series / Direct Port (°)|正式判决|
|---|---|---|---|---|
|Nominal|222.379183→222.853093|138.176441 / 138.419602 / 138.177569|56.442690 / 56.439320 / 56.438520|BW PASS；UGF/PM UNKNOWN|
|保存的真实Agent|225.000000→226.403934|167.166520 / 168.090256 / 167.168966|72.247210 / 72.242188 / 72.242914|BW PASS；UGF/PM UNKNOWN|
|PM边界|161.619465→161.895664|104.265350 / 104.427382 / 104.263022|50.000000 / 50.023715 / 49.997335|BW PASS；UGF/PM UNKNOWN|

Series/Direct Port两列均为**局部测量诊断值，未进入正式M2认证列**。BW相对误差分别+0.213109%、+0.623971%、+0.170895%。Series PM相对M1的绝对差分别−0.003371°、−0.005022°、+0.023715°；与Direct Port的拓扑差分别0.000799°、0.000726°、0.026379°。边界点的两种局部PM分居50°两侧，尤其不能据此签发稳定裕量PASS或FAIL。严格1e-6Hz频率认证仍UNKNOWN，三例整体均UNKNOWN。

BW/Capture用原Protocol1.1完整重跑：Nominal和Agent的全部M2 metrics/constraints与冻结Stage3A参考逐字段一致。边界点为本轮新案例，无伪造历史等价声明。三例捕获均按原条件执行；暖启动返回比测量不能替代冷启动捕获结论。

闭环T/(1−T)诊断分别为138.418121kHz/56.329321°、168.074250kHz/72.196838°、104.532515kHz/49.957384°。这些来自旧BW实际复数T事后反算，受标量假设、频率网格与病态性限制，始终仅诊断，未升级认证。

## 二、数值收敛与科学障碍

门限在首轮扫描前写入`docs/stage4/AUDIT_AND_METHOD_PLAN.md`及扩展协议0.1。v0.2只增加实测DC初始化，未改门限。六组完整扫频包括base、幅度半、步长半、窗口双、错位网格、独立clamp，正负注入独立运行；clamp正负各先pilot再新运行恢复DC。

|案例|幅度/步长/窗口/错位网格最大UGF变化|对应最大PM变化|Series/Clamp UGF差|最大原始THD|最大原始残差/基波|
|---|---:|---:|---:|---:|---:|
|Nominal|0.001106%|0.002141°|0.174855%|0.015133%|0.209649%|
|真实Agent|0.002489%|0.002491°|0.548093%|0.017857%|0.279507%|
|PM边界|0.002249%|0.001495°|0.157392%|0.015907%|0.233014%|

所有有效括区宽度≤0.2%；无实际限幅，控制均值/漂移及频差通过预设门限；独立clamp的原始pilot偏移/恢复后轨迹分别保留。最大已测低频→侧带RSS约1.73%、2.30%、1.92%，通过3%门限。以上是确定性数值变化和实测比值，不是统计置信区间或完整误差界。

随后在**实际测得交越**附近，以0.001rad分别驱动fref−f和fref+f，采用.4/.2ns步长、5ns观测、固定80µs丢弃及12个低频周期观测；没有用M1选探针频率。反向低频转换增益范围：Nominal0.997874–0.997939，Agent0.994171–0.994233，边界0.997937–0.997970。步长收敛后仍存在；说明低频产生的侧带很小，不等于反向耦合很小。

这不证明系统不稳定，也不证明标量PM必定错误；它证明现有有限单音实验尚不能给出周期谐波环路的完整稳定性证书。没有测得有截断上界的完整谐波返回矩阵、广义Nyquist或Floquet条件。因此正式UGF/PM列保持空/UNKNOWN，不能将测量定义差异直接标为可靠MODEL_DISAGREEMENT或SPEC_VIOLATION。

## 三、结构化反馈与统一入口

最终证据为`experiments/stage4_summary_20261105_05/{nominal,real_agent,pm_boundary}_extension.json`；逐指标对照见根`m1_m2_ugf_pm_comparison.csv`，全部频点（含UNKNOWN及复核组）见根`frequency_response.csv`。版本绑定包括Proposal参数/模型/SystemSpec/协议/源码SHA，普通Protocol1.1结果不覆盖。原始实验保留当时的源码与DLL哈希；最终附件绑定当前分析/有效性审查代码，未把后处理重算算作新仿真。

```powershell
python -m pll_allocation pipeline --strategy analytical --proposal experiments/stage4_study_20261105_02/real_agent/AllocationProposal.json --measurement-extension experiments/stage4_summary_20261105_05/real_agent_extension.json --out experiments/stage4_pipeline_feedback_20261105_03
```

本命令实际完成106次原生仿真，9.729s，M2_PARTIAL_PASS；扩展证据实际传入原Policy.receive_feedback，回执RECEIVED_BY_ALLOCATION_AGENT，automatic_learning=false。显式旧候选复验不算新LLM/FIRST_SHOT成绩；没有proposal时拒绝读取已有测量污染新首次分配。五种诊断标签有组合测试；本次三例实际标签为UNSUPPORTED_METRIC，数值失效的0.1记录对应MEASUREMENT_UNRELIABLE；未制造可靠规格失败或模型失配标签。

## 四、回归、失败记录与保护

|实际执行|PASS|FAIL|ERROR|SKIP|记录|
|---|---:|---:|---:|---:|---|
|Stage4修改前原主线|283|0|0|0|stage4_pretests_20261105_01/tests.xml|
|新增初轮核心测量测试|10|0|0|0|stage4_unittests_20261105_01/tests.xml|
|正式tests与原Track B同次收集|0|0|2|0|stage4_finaltests_20261105_01/tests.xml|
|随后正式完整套件|297|0|0|0|stage4_finaltests_20261105_02/tests.xml|
|中间正式完整套件|300|0|0|0|stage4_finaltests_20261105_03/tests.xml|
|最终正式完整套件|300|0|0|0|stage4_finaltests_20261105_04/tests.xml|
|原Track B单独回归|28|0|0|0|stage4_trackbtests_20261105_01/tests.xml|
|无DLL源码副本重新编译后Stage4测试|17|0|0|0|stage4_bundlecheck_20261105_01/stage4_tests.xml|

最终300=原283+新增17；原Track B 28项与统一套件中的28项为重复验证，不计新增案例。最终pytest报告25.40s；原28项1.42s。无旧DLL的独立源码副本重新编译原核与端口核后，新增17项在1.00s内通过；这是同一Windows/MSVC环境的源码重建检查，没有声称全套跨机器/跨平台验收。新测试覆盖五组零扰动逐元素等价、真实注入边沿变化、复数符号/DC趋势、UNKNOWN点/多交越、域拒绝、扩展版本/参数绑定与拒绝假认证、反馈类别组合、阻止首次反馈泄漏。

保留的失败/修正：① v0.1开放端口低频DC偏移导致gate=false，未扩展；② 中间汇总因NumPy bool不可JSON序列化失败，原部分JSON及failure.json保留，显式转Python bool后在新目录重算；③ tests与track_b/tests同名模块引起2项收集错误，改为分别执行，没有改旧测试；④ 首图对数轴minor标签重叠，初版及碰撞报告保留，禁用多余minor标签后新目录输出；最终对齐/碰撞PASS、PDF最小7pt，PNG为300dpi预览而PDF/SVG为矢量，未声明期刊投稿格式验收。

旧输出/模型/协议/原事件核/已有测试全部由32,576项保护清单核验。允许变更仅.gitignore（新DLL目录忽略）、pipeline.py（显式研究附件适配）及阶段记录/README；新增文件独立记录。历史Track B仓库HEAD/status保持，旧ZIP删除/外部包原状保留，旧发布包未覆盖。最终审计及实际仿真成本见docs/stage4/final_audit_01；测试中的额外仿真与主实验分开统计，不将未保存的测试内部调用混入已记录主实验总数。

主实验实际成本按每次保存的原生summary逐项计数，含失败测量、pilot及三次Pipeline复验：

|实验|原生仿真次数|其中DC pilot|原生函数累计秒数|
|---|---:|---:|---:|
|160kHz原型|4|0|0.072024|
|v0.1 Nominal（DC门限失败）|306|0|9.025710|
|v0.2三例完整测量|1024|102|29.741588|
|反向谐波探针|12|0|0.428940|
|Pipeline附件复验01 / 02 / 03|106 / 106 / 106|0|2.864176 / 3.019535 / 2.910184|
|合计|1664|102|48.062156|

其中原Protocol1.1共7次完整验证、746次原生调用（新边界点的自适应扫频次数不同）；相位端口原生调用918次。累计积分点1,283,205,699。48.062s仅为已记录原生函数计时之和，不包括轨迹写盘、拟合及绘图，不冒充完整研究墙钟时间；最新Pipeline实际总计9.729s。测试和独立源码重编译验证的内部调用单列，不重复加入本表。新LLM请求0；没有已知货币成本数据。

## 五、重现与交付

Windows/MSVC2022 x64、Python3.12.10、NumPy2.5.3、SciPy1.18.1、matplotlib3.11.2；跨平台NOT_VERIFIED。新机器在已具备依赖的源码目录执行：

```powershell
& .\pll_allocation\verification\build_kernel.cmd
& .\pll_allocation\verification\build_return_ratio.cmd
python tools/run_stage4.py --out experiments/new_stage4_study
python tools/stage4_sideband_checks.py --study experiments/new_stage4_study --out experiments/new_stage4_sidebands
python tools/finalize_stage4.py --study experiments/new_stage4_study --harmonics experiments/new_stage4_sidebands --out experiments/new_stage4_summary
python -m pytest -q tests -p no:cacheprovider
```

所有输出和构建目录须不存在；旧机器不要覆盖已有build。run_stage4研究主程序先Nominal数值gate，之后才其他两例；最终正式认证由谐波审核/validity适配器决定，数值gate不代表认证。所有实际点设置、正负/pilot、版本和源Hash均保存，原始npz保留本地不入包。主实验仿真/失败成本汇总及每份轨迹SHA在审计清单；本阶段新LLM调用0、未运行新修复算法。

英文代表图在`experiments/stage4_figures_20261105_02/`，包含M1/Series/Direct Port幅相响应和实测局部UGF标记，未裁掉失效频点。精简包`stage4_ugf_pm_review_bundle.zip`含必要源码、冻结输入、小型证据、图/CSV、协议、测试、失败摘要与文件SHA；不含原始npz、DLL、缓存或密钥。少量历史CSV仅为既有回归夹具；大规模实验波形保留本地。最终包清单注明工作树Hash及基线Commit，不伪称本阶段已Git冻结。包支持源码目录入口；本轮没有新增wheel安装验收，既有pyproject资源清单未扩展为Stage4二进制发布合同。

目前M1在三个理想工作点的局部频响获得更多行为支持；这仍不足以证明周期系统PM、全域可信度、严格频率、噪声/抖动/功耗。最关键缺口是可收敛且有截断误差控制的谐波环路稳定性验证。本阶段在此停止，等待Leader审核。
