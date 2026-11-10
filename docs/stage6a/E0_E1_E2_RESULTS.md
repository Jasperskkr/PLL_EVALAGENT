# E0 / E1 / E2 实验结果

权威数据：`experiments/stage6a/summary_01/candidate_results.csv`及同目录逐候选JSON。每份JSON含输入研究SystemSpec、额外调谐/捕获要求、完整17项含单位JointBlockSpec、M1、独立M2、逐约束裕量、原正式判决、验证等级、成本与原文件SHA。实验前计划为`frozen_01/experiment_plan.json`，未事后改阈值；7个首次候选+1个现有确定性修复，均通过唯一正式pipeline完成真实M2。无新LLM调用。

|实验 / 候选|M1 BW kHz|M1 PM °|M2 BW kHz|锁定 µs|研究判决|
|---|---:|---:|---:|---:|---|
|E0 Analytical|225.000|72.2472|226.4039|33|RESEARCH_JOINT_FEASIBLE|
|E0 SLSQP|204.3567|72.2472|205.3856|37|RESEARCH_JOINT_FEASIBLE|
|E0 不同电容对|225.000|56.4427|225.4724|16|RESEARCH_JOINT_FEASIBLE|
|E1 Analytical|295.000|72.2472|298.1659|24|RESEARCH_JOINT_FEASIBLE|
|E1 高形状边界|299.500|70.0437|301.4536|35|FAIL：测得BW越界|
|E2 低Kvco/近上轨|225.000|72.2472|226.4039|38|RESEARCH_JOINT_FEASIBLE，含条件deadline|
|E2 高Kvco/中心|225.000|72.2472|226.4039|36|RESEARCH_JOINT_FEASIBLE，含条件deadline|
|E1 原确定性BW修复|293.0882|70.0437|294.9261|36|RESEARCH_JOINT_FEASIBLE|

E0约束为BW150–300kHz、M1 PM≥50°、严格0<Vreq<1.2V。Analytical/SLSQP均直接找到联合候选并通过独立BW。不同电容点C1=100pF/C2=1nF、同预测225kHz但PM56.44°，说明没有只保留最大PM解。E0解析的完整候选、M1及M2数值/不确定度/判决与Stage5 S0历史结果一致；对比明确排除了场景标识、解释措辞和非确定性计时。

E1约束为BW290–300kHz、M1 PM≥70°、内部调谐。低形状分支被Rz下限排除，而峰值/高形状分支可行。边界候选的M1 BW裕量仅500Hz、PM裕量0.043687°。M2测量包络[301329.396069,301567.929345]Hz，最高端相对300kHz裕量−1567.929345Hz；不是数值包络与边界重叠，而是可靠FAIL。该点表明M1数学可行不保证M2规格可行。

冻结优先级中E2捕获均通过，因此唯一修复预算用于E1的真实BW失败。原`allocation/repair.py`使用测得BW比例a=295000/301453.584583，协同Rz→Rz/a、Icp→Icp·a²，保持理想PM形状；输出Rz4182.001265Ω、Icp96.450114µA、C1=50pF、C2=2nF、f0=68MHz、Kvco26.730487MHz/V。完整复验测得BW294926.116949Hz，包络[294812.358419,294976.918885]Hz；研究BW下/上裕量4812.358419/5023.081115Hz，M1 PM仍70.043687°、Vreq0.448926V。全部已纳入联合约束重新检查，通过研究判决。PM裕量仍很小，不能称鲁棒保证。

E2在E0约束上增加固定初态/160µs窗口下的捕获与40µs锁定上限。E0解析点作为中心对照复用，不重复计样本；匹配三例M1 BW/PM/UGF完全相同，M2 BW差约3.2µHz（非精度保证），锁定分别33/36/38µs。近上轨例Vreq1.15V、低Kvco17.391304MHz/V，初始失谐与rail轨迹不同；粗/细步长锁定时间相同，包络[37,39]µs通过deadline，尽管早期有clamp和cycle slips。原协议只要求终端持续锁定，不把早期事件自动判失败。额外独立capture pair逐字段重复一致，计2个原生调用。**未找到E2条件行为失败；未执行捕获修复，未证明捕获反馈优化的增量价值。**

强制反例回归读取原Stage5 S3/Random11修复证据：M2 BW通过，但M1 PM约45.661°<50°，本轮联合判决为FAIL。没有因为BW改善而把它算成功；历史证据未覆盖或重跑。

8次新完整M2中8次M1预测联合可行，7次测得BW通过、1次BW失败；7个候选达研究联合可行（包含1次修复），不能把这个计数当独立统计成功率。首次7项中6项研究通过。原正式M2整体判决为7个UNKNOWN、1个可靠BW FAIL（边界候选），严格周期PM/1µHz频率仍UNKNOWN，FULL_SYSTEMSPEC_CERTIFIED=0。研究JSON中的full_SystemSpec_status=UNKNOWN表示完整认证能力未建立；它不能抹掉单独保留的original_M2_status=FAIL和research_joint_status=FAIL。

本轮测得BW相对M1偏差+0.20994%至+1.07320%，边界区域的PASS/FAIL出现不一致，内点一致。正偏差只描述本轮选点，未校准公式、不宣称全域误差界或真实晶体管保真度。
