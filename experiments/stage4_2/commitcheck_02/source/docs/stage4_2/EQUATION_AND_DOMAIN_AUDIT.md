# 公式、耦合与适用域审计

审阅范围：实际`physics_mapping/model.py`、`validation.py`、`block_space/contracts.py`、正式`allocation/{physics,allocate,core}.py`、`verification/{verify,simulator,kernel}`、Protocol1.1及Stage4证据。所有复用路径/SHA/语义由研究Registry和运行manifest绑定。未修改原函数。外部一级资料检索本次HTTP403，没有读到资料，不借未读文献背书；以下推导基于实际理想拓扑和本地原始MATLAB来源记录。

## 1. PFD/CP与VCO

**WHAT**：φe=φref−φdiv（rad）带来CP平均电流；**INPUT**：Icp；**DOMAIN**：相等正UP/DOWN电流、无leakage/q0/reset/mismatch的理想锁定小信号；**INVERSE**：Kpfd=Icp/(2π)可代数还原Icp，但本项目没有独立Kpfd目标；**EVIDENCE**：E_KPFD原实现/来源SHA、Stage1.5频响数值路径与本次1512点一致；**LIMITATION**：平均斜率正确不证明事件周期稳定性或非理想CP平衡。

推导：Δt=φe/(2πfref)，周期平均电流Icp·Δt·fref=Icp·φe/(2π)，故A/rad，不多乘fref。VCO增益输入Kvco为Hz/V，角频增益为2πKvco rad/s/V；L中这两个2π相消，得G=IcpKvco/N。漏掉Divider N或把Kvco当rad/s/V会整体改变增益，不能作为校准误差处理。

**WHAT**：调谐与工作点；**INPUT**：f0、Kvco、N/fref和rail；**DOMAIN**：f(V)=f0+Kvco·V为正线性单调函数，f0是零伏截距；**INVERSE**：Vreq=(80MHz−f0)/Kvco，或给定Vreq求f0；**EVIDENCE**：旧32点中26点条件频率/控制一致、Stage4局部实测与本次代数；**LIMITATION**：不把旧v1“V0锚点”语义混入，曲率/PVT/负载未支持，调谐充分性只限静态存在性，非捕获。

## 2. Loop Filter

**WHAT**：CP电流到控制电压阻抗和lead形状；**INPUT**：Rz/C1/C2；**DOMAIN**：C1对地，与串联Rz-C2支路并联；无Gload/Cload/寄生；**INVERSE**：给定两个电容与ωu,x可还原Rz，但原C只能枚举三个离散值；**EVIDENCE**：E_LF、独立KCL测试、不同数值根路径；**LIMITATION**：无CP输出电阻、VCO输入动态加载及介质损耗。

KCL：C1·s·v=i−(v−u)/R，C2·s·u=(v−u)/R，消去u得到

`Z(s)=(1+sRC2)/(s(C1+C2)+s²RC1C2)`。

`ωz=1/(RC2)`；`ωp=(C1+C2)/(RC1C2)`；pole为0和−ωp。表中的正Hz是极点频率幅值，不能当正半平面根。q=ωp/ωz=1+C2/C1>1。R变化同时平移zero/pole并改变交越位置，不能笼统说“增R恒增PM”；PM在shape峰值两侧方向相反。电容变化同时改变总电容与q；仅同倍缩放C才保留q，不能只按单个时间常数判断。

## 3. L/T、BW与UGF

**WHAT**：连续理想锁定点相位频响；**INPUT**：IcpKvco/N及RC；**DOMAIN**：无延时、理想整数分频、内部工作点的小信号连续近似；**INVERSE**：完整多指标需有界数值交集；**EVIDENCE**：Stage1.5 124个有效点、本次1512个cheap/poly与67个正式M1交叉点；**LIMITATION**：这些是同一物理方程的实现一致，不是第二物理真值。

`L=G·Z/s`，`T=L/(1+L)`，实际参考到输出相位`Href=N·T`。UGF用|L|=1，BW用|T|=1/√2；不能对未归一化Href用相同阈值。原M1扫描8000个log频点再二分、只接受一个向下交越；其通用交越函数没有声称处理所有多交越稳定性问题。当前正理想网络可由单正根多项式解释唯一正频交越，不外推到有延时/非理想系统。

**已有解析策略并非全解析**：`inverse_at_shape`先调用`bandwidth_ratio`解标量多项式根，再还原ωu/R/gain；`analytical`还枚举9个C组合和投影f0，最终由独立M1/域检查。`optimize`为原SLSQP maximin，不是全局最优证明。其1%局部guard是启发式，不能当制造容差或M1/M2误差界。无新策略在本阶段加入。

## 4. PM形状、上界和约束传播

**WHAT**：ωu处lead；**INPUT**：q=1+C2/C1、x=ωuRC2；**DOMAIN**：上述连续理想网络；**INVERSE**：已实现解析必要区间；**EVIDENCE**：既有`phase_interval/pm_ceiling`、本次完整9组表与同UGF配对；**LIMITATION**：只是形状关系，不能脱离原R/gain/BW/tuning域签发候选可行。

`PM=atan(x)−atan(x/q)`，峰在x=√q，`PMmax=asin((q−1)/(q+1))`。PM≥p等价于

`tan(p)x²−(q−1)x+q tan(p)≤0`（0<p<90°）。

PM50要求`C2/C1 ≥ 2sin50°/(1−sin50°) ≈ 6.5486`。C2/C1=2.5、5的三组可直接排除对当前PM目标的求解，保留其声明域作负对照。全声明域理想PM上界72.247209838°由C2/C1=40给出，保存的Agent达该形状峰；这不代表所有参数组合都达峰。

给定C、x和ωu，`R=x/(ωu C2)`，

`IcpKvco=N(C1+C2)ωu² sqrt((1+(x/q)²)/(1+x²))`。

这是真正的**条件解析**重建；若输入是BW，仍需数值求β=BW/UGF；若只给多个规格，不唯一决定六参数。还需产品分解与Kvco/f0调谐交集，所有原上下界/choice均独立校验。

## 5. 稳定性与耦合实验

**WHAT**：连续闭环三阶Routh；**INPUT**：正G/R/C；**DOMAIN**：理想L；**INVERSE**：必要域筛选；**EVIDENCE**：代数`bc−ad=GRC2²>0`；**LIMITATION**：正值下严格连续稳定恒成立，不能把PM<50称连续“不稳定”，不能证明周期事件稳定/捕获。

本次正式M1小实验保留全部输入和调用：Icp=160µA、Kvco=12.5MHz/V的乘积等于Nominal，三项动态指标相同，而Vreq从.4变.64V；只改f0为68MHz则三项动态不变、Vreq变.6V。固定C、R→R/a、IcpKvco→a²乘积时，a=.9/1.1使BW/UGF按a缩放、PM不变，数值误差<1e-7。

Nominal 1%对称log差分：Icp和Kvco的UGF弹性均.857138、BW弹性均.927480；Kvco还使Vreq弹性−1。f0不改变理想动态，但调谐相对灵敏度约−9.024（中心导数−9）；不能据“动态不变”忽略调谐约束。PM在Nominal接近峰，局部斜率几乎0，不代表全域不敏感。C只做合法choice跳变，不做伪连续导数。详见`coupling_and_sensitivity.json`。

## 6. 静态相位误差电荷关系

**WHAT**：用周期净电荷偏置解释静态时间/相位平衡；**INPUT**：q0、Iup/Idown、fref；**DOMAIN**：既有旧CP函数的符号约定，线性脉冲宽度、正分支电流、无额外机制；**INVERSE**：只支持已定义相位预算到电荷窗口的必要筛选；**EVIDENCE**：逐字节旧函数加本次符号/单位测试；**LIMITATION**：当前正式M1不支持非零q0/leakage等，旧proxy load含义不能直接迁移。

旧函数`q_balance=q0+Ibranch·Δt`，平衡Δt=−q0/Ibranch，φrad=2πfrefΔt。正注入泄漏若定义为每周期`q0=Ileak/fref`，则理想对称平均φ=−2πIleak/Icp，必须先确认符号，不能再多乘周期。q0=1fC、100µA、10MHz仅给出代数示例φ=−.036°；不是合法Stage1.5非零参数实验。mismatch/reset在有重叠脉冲时可能造成额外净电荷，当前零reset理想模型不能用该简化式推出可信非零偏置。

## 7. 行为证据与未验证推广

Stage4三点的局部UGF/PM非常接近M1且幅度/步长/窗口检查收敛，但fref±f→f反向转换接近1；不能用少量侧带或T/(1−T)给周期PM认证。原Protocol1.1 BW独立测量可用，但有连续phase/edge-only定义局限。严格频率、jitter、power仍无完整认证。

旧Equation Registry中“event TB尚未测BW”的文字是Stage1.5历史时点的状态；本阶段用带来源SHA的证据层更新查询结论，不改历史Registry。`physics_mapping.model.UnavailableEvaluator('M2')`也是旧保留接口，不表示正式`verification.verify`不存在；Agent应调用实际独立验证入口，不能混用两个接口名。

不同模型/协议、单位、参数、source hash在新Registry loader中必须匹配；研究索引只给建议工具，不执行/隐藏M2，不修改Runner判决。
