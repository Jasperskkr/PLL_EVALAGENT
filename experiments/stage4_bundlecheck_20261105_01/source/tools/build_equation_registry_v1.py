"""Create the traceable machine-readable Equation Registry for Stage 1.5."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    manifest=json.loads((ROOT/'docs/stage1_5/audit/source_manifest.json').read_text(encoding='utf-8'))
    by_name={Path(r['path']).name:r for r in manifest['sources']}
    common=['Integer-N CPPLL','symmetric ideal CP; no leakage/q0/reset delay','linear positive-frequency increasing VCO',
            'C1 shunt || series Rz-C2; no extra load','interior feasible tuning; locked small signal',
            'continuous-time linearization; no sampling equivalence claim']
    equations=[
        ('E_FREQ_PLAN','Frequency planning','f_target=N*f_ref',['N','f_ref'],['f_target'],'Hz; N dimensionless',
         'F_FREQ_PLAN; model/solve_tuning_point.m','PLL frequency target follows ideal integer divider relation.',
         'Multiply fixed N and reference frequency; no acquisition assumption needed for the algebra.',
         ['N positive integer; f_ref>0'],'No claim the transient actually reaches target.'),
        ('E_TUNING','VCO lock point and local gain','f(V)=f0+Kvco*V; Vreq=(f_target-f0)/Kvco; Kvco_local=Kvco',
         ['f_target','f0','Kvco','Vctrl_min','Vctrl_max'],['Vctrl_required','Kvco_local'],
         'Hz; V; Hz/V; angular gain = 2*pi*Kvco_local rad/s/V','F_TUNING; model/vco_model.m; model/solve_tuning_point.m',
         'Static control voltage necessary to produce the frequency plan.',
         'Solve linear VCO frequency law with f0 at zero volts, not the v1 V0 anchor.',
         ['Vmin<Vreq<Vmax for M1','positive f(V) throughout declared voltage domain'],
         'No curvature; no voltage-dependent gain; rail point lacks two-sided small-signal neighborhood.'),
        ('E_KPFD','PFD/CP small signal slope','Kpfd=Icp/(2*pi)', ['Icp'],['Kpfd'],
         'A/rad; phase_error=reference-minus-feedback radians','F_KPFD; model/pll_linear_kernel.m',
         'Average injected current derivative with respect to phase error about ideal lock.',
         'A phase error delta_phi gives pulse width delta_phi/(2*pi*f_ref), so mean current is Icp*delta_phi/(2*pi).',
         ['Iup=Idown=Icp>0','zero mismatch/leakage/reset/q0'],
         'No nonideal CP bias equilibrium, switching spikes or one-sided mismatch linearization.'),
        ('E_LF','Loop filter impedance','Z=(1+s*Rz*C2)/(s*(C1+C2)+s^2*Rz*C1*C2)',
         ['Rz','C1','C2','f_offset'],['Zlf'],'Ohm; s=j*2*pi*f_offset rad/s','F_LF_TF; model/loop_filter_model.m; model/pll_linear_kernel.m',
         'Control-node voltage divided by injected CP current.',
         'Eliminate vc2 from C1*s*vctrl=i-(vctrl-vc2)/R and C2*s*vc2=(vctrl-vc2)/R.',
         ['positive ideal Rz/C1/C2','Cload=Gload=0','finite f_offset>0'],
         'No dynamic VCO input load, CP output resistance, dielectric loss or parasitics.'),
        ('E_LF_ZP','Loop filter zero and poles','wz=1/(Rz*C2); wp=(C1+C2)/(Rz*C1*C2); poles={0,-wp}',
         ['Rz','C1','C2'],['fz','fp'],'fz=wz/(2*pi) Hz; fp=wp/(2*pi) Hz; s poles rad/s',
         'F_LF_TF; characterization/characterize_loop.m',
         'Lead zero, integrator and extra high-frequency pole of the passive LF.',
         'Factor impedance numerator and denominator; wp/wz=1+C2/C1>1.',
         ['positive ideal RC'],'Frequency labels are positive magnitudes, not signed s-plane pole values.'),
        ('E_OPEN','Open loop transfer','L=Kpfd*(2*pi*Kvco_local)*Zlf/(N*s)',
         ['Kpfd','Kvco_local','Zlf','N','f_offset'],['L'],'dimensionless; explicit Hz/V to rad/s/V conversion',
         'F_LOOP; model/pll_linear_kernel.m','Phase-domain forward path with ideal divider feedback.',
         'Multiply current/phase slope, current-to-voltage LF, integrating VCO angular gain and 1/N.',common,
         'Continuous model does not include event sampling, acquisition or nonlinear saturation.'),
        ('E_CLOSED','Normalized closed loop','T=L/(1+L); H_ref=N*T; T(0)=1',
         ['L'],['T'],'dimensionless; normalized output/divider phase response',
         'F_LOOP; model/pll_linear_kernel.m','Closed-loop normalized reference phase response.',
         'Use negative-feedback denominator 1+L; output phase response is N times normalized T.',common,
         'Do not threshold absolute H_ref at 1/sqrt(2); do not infer time-domain lock.'),
        ('E_UGF','Unity gain frequency','|L(j*2*pi*UGF)|=1; first downward crossing',
         ['L','f_offset'],['UGF'],'Hz; scan in log10(f); no angular frequency output',
         'F_LOOP; characterization/characterize_loop.m','Diagnostic unity-gain frequency.',
         '8000-point log scan brackets one downward crossing; log-frequency bisection refines the root.',common+['finite unique bracketed crossing'],
         'No bracket or multiple downward brackets => NUMERICAL_FAILURE; generic multiple-crossing handling is not a phase-margin theorem.'),
        ('E_BW','Closed loop bandwidth','|T(j*2*pi*BW)|=1/sqrt(2)',
         ['T','f_offset'],['BW'],'Hz; normalized -3.0103 dB amplitude criterion',
         'F_LOOP; characterization/characterize_loop.m','First high-frequency downward half-power amplitude crossing of normalized T.',
         'Same log-frequency bracketing and bisection, with a separate T residual from unity-loop crossing.',common+['stable loop; unique finite bracket'],
         'Not UGF, not sampled-loop bandwidth, not measured by available event TB.'),
        ('E_PM','Phase margin','PM=180+arg(L(j*2*pi*UGF))*180/pi',
         ['L','UGF'],['PM'],'degrees; arg radians converted exactly once',
         'F_LOOP; characterization/characterize_loop.m','Phase distance to -180 degrees at unity-loop crossing.',
         'Evaluate complex L again at refined UGF; ideal network phase is -180+atan(w/wz)-atan(w/wp).',common+['valid UGF; unique crossing'],
         'No nonideal delay margin; low PM does not make this strictly stable continuous ideal loop mathematically unstable.'),
        ('E_STABILITY','Continuous stability and domain','D(s)=a*s^3+b*s^2+c*s+d; bc-ad=(Icp*Kvco/N)*Rz*C2^2>0',
         ['Icp','Kvco','N','Rz','C1','C2'],['Routh_bc_minus_ad'],
         'a=R*C1*C2; b=C1+C2; c=(Icp*Kvco/N)*R*C2; d=Icp*Kvco/N',
         'F_LOOP; model/pll_linear_kernel.m; Stage 1 characteristic coefficients',
         'Routh-Hurwitz stability of the third-order continuous linearization.',
         'All a,b,c,d positive and bc>ad; difference simplifies to positive gain*R*C2^2.',
         ['positive parameters; ideal subset'],'Does not prove event/sampled stability or global capture. Negative R/gain are outside the declared model.'),
    ]
    entries=[]
    for eid,title,expression,inputs,outputs,units,origin,what,how,domain,limitations in equations:
        files=[x for x in ('solve_tuning_point.m','vco_model.m','pll_linear_kernel.m','loop_filter_model.m','characterize_loop.m') if x in origin]
        entries.append({'equation_id':eid,'title':title,'expression':expression,'inputs':inputs,'outputs':outputs,
            'units_and_conversions':units,'model_level':'M1','formula_version':'stage1_m1_1.0.0',
            'source':origin,'source_files':[by_name[x] for x in files],
            'what':what,'how':how,'domain':domain,'limitations':limitations,
            'implementation':{'path':'pll_allocation/physics_mapping/model.py','symbol':'M1Evaluator.evaluate' if eid not in {'E_LF','E_OPEN','E_CLOSED'} else '_response'},
            'validation_evidence':{'numerical':'outputs/block_space_v1_20261104_01/FORWARD_MODEL_VALIDATION.csv',
                'independent_path':'pll_allocation/physics_mapping/validation.py::polynomial_reference; independent KCL unit test',
                'behavioral':'sparse event TB frequency/control only; BW/PM/UGF not behaviorally validated',
                'prior_tests':'docs/physics_mapping_stage1/tests_final_20261104.xml'},
            'validation_scope':'numerical_equation_consistency_not_full_behavioral_accuracy'})
    path=ROOT/'configs/PLL_EQUATION_REGISTRY_V1.json'
    with path.open('x',encoding='utf-8') as stream:
        json.dump({'schema_version':'pll-equation-registry-1.0','equations':entries},stream,indent=2,ensure_ascii=False)
        stream.write('\n')
    print(f'Wrote {len(entries)} traceable equation entries')


if __name__=='__main__':
    main()
