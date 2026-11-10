# 核心算法：按实际源码解释

基线：`repo/`（Stage1–6A）。以下公式由当前执行代码展开；函数精确行号见 SOURCE_INDEX。廉价代数、完整M1扫描、完整M2和LLM请求分别计数。Stage6B的新增算法另见文末，不能追溯写成6A已有能力。

## 1. M1 Physics Prediction

源码：`physics_mapping/model.py` 的 parse_parameters、_response、_crossing、M1Evaluator.evaluate；`allocation/physics.py`提供同一物理关系的低成本无量纲求根。

记 I=Icp、R=Rz、C=C1+C2、K=I·Kvco/N，Kvco单位Hz/V。PFD平均增益 I/(2π) A/rad，VCO相位增益2πKvco rad/s/V，所以2π相消：

\[
Z(s)=\frac{1+sRC_2}{s(C_1+C_2)+s^2RC_1C_2},\quad
L(s)=\frac{K Z(s)}s,\quad T(s)=\frac{L(s)}{1+L(s)}.
\]

T是归一化“输出相位/N对参考相位”，真实reference到output相位传递为N·T，不能额外再乘N后测归一化BW。LF有原点极点、ωz=1/(RC2)、ωp=(C1+C2)/(RC1C2)，非零极点为−ωp。

闭环特征多项式为 a s³+b s²+c s+d，a=RC1C2，b=C，c=KRC2，d=K。代码先检查所有系数和bc−ad>0；在正值理想域bc−ad=KRC2²>0。它证明的是连续线性模型的Routh条件，不证明事件捕获或周期稳定性。

**调谐**：fout=Nfref，Vreq=(Nfref−f0)/Kvco。必须严格位于rails内部，轨上点返回OUT_OF_DOMAIN。当前f0以0V为基准；Kvco_local=Kvco。f0对线性动态没有作用，但改变调谐余量、冷启动失谐和rail经历。

**实际扫描与根**：默认8000个对数频点，下界max(min(fz,fp)·1e-4,1 Hz)，上界max(fz,fp,fref)·100。UGF寻找 |L|−1 从正到非正的唯一括区；BW寻找 |T|−1/√2 的唯一向下括区。零个或多个括区都为NUMERICAL_FAILURE。随后在log10频率上二分，最多70次，区间<1e-12 decade退出。PM=180°+arg L(jωu)。不是从BW近似UGF，也不是从闭环幅度推断PM。

```text
parse exact SI envelope and ideal switches
check interior tuning, positive finite coefficients and Routh
log scan → unique downward UGF/BW brackets → log bisection
evaluate PM at actual UGF; return factors, metrics, units, protocols
on unsupported/out-of-domain/numerical failure: clear metrics; never PASS
```

有效假设为理想等电流CP、瞬时PFD复位、线性VCO、理想N、无附加负载/泄漏/噪声，锁定点连续小信号。Kvco2、CP_mismatch/leakage、q0、reset_delay、Cload、Gload非零会被明确拒绝，不能因为语义目录有字段就认为它们已建模。声明六轴范围见START_HERE，数学有效域还要求内部调谐、正频率等；历史器件经验域不等于这些范围。

**廉价等价公式**：令q=1+C2/C1，ωz=1/(RC2)，g=K/(Cωz²)，y=(ω/ωz)²。UGF根满足

\[
y^3/q^2+y^2-g^2 y-g^2=0;
\]

BW根满足

\[
y^3/q^2+(1-2g/q)y^2-(2g+g^2)y-g^2=0.
\]

`raw_prediction`在ln(y)∈[−14,14]内80次二分，必须有符号括区。它是同物理模型的代数计算，不是独立TB；Meter记analytic_calls，不能冒充完整M1或M2。

## 2. Analytical Inverse Allocation

源码：`allocation/physics.py` 的 pm_ceiling、phase_interval、bandwidth_ratio、inverse_at_shape；`allocate.py` 的 analytical。

设 x=ωuRC2、q=1+C2/C1，则

\[
PM=\tan^{-1}x-\tan^{-1}(x/q),\quad
PM_{max}=\sin^{-1}\frac{q-1}{q+1},\quad x_{peak}=\sqrt q.
\]

令t=tan(PMrequired)，相位下限等价 t x²−(q−1)x+qt≤0；`phase_interval`计算两个根（用稳定形式求小根，大根=q/小根）。超过电容对上界返回None。全9对皆None或固定频率计划矛盾时，`propagate`给PROVEN_INFEASIBLE，范围仅限本M1和声明域。无证书只表示必要条件未排除，不证明可行。

解析首发实际固定BW目标为上下界中点，每个电容对取峰值相位形状；**没有遍历整个可行x区间**。对给定(q,x)，令h=√[(1+(x/q)²)/(1+x²)]，β=ωBW/ωu；y=β²满足

\[
(x/q)^2 y^3+(1-2hx^2/q)y^2-(2h+h^2x^2)y-h^2=0.
\]

这一步是数值正根求解，并非闭式反解。继而

\[
\omega_u=2\pi BW_{target}/\beta,\quad
R=x/(\omega_u C_2),\quad
K=C\omega_u^2 h,\quad P=I\,Kvco=N K.
\]

增益分摊先求 Kvco∈[Kvmin,Kvmax]∩[P/Imax,P/Imin]，空集拒绝；取交集中点，再I=P/Kvco。f0按目标80MHz−Kvco·0.6V中心化，再投影到原f0范围。完整域检查仍可能拒绝R越界或调谐不合法的组合。

```text
propagate necessary constraints
for C1,C2 in 3×3 actual choices:
    reject if PM ceiling too low
    x=sqrt(q); numerically solve beta
    reconstruct R and gain product; solve legal Kvco/I split; center/project f0
    build complete 17-input candidate; reject invalid domain
    cheap_predict → margin_details
choose largest minimum normalized margin (stable enumeration breaks ties)
return complete proposal or NOT_FOUND/certificate
```

`margin_details`用BW半区间归一化双边裕量，PM用max(|PMmin|,1)归一化；连续参数的双边域裕量为2·min(p−lo,hi−p)/(hi−lo)，调谐同样按1.2V窗口归一化。频率等式只记录残差/允差，不进入质量目标；离散电容没有虚构边界距离。

基准解I=104.404300186µA、R=3048.124920669Ω、C1=50pF、C2=2nF、f0=63.761604100MHz、Kvco=27.063993167MHz/V，M1 BW225kHz、PM72.247209838°、Vreq=.6V。它不是唯一解或全域最优证书。

局限：只尝试峰值shape和BW中点，有合法解也可能NOT_FOUND；PM证书仅理想域有效；当前联合域不含器件相关性、噪声/功耗。Stage6A的条件x扫描用于研究可行域，并未偷偷替换正式analytical算法。

## 3. Sensitivity / SLSQP

源码：`allocation/allocate.py` 的 sensitivity、optimize、perturbation_check；`allocation/core.py` 的 margin_details。

**敏感度**：中心一次正式M1，Icp、Rz、f0、Kvco各两次，共通常9次。下/上点为max(lo,.99p)、min(hi,1.01p)。弹性Sij=[ln mj(p+)−ln mj(p−)]/ln(p+/p−)，用于BW/UGF/Vreq；PM记录度数对log参数的差商及二阶差分诊断。边界截断使二阶量只是诊断；离散C枚举而不求导。

固定C时L仅依赖Icp·Kvco/N和R。Icp与Kvco的动态敏感度列相同，f0动态列为零；Kvco与f0又通过Vreq耦合。因此SLSQP使用物理坐标 `[K=Icp*Kvco/N, Rz, Kvco, Vreq]`，分别线性缩放到[0,1]，每个电容对独立优化；不是直接在六个互不相关轴上黑箱优化。

目标是maximin epigraph：最大化t，约束所有归一化联合裕量 mj(u)−guardj≥t。由坐标恢复I=N K/Kvco、f0=80MHz−Kvco·Vreq；裕量中包含BW双边、PM下限、I/R/f0/Kvco的原域和调谐内部性，防止优化坐标边界掩盖原参数越界。

BW guard=.01·BWtarget/BWhalfwidth·Σ|S_BW,i|；PM guard=.01/max(|PMmin|,1)·Σ|dPM/dln pi|。其余guard为0。它是中心独立±1%扰动的一阶启发式，不是M1/M2误差界、置信区间或鲁棒认证。

每对以条件解析反解seed初始化；代数trial可暂时越过原分配域，只用于数值求解，明确记录ALGEBRAIC_OPTIMIZER_TRIAL_NOT_M1。最终候选须重新make_candidate/cheap_predict，再交Runner完整M1检查。SLSQP参数maxiter=60、ftol=1e-8、eps=1e-6、t∈[−10,1]；同一前四坐标cache避免重复廉价求根，预算不足可跳过剩余电容对。求解器success不是规格PASS，甚至success=false的最终点也要按实际合法性/指标决定是否可提议。

```text
get or compute 9-call M1 sensitivity
compute local first-order guards
for legal C pair:
    seed physical coordinates; cache algebraic trials
    SLSQP minimize(-t), with margins-guards-t >= 0
    reconstruct complete candidate and check original domain
select highest guarded min-margin candidate
Runner executes full M1 and M2 independently
```

`perturbation_check`另做四连续参数的16角±1%廉价诊断，不裁剪/重抽，域外保留；不是Monte Carlo，也不产生器件良率。历史Track A benchmark已实际比较优化，Stage3A也实际测其M2。Stage5没有独立SLSQP首发arm，但9个越界缩放修复调用旧optimize（记录45次电容对SLSQP solver）。Stage6A E0_slsqp是真实优化候选：M1 BW204356.651Hz，M2约205385.568Hz，条件锁定37µs；解析33µs，故M1裕量更高不等于捕获更快。

最小调用示例（从repo目录执行，不联网）：

```python
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.allocation.core import Meter, assess_m1
from pll_allocation.allocation.allocate import analytical, sensitivity, optimize
_, model, spec, _ = load_inputs()
meter = Meter()
c, meta = analytical(model, spec, meter)
a = assess_m1(model, spec, c, meter)
s = sensitivity(model, spec, meter, c)
o, ometa = optimize(model, spec, Meter(), s)
```

## 4. 真实 LLM Agent 的权限和调用

源码：`allocation/agent.py` 的 TOOLS、MessagesPolicy.decide、run_agent；`llm_transport.py`；`allocation/__init__.py`的AllocationStrategyPolicy。原始system prompt保留于源码，也自动摘录于 `reference/LLM_SYSTEM_PROMPT.txt`；工具动作合同摘录于 `reference/LLM_TOOLS.json`。

工具包含ReadSystemSpec、InspectBlockSpace、QueryPhysicalRelations、PropagateConstraints、AnalyzeSensitivity、SolveInverseAllocation、OptimizeCandidate、EvaluateM1、SubmitCandidateForM2、InterpretVerificationFeedback、Stop。通信返回纯JSON `{tool,args,reason}`，其中EvaluateM1/Submit要求args.handle。这里**没有提供商原生function/tool schema声明**，而是prompt列工具、文本JSON解析和执行白名单；不能误称已实现OpenAI function calling。

prompt明确要求LLM选择确定性工具、不自行高精度计算，不改变冻结目标、不声称verified PASS；首次上下文没有当前M2反馈。默认最多4次网络决策，run_agent本身最多14个工具step。上下文含SystemSpec、域、关系、必要条件、候选句柄和最近观测、剩余cheap/M1预算。LLM能选求解策略、评估句柄、提交或停止；无法直接向工具任意写六参数新值，数值由工具生成。

MessagesPolicy读取环境变量名指定的model/base URL/token，子进程运行llm_transport.py的Messages HTTP后端，保存request/response/transport status/usage/action/metadata；key及Authorization头不落盘。总进程超时、JSON失败也保留计数/耗时。请求HTTP200不等于产生有效候选，S2失败就是例子。

Stage5成功路径均为SolveInverseAllocation → EvaluateM1 → SubmitCandidateForM2，3次真实请求，各候选与解析相同。LLM承担受限工具编排，当前结果没有证明更好的数值设计。`InterpretVerificationFeedback`在first-shot返回NO_M2_FEEDBACK_IN_FIRST_SHOT。`AllocationStrategyPolicy.propose(history)`对llm_agent明确返回REAL_LLM_REPAIR_NOT_IMPLEMENTED；有接收反馈回执不等于又调用LLM修复。

`feedback_agent.py/run_repair_agent`提供可注入decide接口及MockRepairPolicy，用于独立工具链/模拟反馈测试，自己不执行M2。不能把mock、保存proposal重验、真实确定性repair计作新LLM调用。

Stage6A中不存在真实Region Planner、BO或双层Agent。Stage6B的区域候选池仍为确定性逻辑，真实LLM调用为0、无BO/TuRBO、无学习式多保真调度。

## 5. Feedback / Repair

源码：`allocation/repair.py/interpret_feedback, repair`、`pipeline_contracts.py/make_feedback`、`allocation/__init__.py`。反馈必须版本正确、候选规范化哈希一致、来源M2或显式SIMULATED、verdict为FAIL/UNKNOWN。

可靠BW失败时取 a=BWtarget_mid/BWmeasured>0，并提出

\[
R'=R/a,\quad I'=a^2 I,\quad C'_1=C_1,\ C'_2=C_2,\ Kvco'=Kvco,\ f'_0=f_0.
\]

因K'=a²K、R'=R/a，L'(s)=L(s/a)，理想连续UGF/BW随a缩放、q/x和PM保持。依据是当前理想小信号模型的尺度不变性；不能保证真实事件模型误差也不变，所以必须完整M2复验。

直接缩放若违反原范围则调用旧optimize做联合重分配。PM失败时重新选择电容比/shape（analytical）；调谐不可达或捕获假设时投影f0向中心；MULTIPLE用optimize。UNRELIABLE_MEASUREMENT只请求重测，MODEL_OUT_OF_DOMAIN只请求模型诊断，不盲目优化；相同候选哈希会停止重复仿真。

**关键限制**：直接BW缩放只构建合法候选，本函数没有强制“全部M1规格必须PASS才返回”。Runner会重新记录全部M1，但为了保持比较链，M1_SPEC_FAIL合法候选仍可能执行M2。Stage5 S3/random11修复后M2 BW294644.315Hz通过、M1 PM45.661369°不满足50°，不能称联合成功。Stage6A `study.joint_judgment`明确合取内部调谐、M1 PM与收敛M2 BW、必要时capture/deadline，强制此反例FAIL。

Stage6A实际a=295000/301453.584583，将边界M1 BW299500降到293088.2Hz，PM70.043687°保持，完整M2 BW294926.116949Hz，包络完全在290–300kHz，研究联合可行。PM裕量仅0.0437°，不是鲁棒保证。

该公式不能修复周期PM认证、未知频率精度、静态相位测量缺口、Jitter/Power或模型超域；也没有捕获时间的单调缩放保证。f0中心化只是捕获假设，Stage6A未执行捕获修复。

## 6. Unified Pipeline、预算和判决

`pipeline.run_pipeline`顺序：加载/绑定输入→可选场景和可信父反馈→创建不存在的新目录→保存输入/源哈希/run_manifest→必要条件预检→policy.propose→**submitted及initial候选先写盘**→域检查/M1→AllocationProposal→独立M2准入→检查预算和源输入未变→真实完整M2→check_result→保存反馈/回执→允许的下一次完整候选→最终cost_events、trace、候选、result与report。

M1失败不自动取消合法候选的M2，因此Random首发也实际测量；声明域/有效域失败则拒绝。首次Agent内部M1计算可发生在正式submission前，仍计费；首次完整M2前候选必须已冻结。M2测量前不使用proposal预测来设BW交越；测完后才做M1_posthoc差异计算。

Meter分别限制analytic_calls和M1_calls，M2整次预算在Runner检查；每次完整M2含多次原生运行。repair预算必须小于M2预算，保证首次和修复都能计入。native完成/失败、积分点、原生秒、posthoc M1、LLM调用、总墙钟分列，金额未知保存null。无法完整插桩的测试内部调用不能猜总数。

正式M2每个required指标按收敛包络判决：包络完全在允许区间内PASS；整体在外FAIL；交叠或缺失UNKNOWN。任一可靠required FAIL使overall FAIL；无FAIL但有UNKNOWN则UNKNOWN；全部独立required PASS才PASS。pipeline标签M2_PARTIAL_PASS表示有单项PASS但overall仍UNKNOWN，verified_joint_block_spec仍false。CLI退出码0可以表示正常执行的FAIL/UNKNOWN，不能拿退出码当可行判决。

UNKNOWN测量/模型反馈先停止诊断，未解决严格PM/频率不会强行用调参“修好”。Stage6A研究联合可行是混合M1/M2证据的限定结果，不等于正式完整认证。

## 7. 已发现的 Stage6B，作为独立扩展保留

真实源码在 `source_variants/stage6b/pll_allocation/allocation/multispec_constraints.py`、multispec_search.py和pipeline.py。统一研究约束来源、包络判决、词典序目标；A为Analytical，B为原Sensitivity/SLSQP，C与B同首次点再做有限反馈。Vreq扰动重建f0；Kvco扰动同时重建I保持乘积、重建f0保持Vreq；离散电容/增益分摊池供确定性区域访问。BW失败方向使用敏感度与有限回退，并仍须M2。

C每对使用固定锚点，捕获量化包络重叠只记分辨率重叠，非重叠才支持方向；不确定性停止诊断。缓存绑定源/候选/协议及原证据全文件SHA，命中仍消耗候选槽，不重复计新M2。B1 C37→33µs与解析持平，B2 24→23µs包络重叠且主裕量没改善；正式实验首发均已可行，不能宣称通用失败恢复或普遍优于解析。其代码、历史实验与边界单列保留，非Stage6A功能。
