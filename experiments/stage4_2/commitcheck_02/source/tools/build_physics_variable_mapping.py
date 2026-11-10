"""Emit the audited Stage 1 mapping table; refuse replacing an existing table."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.physics_mapping.experiment import load_experiment

# MATLAB ID -> (MATLAB definition, v1 definition, source, conflict).
INPUTS = {
    'f_ref': ('p.f_ref', 'operating_context.fref_Hz', 'model/pll_params.m', 'registry calls it block_design; this experiment fixes it as Context'),
    'N': ('p.n_div', 'operating_context.N and Divider.N must agree', 'model/pll_params.m', 'none; v1 hard domain N=8 remains untouched'),
    'Icp': ('p.i_cp; symmetric nominal UP/DOWN A', 'no single Icp; CP.I_up_A and I_down_A', 'model/pfd_cp_event_step.m', 'directional timing slopes require explicit equal-current assumption'),
    'Rz': ('p.rz; between vctrl and vc2', 'LF.Rz_Ohm; same connection', 'model/loop_filter_model.m', 'none in ideal topology'),
    'C1': ('p.c1; vctrl to ground', 'LF.C1_F with Cload_F added at input', 'model/loop_filter_model.m', 'v1 effective shunt includes Cload; v2 rejects nonzero load'),
    'C2': ('p.c2; vc2 to ground below Rz', 'LF.C2_F; same connection', 'model/loop_filter_model.m', 'none; must not swap with C1'),
    'f0': ('p.f0; f(V=0)', 'VCO.f0_Hz; f(V=V0_V)', 'model/vco_model.m', 'YES: f0_v2=f0_v1-Kvco*V0 for linear VCO'),
    'Kvco': ('p.kvco; coefficient in Hz/V', 'VCO.Kvco_Hz_per_V', 'model/vco_model.m', 'both Hz/V; angular gain requires explicit 2*pi'),
    'Vctrl_min': ('p.vctrl_min; assumed functional limit', 'VCO.voltage_min_V; v1 additionally >0', 'model/validate_pll_params.m', 'v2 ideal default 0 V cannot pass v1; separate contract'),
    'Vctrl_max': ('p.vctrl_max; assumed functional limit', 'VCO.voltage_max_V; v1 < VDD', 'model/validate_pll_params.m', 'v2 has no fabricated VDD/PDK condition'),
    'Kvco2': ('p.kvco2; f(V) curvature Hz/V^2', 'not implemented in v1', 'model/vco_model.m', 'nonzero UNSUPPORTED; no silent linearization'),
    'CP_mismatch': ('p.cp_mismatch_frac=(Iup-Idown)/Icp', 'I_up/I_down explicit; v1 constraint requires equality', 'model/pfd_cp_event_step.m', 'mismatch has one-sided slopes; nonzero UNSUPPORTED'),
    'CP_leakage': ('p.cp_leakage_A; signed positive injection into LF', 'not independent; q0 includes proxy demand', 'model/pfd_cp_event_step.m', 'YES: signed current is not net proxy balance charge'),
    'q0': ('absent as independent variable', 'CP.q0_C; net balance charge includes local proxy demand', 'pll_allocation/_legacy/physics/cp.py', 'YES: cannot subtract leakage again; nonzero UNSUPPORTED'),
    'PFD_reset_delay': ('p.pfd_reset_delay_s; event reset_remaining_s', 'PFD.reset_s; timing clip limit only', 'model/pfd_cp_event_step.m', 'YES: event delay and charge timing clip are different models'),
    'Cload': ('absent; unloaded ideal LF', 'LF.Cload_F; added to C1', 'pll_allocation/_legacy/physics/lf.py', 'v1 50fF proxy is not measured admittance; nonzero UNSUPPORTED'),
    'Gload': ('absent; unloaded ideal LF', 'LF.Rload_Ohm stored but incremental conductance omitted', 'pll_allocation/_legacy/physics/lf.py', 'YES: do not claim v1 Rload was dynamically integrated'),
}


def main():
    exp = load_experiment(ROOT/'configs/physics_mapping_stage1_v2.json')
    columns = ['Variable ID', 'Block', 'Unit', 'MATLAB definition', 'Python v1 definition',
               'Python v2 definition', 'Role', 'Source formula or file', 'Default',
               'Experiment range', 'Validity', 'Semantic conflict']
    rows = []
    def add(name, block, unit, matlab, py1, py2, role, source, default, domain, validity, conflict):
        rows.append(dict(zip(columns, [name, block, unit, matlab, py1, py2, role, source,
                                      str(default), domain, validity, conflict])))
    for name, rule in exp['block_space']['variables'].items():
        matlab, py1, source, conflict = INPUTS[name]
        domain = json.dumps({k: rule[k] for k in ('range', 'fixed', 'choices') if k in rule}, ensure_ascii=False)
        add(name, rule['block'], rule['unit'], matlab, py1, 'values.'+name, rule['role'],
            source+'; '+rule['source'], rule['default'], domain, rule['validity'], conflict)
    # Derived factors and measurements in this stage; values are ideal-point references.
    derived = [
        ('f_target', 'System', 'Hz', 'p.n_div*p.f_ref', 'fout_target_Hz checked against N*fref', 'F_FREQ_PLAN.f_target_Hz', 'Derived', 'model/solve_tuning_point.m', 80e6, 'N positive integer; fref>0', 'derived target is not a transient measurement'),
        ('Vctrl_required', 'VCO', 'V', 'fzero on monotonic f(V) within declared limits', 'V0+(fout-f0)/Kvco', 'F_TUNING.Vctrl_required_V=(N*fref-f0)/Kvco', 'Derived', 'model/solve_tuning_point.m', .4, 'interior voltage point required for M1', 'v1 V0 anchor differs'),
        ('tuning_feasible', 'VCO', '1', 'target between f(Vmin),f(Vmax), endpoints inclusive', 'candidate voltage check; separate trajectory domain', 'F_TUNING.feasible', 'Derived', 'model/solve_tuning_point.m', True, 'positive monotonic linear VCO', 'YES: endpoint feasible is not valid two-sided M1'),
        ('Kvco_local', 'VCO', 'Hz/V', 'p.kvco+2*p.kvco2*Vreq', 'constant Kvco_Hz_per_V', 'F_TUNING.Kvco_local_Hz_per_V', 'Derived', 'model/vco_model.m', 20e6, 'Stage 1 Kvco2=0', 'nonzero curvature deferred'),
        ('Kvco_angular', 'VCO', 'rad/s/V', '2*pi*Kvco_local', 'not a v1 input', 'explicit internal 2*pi*Kvco', 'Derived', 'model/pll_linear_kernel.m', 2*3.141592653589793*20e6, 'do not accept as Hz/V input', 'unit conversion explicit'),
        ('Iup', 'CP', 'A', 'Icp*(1+m/2)', 'CP.I_up_A positive timing slope', 'F_KPFD.Iup_A', 'Derived', 'model/pfd_cp_event_step.m', 1e-4, 'M1 m=0', 'v1 declared slope not observed device current'),
        ('Idown', 'CP', 'A', 'Icp*(1-m/2)', 'CP.I_down_A positive timing slope', 'F_KPFD.Idown_A', 'Derived', 'model/pfd_cp_event_step.m', 1e-4, 'M1 m=0', 'DOWN current subtracted by state logic'),
        ('Kpfd', 'PFD/CP', 'A/rad', 'p.i_cp/(2*pi)', 'no explicit continuous Kpfd in v1', 'F_KPFD.Kpfd_A_per_rad', 'Derived', 'model/pll_linear_kernel.m', 1e-4/(2*3.141592653589793), 'symmetric ideal zero-leakage/reset CP', 'do not infer gain from event reset approximation'),
        ('Zlf', 'LF', 'Ohm', '(1+s*Rz*C2)/(s*(C1+C2)+s^2*Rz*C1*C2)', 'impedance uses C1+Cload', 'response.Zlf_Ohm [real,imag]', 'Derived', 'model/pll_linear_kernel.m; legacy/physics/lf.py', 'frequency dependent', 's=j*2*pi*f; f>0; positive ideal RC; no load', 'Cload/proxy semantics differ'),
        ('fz', 'LF', 'Hz', '1/(2*pi*Rz*C2)', 'requirements.zero_Hz', 'F_LF_TF.zero_Hz', 'Derived', 'characterization/characterize_loop.m', 41663.59766803543, 'positive RC', 'none'),
        ('fp', 'LF', 'Hz', '(C1+C2)/(2*pi*Rz*C1*C2)', 'C1 effective includes Cload', 'F_LF_TF.nonzero_pole_Hz', 'Derived', 'characterization/characterize_loop.m', 458299.57434838975, 'positive RC; also integrator at 0', 'proxy load not carried over'),
        ('L', 'Loop', '1', 'Kpfd*2*pi*Kvco_local*Zlf/(N*s)', 'not validated in v1 backend', 'response.L [real,imag]', 'Derived', 'model/pll_linear_kernel.m', 'frequency dependent', 'locked continuous small signal; ideal subset', 'no sampled-loop equivalence established'),
        ('T', 'Loop', '1', 'L/(1+L)', 'not implemented in v1 backend', 'response.T [real,imag]', 'Derived', 'model/pll_linear_kernel.m', 'DC limit 1', 'normalized; H_ref=N*T', 'BW from normalized T not absolute H_ref'),
        ('UGF', 'Loop', 'Hz', 'first downward |L|=1 crossing', 'unsupported v1', 'metrics.UGF_Hz', 'Measurement', 'characterization/characterize_loop.m', 138176.4411317168, 'finite bracketed unique crossing; diagnostic only', 'frequency-domain derived measurement, not M2 measurement'),
        ('BW', 'Loop', 'Hz', 'first downward |T|=1/sqrt(2) crossing', 'unsupported v1', 'metrics.BW_Hz', 'Measurement', 'characterization/characterize_loop.m', 222379.18349260243, 'stable continuous M1; finite bracket', 'not UGF; not sampled bandwidth'),
        ('PM', 'Loop', 'deg', '180+angle(L_at_UGF)*180/pi', 'unsupported v1', 'metrics.PM_deg', 'Measurement', 'characterization/characterize_loop.m', 56.44269021253223, 'valid UGF; stable continuous M1', 'radians converted once'),
    ]
    for name, block, unit, matlab, py1, py2, role, source, default, validity, conflict in derived:
        add(name, block, unit, matlab, py1, py2, role, source, default, 'derived; no independent axis', validity, conflict)
    extras = [
        ('V0', 'VCO', 'V', 'implicit 0 V origin', 'VCO.V0_V frequency anchor voltage', 'no v2 independent anchor', 'Context', 'behavioral.py PHYSICS; model/vco_model.m', 'MATLAB=0; v1 varies', 'not a v2 axis', 'linear conversion only', 'YES: f0 offset required'),
        ('phase_err', 'PFD', 'rad', 'wrap(phi_ref-phi_div) in radians', 'wrap(feedback-reference) cycles, phase_deg=360*cycles', 'reference-minus-feedback radians', 'Derived', 'model/pll_behavioral_model.m; legacy/evaluation/python_behavioral.py', 'ideal lock 0', '[-pi,pi)', 'no time-domain M1 waveform', 'YES: e_v2_rad=-e_v1_deg*pi/180'),
        ('f_offset', 'Loop', 'Hz', 'positive logspace grid', 'legacy LF uses positive probe frequencies', 'FrequencyScan; response_frequencies_Hz', 'Context', 'characterization/characterize_loop.m', '8000 points; bounds derived from fz/fp/fref', 'positive; custom scan explicit', 'missing crossing => NUMERICAL_FAILURE', 'no units hidden in angular axis'),
        ('Vctrl0', 'VCO', 'V', 'p.vctrl0=0.15; acquisition initial value', 'initialization.Vctrl_V and Vc2_V', 'not executed in M1', 'Context', 'model/pll_params.m; model/pll_behavioral_model.m', .15, 'no Stage 1 axis', 'M2 only; initial lock not assumed proven', 'different initial conditions in v1 history'),
        ('Rload', 'LF', 'Ohm', 'absent', 'LF.Rload_Ohm; DC in q0; incremental conductance omitted', 'no proxy resistance axis; Gload=0', 'Context', 'legacy/physics/lf.py; legacy/evaluation/python_behavioral.py', 'v1 proxy 1e9', 'no Stage 1 axis', 'nonzero Gload unsupported', 'YES: finite stored Rload not a dynamic shunt'),
    ]
    for row in extras:
        add(*row)
    for s in exp['system_spec']['metrics']:
        matlab = 'N*fref' if s['metric'] == 'output_frequency_Hz' else 'historical illustrative BW 100-400kHz' if s['metric'] == 'BW_Hz' else 'historical illustrative PM>=45deg'
        add('spec_'+s['metric'], 'System', s['unit'], matlab, 'v1 frozen phase/frequency/lock targets; unchanged',
            s['protocol'], 'SystemSpec', s['source']+'; factors/pll_default_specs.m',
            json.dumps({k:s[k] for k in ('min','max') if k in s}), 'draft v0 fixed experiment bounds',
            'research target; continuous M1 only', 'new experimental targets are not old v1 constraints')
    out = ROOT/'docs/physics_mapping_stage1/variable_mapping.csv'
    with out.open('x', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f'{len(rows)} audited variables: {out}')


if __name__ == '__main__':
    main()
