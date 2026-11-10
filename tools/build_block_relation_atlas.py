"""Read-only PLL relation tables and conditional M1 domains. Never runs M2 or a policy."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import itertools
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pll_allocation.allocation.core import bounds, Meter, assess_m1, values
from pll_allocation.allocation.physics import bandwidth_ratio, phase_interval, pm_ceiling
from pll_allocation.block_space.contracts import make_candidate, check_parameters
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.pipeline_contracts import load_inputs


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def write(path, obj):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def finite_positive(*args):
    if any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in args):
        raise ValueError('finite positive numbers required')


def tuning_interval(model, kvco):
    """Exact f0 interval, with strict tuning endpoints and closed declaration endpoints."""
    finite_positive(kvco)
    klo, khi = bounds(model, 'Kvco')
    if not klo <= kvco <= khi:
        raise ValueError('Kvco outside declared domain')
    axes = model['variables']
    target = axes['N']['fixed'] * axes['f_ref']['fixed']
    flo, fhi = bounds(model, 'f0')
    lower_rail = target - kvco * axes['Vctrl_max']['fixed']
    upper_rail = target - kvco * axes['Vctrl_min']['fixed']
    lo, hi = max(flo, lower_rail), min(fhi, upper_rail)
    lc, hc = lo > lower_rail, hi < upper_rail
    empty = lo > hi or (lo == hi and not (lc and hc))
    return {'min': lo, 'max': hi, 'min_inclusive': lc, 'max_inclusive': hc,
            'empty': empty, 'unit': 'Hz'}


def product_split(model, product, f0=None):
    """P=Icp*Kvco: Kvco interval, optionally intersected with tuning at a fixed f0."""
    finite_positive(product)
    ilo, ihi = bounds(model, 'Icp')
    klo, khi = bounds(model, 'Kvco')
    lo, hi = max(klo, product / ihi), min(khi, product / ilo)
    lc, hc = True, True
    if f0 is not None:
        if type(f0) not in (int, float) or not math.isfinite(f0):
            raise ValueError('finite f0 required')
        flo, fhi = bounds(model, 'f0')
        if not flo <= f0 <= fhi:
            raise ValueError('f0 outside declared domain')
        axes = model['variables']
        target = axes['N']['fixed'] * axes['f_ref']['fixed']
        # This research derivation is explicitly bound to the current [0, 1.2] V model.
        if axes['Vctrl_min']['fixed'] != 0 or f0 >= target:
            raise ValueError('this split requires Vmin=0 and f0<F')
        threshold = (target - f0) / axes['Vctrl_max']['fixed']
        lo = max(lo, threshold)
        lc = lo > threshold
    return {'min': lo, 'max': hi, 'min_inclusive': lc, 'max_inclusive': hc,
            'empty': lo > hi or (lo == hi and not (lc and hc)), 'unit': 'Hz/V'}


def bandwidth_domain(model, spec, c1, c2, x):
    """Exact conditional BW interval for fixed legal C1,C2,x under the current model.

    beta is an existing numerical scalar root. The interval describes mathematical
    existence in M1, including current/gain limits and existential tuning; it is
    neither a global optimizer nor a behaviorally verified domain.
    """
    finite_positive(c1, c2, x)
    axes = model['variables']
    if c1 not in axes['C1']['choices'] or c2 not in axes['C2']['choices']:
        raise ValueError('capacitors must be original discrete choices')
    by = {row['metric']: row for row in spec['metrics']}
    target = axes['N']['fixed'] * axes['f_ref']['fixed']
    freq = by['output_frequency_Hz']
    if not freq['min'] - freq['tolerance'] <= target <= freq['max'] + freq['tolerance']:
        return {'status': 'EMPTY', 'reason': 'fixed frequency plan conflicts with SystemSpec'}
    phase = phase_interval(c1, c2, by['PM_deg']['min'] - by['PM_deg'].get('tolerance', 0))
    if phase is None or not phase[0] <= x <= phase[1]:
        return {'status': 'EMPTY', 'reason': 'PM shape necessary condition fails', 'x': x}
    q = 1 + c2 / c1
    beta = bandwidth_ratio(q, x)
    h = math.sqrt((1 + (x / q) ** 2) / (1 + x*x))
    ar = x * beta / (2 * math.pi * c2)  # Rz=ar/B
    ap = axes['N']['fixed'] * (c1+c2) * (2*math.pi / beta)**2 * h  # P=ap*B^2
    ilo, ihi = bounds(model, 'Icp')
    klo, khi = bounds(model, 'Kvco')
    flo, fhi = bounds(model, 'f0')
    # All legal Kvco values have at least one interior f0. Check before using P box.
    if not (axes['Vctrl_min']['fixed'] == 0 and fhi < target
            and target - klo * axes['Vctrl_max']['fixed'] < fhi):
        raise ValueError('existential tuning simplification not valid for this model')
    rlo, rhi = bounds(model, 'Rz')
    constraints = {
        'SystemSpec': [by['BW_Hz']['min'], by['BW_Hz']['max']],
        'Rz': [ar/rhi, ar/rlo],
        'gain_product': [math.sqrt(ilo*klo/ap), math.sqrt(ihi*khi/ap)],
    }
    lo, hi = max(v[0] for v in constraints.values()), min(v[1] for v in constraints.values())
    return {'status': 'NONEMPTY' if lo <= hi else 'EMPTY', 'x': x, 'q': q,
            'beta': beta, 'h': h, 'a_R': ar, 'a_P': ap,
            'BW_min_Hz': lo, 'BW_max_Hz': hi, 'intersections_Hz': constraints,
            'existential_tuning_checked': True,
            'scope': 'CONDITIONAL_M1_MATHEMATICAL_DOMAIN',
            'verified_joint_block_spec': False}


def witness(model, domain, c1, c2, fraction=0.5):
    if domain['status'] != 'NONEMPTY':
        raise ValueError('empty conditional domain')
    if not 0 <= fraction <= 1:
        raise ValueError('fraction outside [0,1]')
    bw = domain['BW_min_Hz'] + fraction * (domain['BW_max_Hz'] - domain['BW_min_Hz'])
    product = domain['a_P'] * bw*bw
    split = product_split(model, product)
    if split['empty']:
        raise ArithmeticError('unexpected empty split')
    kvco = (split['min'] + split['max']) / 2
    tune = tuning_interval(model, kvco)
    if tune['empty']:
        raise ArithmeticError('unexpected empty tuning')
    f0 = (tune['min'] + tune['max']) / 2
    candidate = make_candidate(model, {'Icp': product/kvco, 'Kvco': kvco, 'f0': f0,
                            'Rz': domain['a_R']/bw, 'C1': c1, 'C2': c2})
    return candidate, bw


def kcl_response(p, frequency):
    """Solve two-node LF KCL via its 2x2 determinant, independent of reduced Z formula."""
    s = 2j * math.pi * frequency
    g = 1/p['Rz']
    a, b, c, d = s*p['C1']+g, -g, -g, s*p['C2']+g
    z = d / (a*d-b*c)  # response to 1 A at control node
    loop = p['Icp'] * p['Kvco'] * z / (p['N'] * s)
    return z, loop, loop/(1+loop)


def relation_rows():
    # Display formulas are curated views of the registered equations; not a second evaluator.
    def row(rid, block, ids, formula, domain, evidence, eq=(), inverse=''):
        return {'id': rid, 'block': block, 'variable_ids': ids.split(), 'formula': formula,
                'domain': domain, 'inverse': inverse, 'evidence': evidence, 'equation_ids': list(eq)}
    return [
        row('R_SYSTEM','System-level','f_ref N f_target spec_output_frequency_Hz spec_BW_Hz spec_PM_deg',
            'F = N·f_ref = 80 MHz; 150 ≤ BW ≤ 300 kHz; PM ≥ 50°',
            'f_ref = 10 MHz；N = 8；频率容差 1 µHz。SystemSpec 原 draft 元数据保留；Stage5 研究场景另有显式绑定。',
            '输入快照 / 正式判决仅三项', ['E_FREQ_PLAN']),
        row('R_ASSUMPTIONS','固定模型假设','Kvco2 CP_mismatch CP_leakage q0 PFD_reset_delay Cload Gload',
            'Kvco2 = CP_mismatch = CP_leakage = q0 = PFD_reset_delay = Cload = Gload = 0',
            '各量分别按原单位等于零；非零为 UNSUPPORTED。无器件、噪声、延时和动态负载能力承诺。',
            '原 M1 parser / J_IDEAL'),
        row('R_PFD','PFD','phase_err PFD_reset_delay f_ref',
            'φe = wrap(φref − φdiv); Δt = φe / (2π·f_ref)',
            'phase_err 约定 [−π, π) rad；关系用于理想局部平均化；reset = 0。φe 不是新的分配轴。',
            '语义约定 / 小信号推导', ['E_KPFD']),
        row('R_CP','Charge Pump','Icp Iup Idown Kpfd',
            'Iup = Idown = Icp; Kpfd = Icp/(2π); īCP = Kpfd·φe',
            'Icp ∈ [50, 200] µA；Kpfd ∈ [7.957747, 31.830989] µA/rad。',
            '已实现 M1 / 公式注册', ['E_KPFD'], 'Icp = 2π·Kpfd；与 Kvco 必须按乘积联合分配。'),
        row('R_LF','Loop Filter','Rz C1 C2 Zlf Cload Gload',
            'Z(s) = (1+s·Rz·C2) / [s·(C1+C2)+s²·Rz·C1·C2]',
            'Rz ∈ [2, 8] kΩ；C1 ∈ {50,100,200} pF；C2 ∈ {0.5,1,2} nF。C1 对地，并联串联 Rz–C2 支路。',
            '已实现 M1 / KCL 数值核验', ['E_LF']),
        row('R_LF_SHAPE','LF 零极点','Rz C1 C2 fz fp',
            'fz = 1/(2π·Rz·C2); fp = (C1+C2)/(2π·Rz·C1·C2); q = fp/fz = 1+C2/C1',
            's 平面极点为 0 与 −2π·fp；fz、fp 是正的频率幅值。离散电容对决定 q。',
            '已实现 M1 / 精确代数', ['E_LF_ZP'], '给定 C1,C2 及 fz 或形状 x、ωu，可反解 Rz；不得独立选 fz 和 fp。'),
        row('R_VCO','VCO','f0 Kvco Vctrl_min Vctrl_max Vctrl_required tuning_feasible Kvco_local Kvco_angular',
            'f(V) = f0+Kvco·V; Vreq = (F−f0)/Kvco; Kvco_angular = 2π·Kvco',
            'f0 ∈ [60,76] MHz；Kvco ∈ [10,40] MHz/V；0 < Vreq < 1.2 V。f0 为零伏截距，非中心电压频率。',
            '条件调谐解析 / 有限事件点支持', ['E_TUNING'],
            'f0 ∈ [60,76] MHz ∩ (F−1.2·Kvco, F)；Kvco_local = Kvco。开端点必须保留。'),
        row('R_DIVIDER','Divider','N f_ref f_target',
            'f_div = f_out/N; H_div = 1/N; N = 8',
            '理想整数分频、无分配自由度；无 delay/jitter/power 模型。',
            '固定拓扑 / 已实现模型', ['E_FREQ_PLAN','E_OPEN']),
        row('R_LOOP','Loop 动态','Kpfd Kvco_angular Zlf L T',
            'P = Icp·Kvco; K = P/N; L(s) = K·Z(s)/s; T(s) = L(s)/(1+L(s)); Href = N·T',
            's = j2πf；2π 在 CP 与 VCO 增益间相消。P ∈ [500,8000] A·Hz/V 为声明轴乘积范围。',
            '已实现 M1；历史局部 M2 支持', ['E_OPEN','E_CLOSED'],
            '同 RC 和相同 P 保持理想动态；f0/Kvco 仍需满足调谐。'),
        row('R_BW','Bandwidth','BW T',
            '|T(j2π·BW)| = 1/√2; BW = β(q,x)·UGF',
            '归一化 T 唯一向下半功率交越；BW ∈ [150,300] kHz。β 需要数值正根，BW 不等于 UGF。',
            'M1 可解 / Protocol1.1 独立事件 BW', ['E_BW','E_CLOSED'],
            '电容枚举 + x 形状 + β 数值根，再反解 Rz 与 P 并求交。'),
        row('R_PM','Phase Margin','PM UGF L',
            'x = ωu·Rz·C2; PM = atan(x)−atan(x/q); PMmax = asin((q−1)/(q+1))',
            'ωu = 2π·UGF；x>0；相位最终转为度。PM≥50° ⇒ C2/C1≥6.548632。全域理想上界72.247210°。',
            'M1 精确形状 / M2 正式 PM UNKNOWN', ['E_PM','E_UGF'],
            'tanφ·x² − (q−1)·x + q·tanφ ≤ 0；判别式与 x 根区间给出必要形状域。'),
        row('R_UGF','Unity-gain 诊断','UGF L',
            '|L(j·ωu)| = 1; P = N·(C1+C2)·ωu²·h; h = √[(1+(x/q)²)/(1+x²)]',
            'UGF 是诊断量，当前没有 UGF/RUR 硬目标。存在一个有限向下交越；数值失败不判通过。',
            'M1 正向 / 条件代数逆解', ['E_UGF'], 'Rz = x/(ωu·C2)；正式周期 UGF/PM 尚未认证。'),
        row('R_STABILITY','连续稳定性','Icp Kvco Rz C1 C2',
            'a·s³+b·s²+c·s+d = 0; b·c−a·d = K·Rz·C2² > 0',
            'a=Rz·C1·C2，b=C1+C2，c=K·Rz·C2，d=K。原正值域下 Routh 恒成立，仍须满足 PM/BW。',
            'E_STABILITY / 非事件捕获证明', ['E_STABILITY']),
        row('R_JOINT','联合条件可行域','Icp Rz C1 C2 f0 Kvco BW PM',
            'D_M1 = D_declared ∩ D_ideal ∩ D_tuning ∩ {150≤BW≤300 kHz, PM≥50°}',
            '给定 C1,C2,x：B ∈ [Bmin,Bmax] ∩ [aR/Rmax,aR/Rmin] ∩ [√(Pmin/aP),√(Pmax/aP)]。',
            '本轮条件域推导 / 正式 M1 核验', ['E_TUNING','E_BW','E_PM'],
            'aR=x·β/(2π·C2)，aP=N·(C1+C2)·(2π/β)²·h；Rz=aR/B，P=aP·B²。见推导。'),
        row('R_SPLIT','CP ↔ VCO 分摊','Icp Kvco f0 Vctrl_required',
            'Kvco ∈ [Kvco_min,Kvco_max] ∩ [P/Icp_max,P/Icp_min]; Icp = P/Kvco',
            '若 f0 已定，再交 Kvco > (F−f0)/1.2 V；若 Kvco 已定，再交严格 f0 调谐区间。',
            '条件解析 / 同产品局部 M2 支持', ['E_TUNING','E_OPEN'],
            '本声明域任一合法 Kvco 均可选到至少一个调谐 f0；不表示给定 f0 总合法。'),
        row('R_CONTEXT','上下文 / 非执行量','V0 f_offset Vctrl0 Rload',
            's = j2π·f_offset; f0 使用 V=0 截距；V0 仅旧上下文; Gload = 0',
            'f_offset>0 为测量扫描；Vctrl0 为事件初值上下文；旧 V0/Rload 不能变成当前自由轴。',
            '原 41 项目录 / 语义兼容边界'),
        row('R_VERIFICATION','行为验收','BW PM UGF Vctrl0 phase_err',
            'D_verified ⊆ {逐个完整候选按冻结协议全部必需指标 PASS}',
            '捕获/lock time 是初值与160µs窗口条件测量。正式PM、1µHz频率认证仍 UNKNOWN；完整已认证域未建立。',
            'Stage4.1 十个局部点 / Stage5 当前结论'),
        row('R_GAPS','尚缺映射','',
            'Jitter / Phase Noise / Power / RUR：当前无可信数值可行域',
            '补噪声源与频带、功耗定义与模块模型、RUR定义及协议后才能版本化扩展。Icp 不能当总电源电流。',
            'UNSUPPORTED / 未增设 SystemSpec'),
    ]


def variable_catalog(model, rows):
    result = []
    for item in model['variable_catalog']:
        vid = item['id']
        related = [r for r in rows if vid in r['variable_ids']]
        if not related:
            raise ValueError('unmapped catalog variable: ' + vid)
        original = item['stage1_mapping']
        axis = model['variables'].get(vid)
        result.append({'id': vid, 'block': item['block'], 'kind': item['kind'], 'unit': item['unit'],
                       'participation': item['participation'], 'declared_axis': axis,
                       'semantic_definition': original['Python v2 definition'],
                       'range_text': original['Experiment range'], 'validity': original['Validity'],
                       'semantic_conflict': original['Semantic conflict'],
                       'relation_ids': [r['id'] for r in related],
                       'co_variables': sorted({v for r in related for v in r['variable_ids']} - {vid}),
                       'traceability': 'configs/BLOCK_SPACE_MODEL_V1.json#/variable_catalog/' + vid})
    return result


def derived_ranges(model):
    """Exact marginal projections only. Discrete sums/ratios remain choices."""
    ilo, ihi = bounds(model, 'Icp')
    klo, khi = bounds(model, 'Kvco')
    rlo, rhi = bounds(model, 'Rz')
    c1lo, c1hi = bounds(model, 'C1')
    c2lo, c2hi = bounds(model, 'C2')
    flo, fhi = bounds(model, 'f0')
    n = model['variables']['N']['fixed']
    target = n*model['variables']['f_ref']['fixed']
    pairs=list(itertools.product(model['variables']['C1']['choices'],model['variables']['C2']['choices']))
    return [
        {'id':'Kpfd','unit':'A/rad','range':[ilo/(2*math.pi),ihi/(2*math.pi)],'expression':'Icp/(2π)','scope':'declared projection'},
        {'id':'Kvco_angular','unit':'rad/s/V','range':[2*math.pi*klo,2*math.pi*khi],'expression':'2π·Kvco','scope':'declared projection'},
        {'id':'P','unit':'A*Hz/V','range':[ilo*klo,ihi*khi],'expression':'Icp·Kvco','scope':'declared projection; supplementary derived symbol'},
        {'id':'K','unit':'A*Hz/V','range':[ilo*klo/n,ihi*khi/n],'expression':'P/N','scope':'declared projection; supplementary derived symbol'},
        {'id':'C_sum','unit':'F','choices':sorted({a+b for a,b in pairs}),'expression':'C1+C2','scope':'discrete derived choices; supplementary symbol'},
        {'id':'q','unit':'1','choices':sorted({1+b/a for a,b in pairs}),'expression':'1+C2/C1','scope':'discrete derived choices; supplementary symbol'},
        {'id':'fz','unit':'Hz','range':[1/(2*math.pi*rhi*c2hi),1/(2*math.pi*rlo*c2lo)],'expression':'1/(2π·Rz·C2)','scope':'declared marginal extrema; coupled to fp'},
        {'id':'fp','unit':'Hz','range':[(1/c1hi+1/c2hi)/(2*math.pi*rhi),(1/c1lo+1/c2lo)/(2*math.pi*rlo)],'expression':'(1/C1+1/C2)/(2π·Rz)','scope':'declared marginal extrema; coupled to fz'},
        {'id':'Vctrl_required','unit':'V','range':[(target-fhi)/khi,(target-flo)/klo],
         'validity_intersection':[0,1.2],'validity_endpoints':'strictly interior',
         'expression':'(F−f0)/Kvco','scope':'declared [0.1,2] V; model-valid projection [0.1,1.2) V'},
    ]


DERIVATION = r"""
## 怎样读这张表

六个独立分配变量是 **Icp、Rz、C1、C2、f0、Kvco**。f_ref、N、Vctrl_min/max 是固定输入，另七项是零非理想假设；BW、PM、UGF、Kpfd、fz/fp 等是计算或测量结果。表中的范围来自人工声明行为实验，不代表已表征电路能力。所有机器文件保留 SI 单位；展示表按 µA/kΩ/pF/nF/MHz 换算。

范围分四层：**声明域**是原轴的笛卡尔积；**模型有效域**还需零非理想、正值与严格内部调谐；**M1 规格可行域**再交 BW/PM 目标；**完整 TB 验证域**必须逐候选独立判决。历史有限局部点不构成连续验证区域，尚未签发满足全部正式 SystemSpec 的 Verified JointBlockSpec。

## 条件域推导与使用

取 P=Icp·Kvco，CΣ=C1+C2，q=1+C2/C1，x=ωu·Rz·C2。先从九个合法电容对枚举，不能在电容最小/最大之间连续插值。

1. **调谐**：f0 ∈ [60,76] MHz ∩ (F−Kvco·1.2V, F)，F=80 MHz。给定 f0 时，Kvco ∈ [10,40] MHz/V ∩ ((F−f0)/1.2V, ∞)。例如 Kvco=10 MHz/V 必须 f0>68 MHz；f0=68 MHz 与 Kvco=10 MHz/V 恰在 rail，不能进入 M1。Kvco=20 MHz/V 时，全部声明 f0 均可调谐。这里的 1.2 V 是控制轨，不作为供电规格。

2. **PM 形状**：PM(x)=atan(x)−atan(x/q)。令 φ=50°、t=tanφ，D=(q−1)²−4qt²。D<0 则这个电容对没有满足 PM 的点；否则 x ∈ [x−,x+]，x−=2qt/(q−1+√D)、x+=q/x−。这是以形状变量 x 表达的准确 PM 条件，单独看电容比只是必要筛选。PMmax 在 x=√q 取得；此峰值与其它约束是否相交还需核验。

3. **BW 与形状**：h=√[(1+(x/q)²)/(1+x²)]，y=(BW/UGF)²。β=√y，由唯一正根确定：

   (x/q)²·y³ + (1−2h·x²/q)·y² − (2h+h²·x²)·y − h² = 0。

   本工具复用已有 bandwidth_ratio 数值根，保留“数值”属性；没有把它写成经验常数或闭式公式。给定 B=BW 时，ωu=2πB/β。

4. **R 与增益交集**：令 aR=xβ/(2πC2)，aP=N·CΣ·(2π/β)²·h，则 Rz=aR/B，P=aP·B²。给定 C1,C2,x 时允许的 B 恰为：

   [150,300] kHz ∩ [aR/8000Ω,aR/2000Ω] ∩ [√(Pmin/aP),√(Pmax/aP)]，Pmin=500、Pmax=8000 A·Hz/V。

   交集为空就排除此形状。非空才可选 B、重建 Rz/P、再分摊 CP/VCO。这个条件表述覆盖连续 x，不等同于一次有限网格证明。本次在各电容对的 PM 峰值给出一条可读切片；切片边界不能称该电容对的全局 BW 边界。

5. **产品分摊与调谐**：Kvco ∈ [10,40] MHz/V ∩ [P/200µA,P/50µA]，Icp=P/Kvco；选 f0 前再套第1条。当前域任一合法 Kvco 的 f0 调谐交集都非空，因为最不利 Kvco=10 MHz/V 时 80−10×1.2=68<76 MHz。因此用 Pmin/Pmax 传播存在性是成立的；未来改变频率计划、控制轨或 f0 域，必须重新证明这一简化。若 f0 已固定，Kvco 的严格下界也要交进去。

这给出了当前理想 M1 的条件参数化：合法电容对 → 合法 x → 联合 B 区间 → P 与 R → Kvco/f0 交集 → 完整17量候选 → 原约束检查与正式 M1。所有等价关系限定于当前正值、无延时、无非理想的连续模型，不证明捕获、周期稳定性或实现能力。

## 证据边界和待补映射

- Stage4.1 十个完整参数点支持局部调谐/频响/阶跃映射，最大观测 BW 误差约0.624%；该值是有限样本观测，不作为全域误差界或新增 guard。C01/C08 同产品拆分提供局部等价例子。相关报告保留正式 PM/严格频率 UNKNOWN。
- Stage5 研究场景明确覆盖 BW/PM 阈值变体，不能把某个场景的结果或范围写回原 SystemSpec；本表默认列原 Stage1.5 快照。
- PFD/Divider 目前没有独立可分配性能轴。CP mismatch/leakage、VCO 曲率、LF 动态负载当前固定零；加宽这些范围需要新模型及验证。
- 静态相位偏置只可使用旧符号电荷平衡作条件初筛，当前不支持非零参数分配。锁定时间/捕获必须依照初值、窗口和事件协议测量；不使用 1/BW 或二阶 PM 经验式代替。
- Jitter/phase noise 缺少 PSD、积分频带、源传递与协议；Power 缺供电及各块损耗模型；RUR 未正式定义。这些项目列为缺口，不填写任意经验范围。

## 使用与后续

HTML 为独立离线表格，可直接打开/打印；Markdown 可评审与版本管理；JSON/CSV 保留41项变量、18条展示关系、原 Equation ID、域层级、来源与真实计数。JSON 是只读研究图谱，不自动接入 Agent，不授予 PASS 权限。

查看表中条件域后，仍用正式 pipeline 对完整候选运行原 TB。要覆盖新增非理想、噪声/功耗或扩大轴范围，另建版本并先定义测量合同；这张表本身不改变任何输入、策略或判决。
"""


def csv_new(path, rows):
    with Path(path).open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(headers, rows):
    esc = lambda s: str(s).replace('|', '\\|').replace('\n', '<br>')
    return '\n'.join(['|'+'|'.join(headers)+'|', '|'+'|'.join(['---']*len(headers))+'|'] +
                     ['|'+'|'.join(esc(x) for x in row)+'|' for row in rows])


def pretty_formula(value):
    replacements={
        'Icp':'I<sub>CP</sub>', 'Iup':'I<sub>UP</sub>', 'Idown':'I<sub>DN</sub>',
        'Kpfd':'K<sub>PFD/CP</sub>', 'Rz':'R<sub>z</sub>', 'C1':'C<sub>1</sub>', 'C2':'C<sub>2</sub>',
        'Kvco':'K<sub>VCO</sub>', 'Kvco2':'K<sub>VCO2</sub>', 'Kvco_angular':'K<sub>VCO,angular</sub>',
        'Kvco_local':'K<sub>VCO,local</sub>', 'f_ref':'f<sub>ref</sub>', 'f0':'f<sub>0</sub>',
        'f_out':'f<sub>out</sub>', 'f_div':'f<sub>div</sub>', 'Vreq':'V<sub>req</sub>',
        'Vctrl0':'V<sub>ctrl,0</sub>', 'V0':'V<sub>0</sub>', 'fz':'f<sub>z</sub>', 'fp':'f<sub>p</sub>',
        'ωu':'ω<sub>u</sub>', 'φe':'φ<sub>e</sub>', 'φref':'φ<sub>ref</sub>', 'φdiv':'φ<sub>div</sub>',
        'PMmax':'PM<sub>max</sub>', 'Href':'H<sub>ref</sub>', 'H_div':'H<sub>div</sub>',
        'D_M1':'D<sub>M1</sub>', 'D_declared':'D<sub>declared</sub>', 'D_ideal':'D<sub>ideal</sub>',
        'D_tuning':'D<sub>tuning</sub>', 'D_verified':'D<sub>verified</sub>',
        'Cload':'C<sub>load</sub>','Gload':'G<sub>load</sub>','q0':'q<sub>0</sub>',
        'aR':'a<sub>R</sub>', 'aP':'a<sub>P</sub>', 'Pmin':'P<sub>min</sub>', 'Pmax':'P<sub>max</sub>',
    }
    pattern='|'.join(re.escape(k) for k in sorted(replacements,key=len,reverse=True))
    escaped=html.escape(str(value))
    return re.sub(r'(?<![A-Za-z0-9_])('+pattern+r')(?![A-Za-z0-9_])',
                  lambda match: replacements[match.group()],escaped).replace('\n','<br>')


def table_html(headers, rows, css=''):
    esc = lambda v: html.escape(str(v)).replace('\n','<br>')
    return ('<div class="scroll"><table class="'+css+'"><thead><tr>' +
            ''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+
            ''.join('<tr>'+''.join('<td>'+(pretty_formula(c) if css=='main' and i==2 else esc(c))+'</td>' for i,c in enumerate(row))+'</tr>' for row in rows)+
            '</tbody></table></div>')


def render(out, atlas, cap_rows):
    rows = atlas['relations']
    heads = ['层级 / Block','Variables（原 ID）','Relations','范围 / 条件可行域','证据 / 适用边界']
    table_rows = [[r['block'],', '.join(r['variable_ids']) or '—',
                   r['formula'] + ('\n逆向：'+r['inverse'] if r['inverse'] else ''),r['domain'],r['evidence']] for r in rows]
    cap_heads = ['C1 / pF','C2 / nF','PM 上界 / °','PM≥50° 的 x 区间','x=√q 时联合 BW / kHz']
    cap_table = []
    for r in cap_rows:
        interval = r['x_interval']
        domain = r['peak_shape_domain']
        cap_table.append([f"{r['C1_F']*1e12:g}", f"{r['C2_F']*1e9:g}", f"{r['PM_ceiling_deg']:.6f}",
                          '空集' if interval is None else f'[{interval[0]:.6f}, {interval[1]:.6f}]',
                          '空集' if domain['status']=='EMPTY' else f"[{domain['BW_min_Hz']/1e3:.3f}, {domain['BW_max_Hz']/1e3:.3f}]"])
    axis_heads = ['变量','Block','单位','原声明范围 / 固定值','参与类型']
    axis_rows=[]
    for vid,a in atlas['axes'].items():
        content = a.get('range',a.get('choices',a.get('fixed')))
        axis_rows.append([vid,a['block'],a['unit'],json.dumps(content,ensure_ascii=False),a['kind']])
    catalog_heads=['变量','块 / 类型','单位','语义','关系 ID']
    catalog_rows=[[v['id'],v['block']+' / '+v['kind'],v['unit'],v['semantic_definition'],', '.join(v['relation_ids'])] for v in atlas['variables']]
    range_heads=['派生量','单位','边际范围 / 离散集合','关系与适用层级']
    range_rows=[[v['id'],v['unit'],json.dumps(v.get('range',v.get('choices')),ensure_ascii=False),
                 v['expression']+'；'+v['scope']] for v in atlas['derived_marginal_ranges']]
    md = '# PLL Block Variables and Relations\n\n2026-11-06 · 当前冻结快照的只读研究图谱\n\n'
    md += markdown_table(heads,table_rows)+'\n\n## 九个电容对的形状与联合区间\n\n'
    md += '最后一列只是在 x=√q 这条峰值形状切片上的条件交集，不是每个电容对的全部可行域。三组空集不从原声明域删除。\n\n'
    md += markdown_table(cap_heads,cap_table)+'\n'+DERIVATION
    md += '\n## 派生量的边际范围\n\n这些是原声明域的投影极值或离散集合；不同量的端点不能任意拼成联合可行点。P/K/C_sum/q 是辅助派生符号，不是新增自由输入。\n\n'+markdown_table(range_heads,range_rows)
    md += '\n## 17项输入（SI 原值）\n\n'+markdown_table(axis_heads,axis_rows)
    md += '\n\n## 全部41项变量的映射索引\n\n'+markdown_table(catalog_heads,catalog_rows)+'\n'
    md += '\n实际数值调用和结果见 `validation.json`；来源路径/SHA/语义见 `source_manifest.json`。此轮未执行 M2/LLM。\n'
    (out/'VARIABLES_AND_RELATIONS.md').write_text(md,encoding='utf-8')
    # Offline document: no remote fonts, scripts or math rendering dependency.
    body = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PLL · Variables and Relations</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f2f4f6;color:#172331;font:15px/1.65 "Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1580px;margin:32px auto;padding:34px 40px 50px;background:white;border:1px solid #dbe1e7}header{text-align:center;border-bottom:2px solid #172331;padding-bottom:22px;margin-bottom:24px}.eyebrow{letter-spacing:2px;color:#536776;font-size:12px}h1{font:600 30px/1.3 Georgia,"Microsoft YaHei",serif;margin:8px}h2{font-size:20px;margin:32px 0 12px}p{margin:10px 0}.intro{max-width:1160px;margin:12px auto 0;color:#4c5a68}.pills{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:15px}.pills span{border:1px solid #cad6df;padding:3px 12px;border-radius:3px;font-size:12px}.notice{background:#f1f6fa;border-left:3px solid #3a617b;padding:14px 18px;margin:18px 0}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;margin:12px 0 20px;table-layout:fixed}th{background:#eef2f5;color:#203d52;font-weight:650}td,th{border:1px solid #bcc8d1;padding:12px 13px;text-align:left;vertical-align:middle;overflow-wrap:anywhere}th:first-child{width:11%}.main th:nth-child(2){width:15%}.main th:nth-child(3){width:33%}.main th:nth-child(4){width:28%}.main th:nth-child(5){width:13%}.main td:first-child{font-weight:650}.main td:nth-child(2){font-size:13px;color:#33556d}.main td:nth-child(3){font-family:"Cambria Math",Cambria,"Microsoft YaHei",serif;font-size:16px;line-height:1.75}.main td:nth-child(4){font-size:13px}.main td:nth-child(5){font-size:12px;color:#526775}tr:nth-child(even){background:#fafcfd}.detail{font-size:13px}.detail th:first-child{width:15%}.cap th:first-child{width:14%}.cap th:nth-child(2){width:14%}.cap th:nth-child(3){width:18%}.cap th:nth-child(4){width:27%}.cap th:nth-child(5){width:27%}details{margin-top:22px}summary{cursor:pointer;font-size:18px;font-weight:650;color:#294b65}.prose{max-width:1160px}.prose pre{white-space:pre-wrap;font:14px/1.8 "Segoe UI","Microsoft YaHei",sans-serif;margin:18px 0}.small{font-size:12px;color:#607281}.section-nav{text-align:center;margin:16px 0}.section-nav a{margin:0 12px;color:#315b77;text-decoration:none}footer{border-top:1px solid #c7d0d8;padding-top:16px;margin-top:30px;color:#586978;font-size:12px}@media(max-width:850px){main{margin:0;padding:20px 16px}.main{min-width:1150px}.cap{min-width:780px}h1{font-size:24px}}@media print{@page{size:A3 landscape;margin:12mm}body{background:white}main{margin:0;padding:0;border:0;max-width:none}table{font-size:10px}td,th{padding:6px 7px}.main td:nth-child(3){font-size:12px}thead{display:table-header-group}tr{break-inside:avoid}.section-nav{display:none}details{break-before:page}.prose pre{font-size:11px}}
</style><main><header><div class="eyebrow">TABLE I · INTEGER-N CPPLL · 2026-11-06</div><h1>Block Variables and Relations</h1><div class="intro">变量、物理映射与条件可行域 · 与当前主线原模型同源</div><div class="pills"><span>6 个自由分配变量</span><span>41 项完整语义</span><span>9 个离散电容组合</span><span>M1 条件域</span></div></header>
<div class="notice"><b>域的层级：</b>声明范围 → 模型有效域 → M1 规格可行域 → 完整 TB 验证。<br>人工声明范围不代表器件能力；局部 M2 证据只支持测过的完整参数点。正式 PM / 严格频率认证保持 UNKNOWN。</div><nav class="section-nav"><a href="#mapping">关系总表</a><a href="#capacitors">电容与联合区间</a><a href="#derivation">条件域推导</a><a href="#catalog">完整变量索引</a></nav><section id="mapping">'''
    body += table_html(heads,table_rows,'main')+'</section><section id="capacitors"><h2>九个电容对：PM 形状与 BW 联合切片</h2>'
    body += '<p class="small">最后一列固定 x=√q，已经交入原 BW、Rz 与增益乘积范围。它是条件切片，不能作为该电容对的全局极值。空集组仍保留在原声明域作负对照。</p>'
    body += table_html(cap_heads,cap_table,'cap')+'</section><section id="derivation" class="prose"><h2>条件域推导与证据边界</h2><pre>'
    body += html.escape(DERIVATION.replace('**','').replace('## ','')).strip()+'</pre></section>'
    body += '<details><summary>派生量边际范围 · 极值不能任意重组</summary>'+table_html(range_heads,range_rows,'detail')+'</details>'
    body += '<details><summary>17项输入 · SI 原值与参与类型</summary>'+table_html(axis_heads,axis_rows,'detail')+'</details>'
    body += '<details id="catalog"><summary>完整41项变量 · 关系与语义索引</summary>'+table_html(catalog_heads,catalog_rows,'detail')+'</details>'
    body += '<footer>只读研究图谱 · 冻结模型/原公式/策略/验收协议保持原状。JSON、CSV、数值核验与原路径/SHA 位于同目录。本轮 M2=0，LLM=0；M1 数值核验不签发 Verified JointBlockSpec。</footer></main></html>'
    (out/'VARIABLES_AND_RELATIONS.html').write_text(body,encoding='utf-8')


SOURCE_PURPOSES = {
    'configs/BLOCK_SPACE_MODEL_V1.json': '原17输入范围、41变量语义、固定拓扑和版本',
    'configs/PLL_EQUATION_REGISTRY_V1.json': '11条原公式ID和历史MATLAB来源路径/SHA；不覆盖原文件',
    'configs/SYSTEM_SPEC_STAGE1_5.json': '原三指标目标及draft元数据',
    'configs/pipeline_stage3a.json': '正式输入哈希绑定',
    'configs/verification/protocol_v1_1.json': '独立行为测量定义与正式UNKNOWN边界',
    'pll_allocation/physics_mapping/model.py': '正式连续M1函数与SI语义；调用复用',
    'pll_allocation/physics_mapping/validation.py': '既有独立数值验证语义参考',
    'pll_allocation/block_space/contracts.py': '原域检查、候选完整性；调用复用',
    'pll_allocation/allocation/physics.py': '原PM区间、上界、BW数值根；调用复用',
    'pll_allocation/allocation/core.py': 'M1计量、独立判决与区间读取；调用复用',
    'pll_allocation/pipeline_contracts.py': '正式版本绑定只读加载；不调用M2',
    'docs/track_a/A1_INVERSE_RELATIONS.md': '既有条件逆解、缩放关系与数值根推导',
    'docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json': '只读映射分类、版本与证据层级参考',
    'docs/stage4_2/EQUATION_AND_DOMAIN_AUDIT.md': '变量语义/公式域/非理想边界审查',
    'docs/stage4_2/SYSTEM_SPEC_MAPPING_MATRIX.md': '系统指标映射与支持状态',
    'docs/stage4_1/M1_M2_MAPPING_VALIDATION_REPORT.md': '历史10个局部点支持，不构成连续验证域',
    'docs/stage4_1/ENGINEERING_MAPPING_CONFIDENCE.json': '局部证据逐点可追溯索引',
    'docs/stage5/END_TO_END_FEASIBILITY_REPORT.md': '最新端到端证据/正式认证缺口',
    'pll_allocation/scenarios.py': 'Stage5研究场景覆盖与原规格边界',
    'tools/build_block_relation_atlas.py': '本轮生成器与新条件交集推导',
}


def build(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    config, model, spec, protocol = load_inputs()
    rows = relation_rows()
    equations = read('configs/PLL_EQUATION_REGISTRY_V1.json')
    eqids = {r['equation_id'] for r in equations['equations']}
    if {e for r in rows for e in r['equation_ids']} - eqids:
        raise ValueError('unregistered formula ID')
    catalog = variable_catalog(model, rows)
    manifest = [{'path': p, 'absolute_path': str(ROOT/p),
                 'sha256': hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),
                 'purpose_and_semantics': purpose,
                 'domain': 'current ideal integer-N CPPLL behavioral research; no circuit capability claim'}
                for p,purpose in SOURCE_PURPOSES.items()]
    write(out/'source_manifest.json', {'sources': manifest,
        'upstream_source_status': 'historical paths/hashes preserved from registered provenance; not re-read in this generation',
        'upstream_equation_sources': [{'equation_id': r['equation_id'], 'source_files': r['source_files']}
                                      for r in equations['equations']],
        'external_references': 'Web search blocked HTTP403; no unread external source cited'})
    atlas = {'schema_version': 'pll-block-relation-atlas-1.0', 'status': 'READ_ONLY_RESEARCH',
             'model_sha256': fingerprint(model), 'system_spec_sha256': fingerprint(spec),
             'versions': model['versions'], 'system_spec': spec, 'axes': model['variables'],
             'relations': rows, 'variables': catalog, 'derived_marginal_ranges':derived_ranges(model),
             'formal_metrics': ['output_frequency_Hz','BW_Hz','PM_deg'],
             'layers': ['DECLARED','MODEL_VALIDITY','M1_SPEC_FEASIBLE','FULL_TB_VERIFIED'],
             'may_issue_behavioral_PASS': False, 'automatic_agent_integration': False,
             'exact_conditional_domain': 'legal C1,C2; x in PM interval; B in three-way interval; P=a_P B^2; R=a_R/B; Kvco/f0 split with strict tuning',
             'full_TB_certified_continuous_domain': 'NOT_ESTABLISHED',
             'unavailable': ['periodic_PM_certification','1uHz_frequency_certification','RUR_definition','jitter','phase_noise','power']}
    write(out/'relation_atlas.json', atlas)
    meter = Meter(cheap_limit=2000, m1_limit=100)
    caps, examples = [], []
    kcl_error, reconstruction_error = 0., 0.
    beta_calls = 0
    for c1,c2 in itertools.product(model['variables']['C1']['choices'],model['variables']['C2']['choices']):
        q=1+c2/c1
        phase=phase_interval(c1,c2,50)
        peak=bandwidth_domain(model,spec,c1,c2,math.sqrt(q))
        beta_calls += int(phase is not None)
        cap={'C1_F':c1,'C2_F':c2,'q':q,'PM_ceiling_deg':pm_ceiling(c1,c2),
             'x_interval':phase,'peak_shape_domain':peak}
        caps.append(cap)
        if phase is None:
            continue
        for fraction in (0.15,0.5,0.85):
            x=math.exp(math.log(phase[0])+fraction*math.log(phase[1]/phase[0]))
            domain=bandwidth_domain(model,spec,c1,c2,x)
            beta_calls += 1
            entry={'C1_F':c1,'C2_F':c2,'log_x_fraction':fraction,'domain':domain}
            if domain['status']=='NONEMPTY':
                candidate,bw=witness(model,domain,c1,c2)
                meter.charge('candidate_generations', source='conditional_domain_reconstruction')
                assessment=assess_m1(model,spec,candidate,meter)
                metrics=assessment['prediction']['metrics']
                reconstruction_error=max(reconstruction_error,abs(metrics['BW_Hz']/bw-1))
                p=values(candidate)
                residuals=[]
                for f in (metrics['BW_Hz'],metrics['UGF_Hz']):
                    z,l,t=kcl_response(p,f)
                    residuals.append({'f_Hz':f,'abs_L':abs(l),'abs_T':abs(t)})
                kcl_error=max(kcl_error,abs(residuals[0]['abs_T']*math.sqrt(2)-1),abs(residuals[1]['abs_L']-1))
                entry.update(candidate=candidate,requested_BW_Hz=bw,assessment=assessment,kcl_residuals=residuals)
            examples.append(entry)
    write(out/'conditional_domains.json',{'scope':'exact conditional expressions; finite examples are not global extrema',
          'capacitor_pairs':caps, 'examples':examples,
          'tuning_examples':[{'Kvco_Hz_per_V':k,'f0_interval':tuning_interval(model,k)} for k in (10e6,20e6,40e6)],
          'product_split_example':{'P_A_Hz_per_V':2000,'Kvco_interval':product_split(model,2000)}})
    judgments=[x['assessment']['judgment']['verdict'] for x in examples if 'assessment' in x]
    validation={'catalog_coverage':len(catalog),'input_count':len(model['variables']),
                'free_input_count':sum(a['kind']=='free_allocation_parameter' for a in model['variables'].values()),
                'relation_count':len(rows),'capacitor_pairs':len(caps),
                'PM_shape_excluded_pairs':sum(c['x_interval'] is None for c in caps),
                'predeclared_example_rule':'each PM-admissible pair: log-x fractions 0.15, 0.5, 0.85; midpoint of conditional B and gain/tuning intervals; empty intersections preserved',
                'conditional_examples':len(examples),'empty_examples':sum(e['domain']['status']=='EMPTY' for e in examples),
                'M1_spec_pass':judgments.count('M1_SPEC_PASS'),'M1_spec_fail':judgments.count('M1_SPEC_FAIL'),
                'max_M1_BW_reconstruction_relative_error':reconstruction_error,
                'max_independent_KCL_crossing_residual':kcl_error,
                'costs':{**meter.counts,'conditional_beta_root_calls':beta_calls},
                'new_M2_calls':0,'new_LLM_calls':0,'verified_joint_block_spec':False,
                'status':'NUMERICAL_CHECK_PASS' if len(catalog)==41 and judgments and all(x=='M1_SPEC_PASS' for x in judgments)
                          and reconstruction_error<1e-8 and kcl_error<1e-8 else 'CHECK_FAILED'}
    write(out/'validation.json',validation)
    write(out/'M1_meter.json',{'counts':meter.counts,'events':meter.events})
    csv_new(out/'variables.csv',[{k:('; '.join(v) if isinstance(v,list) else v) for k,v in a.items()
                                  if k not in ('declared_axis',)} for a in catalog])
    csv_new(out/'capacitor_domains.csv',[{'C1_pF':c['C1_F']*1e12,'C2_nF':c['C2_F']*1e9,
              'PM_ceiling_deg':c['PM_ceiling_deg'],'x_min':c['x_interval'][0] if c['x_interval'] else None,
              'x_max':c['x_interval'][1] if c['x_interval'] else None,
              'peak_shape_BW_min_Hz':c['peak_shape_domain'].get('BW_min_Hz'),
              'peak_shape_BW_max_Hz':c['peak_shape_domain'].get('BW_max_Hz'),
              'scope':'fixed_x_sqrt_q_slice_not_global_extrema'} for c in caps])
    render(out,atlas,caps)
    print(json.dumps({'out':str(out),'validation':validation},ensure_ascii=False))
    if validation['status']!='NUMERICAL_CHECK_PASS':
        raise SystemExit(1)
    return validation


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    build(parser.parse_args().out)
