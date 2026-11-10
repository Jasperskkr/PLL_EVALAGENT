"""Build the three required scientific reports from retained Stage 1.5 evidence."""
from __future__ import annotations
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'outputs/block_space_v1_20261104_01'
DOC=ROOT/'docs/stage1_5'


def write_new(name,text):
    with (DOC/name).open('x',encoding='utf-8') as stream:
        stream.write(text.rstrip()+'\n')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    model=read(ROOT/'configs/BLOCK_SPACE_MODEL_V1.json')
    summary=read(RUN/'summary.json')
    registry=read(ROOT/'configs/PLL_EQUATION_REGISTRY_V1.json')['equations']
    rows=[read(p) for p in sorted((RUN/'cases').glob('*/result.json'))]
    byid={r['case']['case_id']:r for r in rows}
    sensitivities=read(RUN/'sensitivity.json')
    ref=read(RUN/'REFERENCE_BLOCKSPEC.json')
    valid=[r for r in rows if r['forward']['prediction']]
    agreeing=[r for r in rows if r.get('event',{}).get('conditional_frequency_control_agreement')]
    events=[r for r in rows if r.get('event',{}).get('status')=='COMPLETED']
    warm=read(ROOT/'outputs/block_space_warmstart_diagnostic_20261104_01/result.json')
    longer=read(ROOT/'outputs/block_space_boundary_diagnostic_20261104_01/result.json')
    eq=['# EQUATION_MAPPING_REPORT', '', '2026-11-04 · Stage 1.5。System Performance ← Physical Equations ← Block Variables。', '',
        '唯一实验依据为 Stage 1 配置的哈希快照：10 MHz、N=8、80 MHz，BW 150–300 kHz、PM≥50°；UGF 为诊断。Stage 1 的 draft=true 保留，仅在本阶段固定输入；未把旧 MATLAB 的 100–400 kHz / 45° 混入本轮目标。', '',
        '|系统量|方程链|共同变量|当前证据层级|','|---|---|---|---|',
        '|条件输出频率、调谐电压|E_FREQ_PLAN → E_TUNING|N、fref、f0、Kvco、Vmin/Vmax|解析与数值；32 个事件点中的条件稳态检查|',
        '|BW|E_KPFD → E_LF → E_OPEN → E_CLOSED → E_BW|Icp、Rz、C1、C2、Kvco、N|连续 M1 数值一致性；无事件注入测量|',
        '|PM|E_KPFD → E_LF → E_OPEN → E_UGF → E_PM|同上|连续 M1 数值一致性；无事件注入测量|',
        '|UGF（诊断）|E_OPEN → E_UGF|同上|连续 M1 数值一致性|', '',
        '机器注册表为 `configs/PLL_EQUATION_REGISTRY_V1.json`，含每条公式的输入/输出、单位、层级、来源绝对路径/SHA、实现符号和证据。下面逐项给出 What / How / Domain / Evidence / Limitations。']
    for e in registry:
        eq += ['',f'## {e["equation_id"]} · {e["title"]}', '',f'**What**：{e["what"]}', '',f'**公式**：`{e["expression"]}`', '',
            f'**How**：{e["how"]} 输入：{", ".join(e["inputs"])}；输出：{", ".join(e["outputs"])}。', '',
            f'**Domain**：{"; ".join(e["domain"])}。单位/转换：{e["units_and_conversions"]}。', '',
            f'**Evidence**：来源 `{e["source"]}`；实现 `{e["implementation"]["path"]}::{e["implementation"]["symbol"]}`。',
            '本轮 124 个有效 M1 点均与独立 ω² 幅度多项式求根一致；原有独立两节点 KCL 阻抗测试保留。调谐/频率另有稀疏事件 TB 证据；事件 TB 没有测量 BW/PM/UGF。', '',
            f'**Limitations**：{e["limitations"]}']
    eq += ['', '## 语义、稳定性和交越专项审核', '',
        'Kvco 输入是 Hz/V，进入相位积分增益时仅乘一次 2π。f0 是 0 V 截距；旧 v1 的 V0 锚点需要显式转换。LF 连接是 C1 并联 Rz-C2 串联支路，禁止交换 C1/C2。CP 的 q0、leakage、mismatch、reset 均显式为零，非零时不能借理想 Kpfd 验收。相位约定 ref-div rad，与旧 v1 符号相反。', '',
        '正值理想网络中，|L|²=K0²(1+ω²/ωz²)/(ω⁴(1+ω²/ωp²))。对 logω 的导数为 2A−4−2B<−2，其中 0<A,B<1，因此 |L| 严格递减，正频轴仅一个单位增益交越。BW 的 x=ω² 多项式系数符号为 +、任意、−、−，恰有一次符号变化，因此仅一个正根。', '',
        '三阶 Routh 差值 bc−ad=(Icp*Kvco/N)*Rz*C2²>0。声明的正值理想域不会产生连续模型不稳定点；低 PM 属于规格违例，不能贴“连续不稳定”标签。负 R 或负增益的扩展是域外反例，程序拒绝它们。该证明不能外推到采样/延迟/非理想系统。', '',
        '数值测试对无交越、多个下降交越和非有限残差均要求 NUMERICAL_FAILURE。当前公式族中多交越由解析关系排除，泛化到别的拓扑必须重新处理相位展开、交越选择及稳定性判据。', '',
        '独立数值路径验证的是方程实现正确性，不能把两个同源公式实现的吻合称为行为真实性。BW/PM 的外部行为误差目前为空值/NOT_ESTABLISHED，而不是零。']
    write_new('EQUATION_MAPPING_REPORT.md','\n'.join(eq))

    domain=['# DOMAIN_VALIDATION_REPORT', '', '2026-11-04 · Stage 1.5。输入/目标保持 Stage 1，不扩域、不调低门限。', '',
        '## A. Declared Parameter Domain', '',
        '六个可分配参数如下；其余固定系统条件或理想模型假设。均为人工定义的行为实验范围，未包装成已验证的器件实现能力。', '',
        '|参数|范围或 choices|Nominal|单位|范围选择理由|','|---|---|---:|---|---|']
    for name in ('Icp','Rz','C1','C2','f0','Kvco'):
        a=model['variables'][name]
        limits=str(a['choices']) if 'choices' in a else f"{a['range']['min']} … {a['range']['max']}"
        domain.append(f'|{name}|{limits}|{a["default"]}|{a["unit"]}|{a["range_rationale"]}|')
    domain += ['', 'PFD reset=0、CP mismatch/leakage/q0=0，VCO Kvco2=0，Cload=Gload=0。N=8，fref=10 MHz，Vctrl∈[0,1.2]V。', '',
        '## B. Model Validity Domain', '',
        '声明域 ∩ 正值 SI 参数 ∩ 理想假设 ∩ 正且单调 VCO ∩ 严格内部调谐点 ∩ 可解析稳定性 ∩ 数值上有效的交越。联合调谐限制为 `0 < (80e6-f0)/Kvco < 1.2`；不是单独验证 f0 与 Kvco 的范围就足够。', '',
        '声明域未因事件采样结果被私自收缩或扩大。全域行为可信度另列为 NOT_ESTABLISHED；证据只针对被实际测量的点。距轨 1 mV 及更小裕量的区域已有不良捕获诊断，应作为后续 allocation 风险提示，不能因为 M1 有解而自动宣布捕获成功。', '',
        '## C. SystemSpec Feasible Region', '',
        '在 B 域中再要求 BW∈[150,300]kHz、PM≥50°及条件锁定频率 80 MHz。UGF 不参与通过判定。本轮找到 44 个 M1 通过点，证明存在可行候选；这些点不构成对整个高维可行域的精确求解，也不是均匀随机成功率估计。', '',
        '## 扫描计划与全部成本', '',
        '评估前已保存 `candidate_snapshots.json` 和 `validation_plan.json`。固定名义点、±2%局部扰动、单轴上下界及1%邻域、连续参数16角点、电容组合、48点Halton、Icp/Rz各17点固定切片、调谐轨附近点、增益乘积不变点及高低增益折中点；去除重复后按类别保留 alias。没有自适应逆向求解器或优化器。', '',
        f'共 {summary["case_count"]} 点：声明域内 {summary["declared_cases"]} 点 + 域外异常 5 点；124 点有效 M1，44 点 M1_SPEC_PASS、80 点 M1_SPEC_FAIL、15 点 UNKNOWN。域内有10点无内部调谐点；另5点是域外符号/非理想异常。', '',
        '|采样类别|唯一点数|','|---|---:|']
    domain += [f'|{k}|{v}|' for k,v in summary['category_counts'].items()]
    domain += ['', '每个候选在任何计算前写盘；每点保存参数、联合域检查、预测、独立参考、误差、事件结果及失败原因。机器表格：`outputs/block_space_v1_20261104_01/FORWARD_MODEL_VALIDATION.csv`。', '',
        f'本轮域扫描：124次M1、124次独立多项式参考、64次Python事件仿真（32点×两步长），{summary["cost"]["Python_event_integration_points"]:,}个积分点。另做边界诊断4次事件仿真；MATLAB Runtime=0，LLM=0。测试中的2µs稳态不变量是额外短仿真，不混入32点统计。', '',
        '## 第一类：数值与公式验证', '',
        '|误差|最大值|门限|','|---|---:|---:|',
        f'|UGF 相对误差|{summary["maximum_numerical_errors"]["UGF_Hz"]:.3e}|0.005|',
        f'|BW 相对误差|{summary["maximum_numerical_errors"]["BW_Hz"]:.3e}|0.005|',
        f'|PM 绝对误差|{summary["maximum_numerical_errors"]["PM_deg"]:.3e}°|0.2°|',
        '|Vreq 绝对误差|0 V|1e-6 V|', '',
        '124个有效点全部通过独立数值门限。正值理想网络连续稳定已解析证明；域外负R/负增益拒绝。无交越、多交越、非有限数值测试明确拒绝。', '',
        '## 第二类：事件行为交叉验证', '',
        '原 MATLAB 工程中已有 `verification/python_crosscheck.py::simulate` 被按字节快照到新数据目录，SHA=f6f55027622840cb62090e3870c29b75c23824b27fa786689605b7c6196706e2。通过 AST 仅提取 simulate，原文件和 check() 的写盘流程未执行。该模型为固定步长、边沿分数插值 PFD/CP、Euler KCL、VCO相位积分、0..1.2V控制限幅；不是纯平均线性模型，也不是精确事件求解器。', '',
        '预设初值0.15V、160µs窗口、最后20%统计；粗步长1/(25*fmax)，再减半。门限提前落盘：步长频率差≤1ppm、控制端点差≤0.1mV、相位RMS差≤0.1°；条件频率预测误差≤100ppm、控制端点差≤1mV。**这些是交叉验证门限，不是替换冻结SystemSpec的1e-6Hz频率允差。**', '',
        '32点全部完成且满足两档步长比较门限。26个有内部锁点且尾窗有跟踪观测的点获得条件频率/控制一致性证据；6点不一致/不可比较，均保留：', '',
        '|点|标签|M1结论|事件尾均频率 / Hz|Vctrl末值 / V|原因|','|---|---|---:|---:|---|']
    for cid in summary['event_nonagreement_ids']:
        r=byid[cid]; e=r['event']; fine=e['runs'][-1]
        domain.append(f'|{cid}|{r["case"]["label"]}|{r["forward"]["judgment"]["verdict"]}|{fine["fout_avg"]:.6f}|{fine["vfinal"]:.9f}|调谐无内部点或近轨捕获未建立；存在近轨样点|')
    domain += ['', '这26点的最大条件频率误差为 '+f'{max(abs(r["event"]["errors"]["frequency_prediction_error_ppm"]) for r in agreeing):.6g} ppm，控制端点误差最大 '+f'{max(abs(r["event"]["errors"]["Vctrl_endpoint_prediction_error_V"]) for r in agreeing):.6g} V。', '',
        'C130：f0=68.01MHz、Kvco=10MHz/V，Vreq=1.199V。160µs冷启动停在上轨，频差约+125ppm；延长到640µs、两步长仍约+125ppm，尾窗相位RMS约53.77°。这不能证明永久无法捕获。将同一参数从Vreq启动后，160µs尾频差约 '+f'{warm["runs"][-1]["summary"]["ppm"]:.6g} ppm，Vctrl≈{warm["runs"][-1]["summary"]["vfinal"]:.12f}V且无近轨样点。说明本点具备局部锁定点一致性，但冷启动捕获受限幅/初值/有限窗口影响；不得把已锁定M1外推到捕获。', '',
        '长窗口和暖启动是新的诊断记录，位于 `outputs/block_space_boundary_diagnostic_20261104_01/` 和 `outputs/block_space_warmstart_diagnostic_20261104_01/`。原失败结果未覆盖。参考simulate在“窗口中从未超2%频差”时返回settle_us=NaN，已显式转换为null并记录缺失，未将其当作锁定时间。', '',
        '事件模型只返回摘要，无原始轨迹/持锁协议；无BW/PM注入。不能宣称全M2系统验收、完整Lock Time或Static Phase Error支持。', '',
        '## 敏感度与耦合', '',
        '|参数|方法|BW log弹性|UGF log弹性|PM变化/1%参数|Vreq log弹性|','|---|---|---:|---:|---:|---:|']
    for x in sensitivities:
        domain.append(f'|{x["parameter"]}|{"局部±2%" if x["method"].startswith("local") else "离散端点割线"}|{x["BW_log_elasticity"]:.4f}|{x["UGF_log_elasticity"]:.4f}|{x["PM_deg_per_one_percent"]:.6f}°|{x["Vreq_log_elasticity"]:.4f}|')
    domain += ['', '在名义点附近，Icp和Kvco对BW的弹性均约0.927，Rz约0.855；两者Icp×Kvco/N共同决定环路增益。名义点附近PM对Icp/Rz一阶变化很小，不能外推到整个域。C1/C2比值显著改变最大可达PM；电容行是离散端点割线，不应当作连续局部导数。f0不改变理想线性环路，却显著改变调谐裕量。', '',
        '解析上PM峰值为 atan(sqrt(C2/C1+1))−atan(1/sqrt(C2/C1+1))，对应ω=sqrt(ωzωp)。因此PM≥50°的必要条件为 C2/C1≥约6.55；这不是充分条件，因为UGF必须落在合适的频率位置，且BW还有边界。', '',
        '## 典型参考、违例与边界', '',
        '推荐点固定为本轮之前的Stage1名义点：Icp=100µA、Rz=3820Ω、C1=100pF、C2=1nF、f0=72MHz、Kvco=20MHz/V、Vctrl∈[0,1.2]V。Vreq=0.4V，UGF≈138176.441Hz，BW≈222379.183Hz，PM≈56.442690°。BW下界/上界裕量分别72.379/77.621kHz，PM裕量6.443°，电压裕量0.4V。保存为M1_VALIDATED；没有全M2签发。', '',
        '|点|BW / kHz|PM / deg|结论|','|---|---:|---:|---|']
    for cid in ('C000','C009','C013','C014','C122','C123','C132','C133'):
        r=byid[cid]; m=(r['forward']['prediction'] or {}).get('metrics',{})
        domain.append(f'|{cid} {r["case"]["label"]}|{m.get("BW_Hz",0)/1000:.6f}|{m.get("PM_deg",0):.6f}|{r["forward"]["judgment"]["verdict"]}|')
    domain += ['', 'Rz切片在C121与C122附近跨过BW上限；C122的BW=300.760kHz、PM=50.585°，体现BW先失败。C123 PM=48.882°且BW=310.694kHz。上下界和PM边界没有被重设以制造成功。BW下限附近也可能PM不足，因此单项满足不代表联合通过。', '',
        f'本轮样本最高UGF/fref≈{max(r["forward"]["prediction"]["diagnostics"]["UGF_over_fref"] for r in valid):.4f}、BW/fref≈{max(r["forward"]["prediction"]["diagnostics"]["BW_over_fref"] for r in valid):.4f}；这些高比值区域的BW/PM采样效应仍未被验证，不把该最大值当作全域理论界。', '',
        '## 未解决区域与下一步最小验证', '',
        '优先保留M1为已支持BW/PM的评估器；补可重用事件波形与相位调制注入，对名义点、BW/PM边界、高UGF/fref和近轨点建立收敛的闭环响应测量。先测BW与T频响；PM若无独立开环注入/闭环辨识协议继续标未验证。捕获另需多初值、较长窗口、无cycle-slip持锁协议。非理想CP、reset、负载、曲率、噪声与功耗均不属于当前支持域。']
    write_new('DOMAIN_VALIDATION_REPORT.md','\n'.join(domain))

    readiness='''# BLOCK_SPACE_READINESS_REPORT

## WHAT：最终得到了怎样的 Block Space Model？

得到可加载的 Behavioral Block Space Model v1，位于 `configs/BLOCK_SPACE_MODEL_V1.json`。它包含17个实际输入/假设、41项语义目录、固定拓扑、原样保留的Stage1实验配置、7项可执行联合关系、版本/来源、逐指标可信度和校准记录合同。Declared Domain、Model Validity、M1 SystemSpec Feasible Region分开判定。已完成本阶段，等待技术Leader审阅；未启动Stage2。

## HOW：变量范围如何建立，系统指标如何映射？

1. 当前可分配参数只有Icp、Rz、C1、C2、f0、Kvco。Icp=50–200µA、Rz=2–8kΩ、C1∈{50,100,200}pF、C2∈{0.5,1,2}nF、f0=60–76MHz、Kvco=10–40MHz/V，完整继承Stage1的人工行为范围，未扩域。PFD非理想项、N、参考频率、电压上下限固定。
2. 每个轴保存单位、上下界/choices、nominal、来源、选择理由、角色、适用条件和是否参与计算。范围不是已验证的器件能力。新版loader不能把新契约硬塞进旧v1 Runner；新实验Runner可以直接调用load_model/make_candidate/check_parameters/forward，旧入口保持不变。
3. 显著耦合为Icp×Kvco/N、Rz/C1/C2的零极点与最大PM、f0/Kvco/Vctrl的内部调谐限制。CP非理想与静态偏移存在关系，但当前无可信模型，明确UNSUPPORTED。
4. 系统条件保持10MHz×8=80MHz，支持的SystemSpec为条件频率/内部调谐、连续BW150–300kHz、PM≥50°；UGF只诊断。Jitter、Lock Time、Static Phase Error、功耗未受支持。

## EVIDENCE：哪些计算和实验支持这套模型？

139点记录包含134点声明域内代表采样和5个异常；124个有效M1点全数值一致，44个M1通过、80个M1失败、15个UNKNOWN。32点共64次既有Python边沿插值事件TB获得独立行为摘要，26点条件频率/控制一致；6点的不可调谐/轨边或未捕获情况原样保存。另有4次近轨长窗口/暖启动诊断。

正式参考BlockSpec为预先指定名义点，保存于 `outputs/block_space_v1_20261104_01/REFERENCE_BLOCKSPEC.json`：BW≈222.379kHz、PM≈56.443°、Vreq=0.4V，有约6.443°PM裕量与72.379kHz带宽下界裕量。状态为M1_VALIDATED。名义点另有事件尾频率/控制比较证据，但不代表全部SystemSpec经过M2验收。

## UNCERTAINTY：哪些范围、公式和指标仍不够准确？

BW/PM/UGF仅得到连续公式的独立数值一致性，行为预测误差尚未建立；不能把近机器精度数值误差当模型误差。事件TB为固定步长Euler摘要、稀疏点、有限窗口，无通用锁定证书。C130距上轨仅1mV，从0.15V冷启动到640µs仍无尾窗跟踪，从Vreq暖启动则保持频率；局部锁定点与捕获能力不同。离轨远、高UGF/fref、未测初值/参数组合均不能整体宣称已验证。

校准记录包含Formula/Parameter Domain/Behavioral Model版本、参数哈希、原预测/观测、单位、两边测量协议、证据、原始误差、局限、建议和原因分类。数值错误、假设不适用、语义冲突、缺失效应、协议不一致和未决六类分开。记录不修正原公式，不实现残差拟合。

## READINESS：现在可以支持哪些 Spec Allocation 实验？

足以在严格标注M1范围的前提下，作为下一阶段低成本逆向Allocation原型的候选检查/正向评估接口：分配上述6参数，目标仅为当前频率、连续BW/PM。可研究联合可行性与数值算法行为；不能据此报告完整事件TB的first-shot成功率、捕获/锁定时间、jitter或硅实现能力。44个通过点提供存在性证据，不是整个搜索域的概率成功率。真正用于行为验收的评估器仍须补强。

## NEXT：优先逆向分配器，还是关键行为模型？

建议技术Leader优先批准一个小范围、可保存波形的事件响应/注入验证模块，聚焦BW/PM预测与捕获边界。原因是M1数值实现已在代表域内充分自洽，而尚缺独立动态测量，近轨诊断已经暴露不能把锁定线性模型外推到捕获的风险。M1逆向原型具备接口条件，可在明确其研究标签后另行批准；本阶段不自行启动。

交付索引：机器模型 `configs/BLOCK_SPACE_MODEL_V1.json`；机器公式注册表 `configs/PLL_EQUATION_REGISTRY_V1.json`；公式报告与本报告同目录；域报告 `DOMAIN_VALIDATION_REPORT.md`；逐点CSV和参考BlockSpec在主运行目录。最终测试、保护核对和实际命令见 `ACCEPTANCE.md`。
'''
    write_new('BLOCK_SPACE_READINESS_REPORT.md',readiness)
    print('Wrote Equation Mapping, Domain Validation and Readiness reports from retained results.')


if __name__=='__main__':
    main()
