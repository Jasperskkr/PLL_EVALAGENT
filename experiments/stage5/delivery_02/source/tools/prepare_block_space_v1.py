"""Audit first, then create a sourced Stage 1.5 model without changing Stage 1."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.physics_mapping.model import fingerprint


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    original_path = ROOT/'configs/physics_mapping_stage1_v2.json'
    exp = json.loads(original_path.read_text(encoding='utf-8'))
    source_manifest = json.loads((ROOT/'docs/physics_mapping_stage1/audit/source_manifest.json').read_text(encoding='utf-8'))
    reference = Path(source_manifest['matlab_root'])/'verification/python_crosscheck.py'
    old_reference = next(x for x in source_manifest['sources'] if x['path'] == str(reference))
    assert sha(reference) == old_reference['sha256'], 'reference changed since Stage 1 audit'
    audit = ROOT/'docs/stage1_5/audit'
    audit.mkdir(parents=True, exist_ok=False)
    # Capture every already existing project and MATLAB file except expected append-only docs.
    allowed = {ROOT/'docs/PROJECT_STATUS.md', ROOT/'docs/DECISIONS.md'}
    protected = []
    for base in (ROOT, Path(source_manifest['matlab_root'])):
        for p in sorted(base.rglob('*')):
            if (p.is_file() and p not in allowed and '__pycache__' not in p.parts
                    and '.pytest_cache' not in p.parts and '.git' not in p.parts
                    and audit not in p.parents):
                protected.append({'path': str(p), 'sha256': sha(p)})
    write_new(audit/'protected_before.json', protected)
    source_rows = source_manifest['sources'] + [
        {'path': str(p), 'sha256': sha(p), 'mode': 'reuse_unchanged', 'domain': 'Stage 1 ideal continuous M1',
         'semantic': 'same formulas, same parameter ranges and SystemSpec; Stage 1.5 adds domain/evidence contracts'}
        for p in [original_path, ROOT/'pll_allocation/physics_mapping/model.py',
                  ROOT/'pll_allocation/physics_mapping/experiment.py', ROOT/'pll_allocation/physics_mapping/validation.py',
                  ROOT/'docs/physics_mapping_stage1/variable_mapping.csv']]
    write_new(audit/'source_manifest.json', {'sources': source_rows, 'protected_files': len(protected),
        'reference_semantic': 'reuse simulate only: fixed-step edge-interpolated PFD, Euler KCL, clipped vctrl; not MATLAB execution'})
    destination = ROOT/'data/behavioral_space_v1/reference/python_crosscheck.py'
    destination.parent.mkdir(parents=True, exist_ok=False)
    with destination.open('xb') as stream:
        stream.write(reference.read_bytes())
    write_new(destination.parent/'provenance.json', {'source': str(reference), 'destination': str(destination),
        'sha256': sha(destination), 'mode': 'byte_identical_read_only_reference',
        'execution': 'AST-extract only simulate function, never check() or write reference results',
        'limitations': ['fixed-step edge interpolation; Euler integration', 'hardcoded 0..1.2 V rails',
                        'ideal equal-current CP, reset=0, no leakage, linear VCO',
                        'returns summaries, not raw waveforms; RMS phase is not a formal lock detector']})
    with (ROOT/'docs/physics_mapping_stage1/variable_mapping.csv').open(encoding='utf-8-sig', newline='') as stream:
        mapping = list(csv.DictReader(stream))
    variable_catalog = []
    for row in mapping:
        name = row['Variable ID']
        rule = exp['block_space']['variables'].get(name)
        kind = ('free_allocation_parameter' if rule and ('range' in rule or 'choices' in rule)
                else 'model_assumption' if rule and name in {'Kvco2','CP_mismatch','CP_leakage','q0','PFD_reset_delay','Cload','Gload'}
                else 'fixed_condition' if rule else 'system_measurement' if row['Role'] == 'Measurement'
                else 'system_requirement' if row['Role'] == 'SystemSpec' else 'derived_parameter' if row['Role'] == 'Derived' else 'context_not_executed')
        variable_catalog.append({'id': name, 'kind': kind, 'block': row['Block'], 'unit': row['Unit'],
            'participation': 'M1_input_or_domain_gate' if rule else 'M1_derived' if row['Role'] in {'Derived','Measurement'} and name not in {'phase_err','V0'}
                             else 'acceptance_bound' if row['Role'] == 'SystemSpec' else 'semantic_reference_not_executed',
            'stage1_mapping': row})
    reasons = {
        'Icp': 'Factor-of-two local gain exploration about 100uA; preserve Stage 1 declared bounds, not device evidence.',
        'Rz': 'Probe zero/pole and damping tradeoff around 3820 Ohm without changing Stage 1 bounds.',
        'C1': 'Three declared shunt capacitances, spanning 0.5x to 2x nominal.',
        'C2': 'Three declared branch capacitances, spanning 0.5x to 2x nominal.',
        'f0': 'Zero-volt intercept choices permit both interior tuning and unreachable cases.',
        'Kvco': 'Positive frequency slope spanning 0.5x to 2x nominal; jointly constrained by tuning.',
    }
    variables = {}
    for name, rule in exp['block_space']['variables'].items():
        variables[name] = dict(rule, kind=next(x['kind'] for x in variable_catalog if x['id'] == name),
            participates_in_calculation=True, domain_mode='range' if 'range' in rule else 'choices' if 'choices' in rule else 'fixed',
            range_provenance='MANUALLY_DECLARED_BEHAVIORAL_EXPERIMENT' if name in reasons else 'FIXED_EXPERIMENT_OR_IDEAL_ASSUMPTION',
            range_rationale=reasons.get(name, 'Preserve Stage 1 fixed context or ideal-model assumption; no extension authorized.'))
    model = {
        'schema_version': 'behavioral-block-space-1.0', 'model_id': 'integer_n_cppll_behavioral_space_v1',
        'versions': {'formula_version': 'stage1_m1_1.0.0', 'parameter_domain_version': 'stage1_declared_domain_1.0.0',
                     'behavioral_model_version': 'reference_python_edge_euler_sha256_'+sha(reference)[:12]},
        'scope': 'BEHAVIORAL_ONLY_NO_IMPLEMENTATION_CAPABILITY_CLAIM',
        'experiment_freeze': {'status': 'FROZEN_FOR_STAGE_1_5_VALIDATION_ONLY', 'source_path': str(original_path),
            'source_file_sha256': sha(original_path), 'experiment_sha256': fingerprint(exp),
            'global_research_spec_frozen': False, 'conflict_resolution': 'Stage 1 draft retained byte-semantically; no global promotion. Older MATLAB/v1 metrics excluded.'},
        'topology': {'id': exp['topology'], 'blocks': ['PFD','CP','LF','VCO','Divider'],
            'connections': [['PFD','CP'],['CP','LF'],['LF','VCO'],['VCO','Divider'],['Divider','PFD']]},
        'experiment': exp, 'variables': variables, 'variable_catalog': variable_catalog,
        'joint_constraints': [
            {'id': 'J_FREQ', 'layer': 'model_validity', 'expression': 'f_target=N*f_ref=80e6 Hz', 'implementation': 'contracts.check_parameters'},
            {'id': 'J_TUNING', 'layer': 'model_validity', 'expression': 'Vmin < (N*f_ref-f0)/Kvco < Vmax', 'implementation': 'contracts.check_parameters'},
            {'id': 'J_GAIN', 'layer': 'coupling', 'expression': 'G=Icp*Kvco/N; equal products preserve continuous L, not Vreq', 'implementation': 'Stage1 M1Evaluator'},
            {'id': 'J_LF', 'layer': 'coupling', 'expression': 'wz=1/(Rz*C2); wp=(C1+C2)/(Rz*C1*C2)', 'implementation': 'Stage1 M1Evaluator'},
            {'id': 'J_STABILITY', 'layer': 'model_validity', 'expression': 'b*c-a*d=(Icp*Kvco/N)*Rz*C2^2>0 for positive declared values', 'implementation': 'contracts.check_parameters'},
            {'id': 'J_IDEAL', 'layer': 'model_validity', 'expression': 'Kvco2=mismatch=leakage=q0=reset=Cload=Gload=0', 'implementation': 'Stage1 parse_parameters'},
            {'id': 'J_SYSTEM', 'layer': 'system_feasible_region', 'expression': 'interior tuning AND 150e3<=BW<=300e3 AND PM>=50deg', 'implementation': 'contracts.forward'},
        ],
        'metric_support': {
            'output_frequency_Hz': {'evaluator': 'M1', 'status': 'CONDITIONAL_STATIC_TUNING', 'behavioral_validation': 'SPARSE_EVENT_TB_CHECK_REQUIRED'},
            'BW_Hz': {'evaluator': 'M1', 'status': 'CONTINUOUS_FORMULA_NUMERICAL_VALIDATION', 'behavioral_validation': 'NOT_MEASURED_NO_INJECTION_PROTOCOL'},
            'PM_deg': {'evaluator': 'M1', 'status': 'CONTINUOUS_FORMULA_NUMERICAL_VALIDATION', 'behavioral_validation': 'NOT_MEASURED_NO_INJECTION_PROTOCOL'},
            'UGF_Hz': {'evaluator': 'M1', 'role': 'diagnostic', 'status': 'CONTINUOUS_FORMULA_NUMERICAL_VALIDATION'},
            'Jitter': {'status': 'UNSUPPORTED'}, 'Lock_Time': {'status': 'UNSUPPORTED'},
            'Static_Phase_Error': {'status': 'UNSUPPORTED_AS_SYSTEMSPEC'}, 'Power': {'status': 'UNSUPPORTED'},
        },
        'equation_registry': 'configs/PLL_EQUATION_REGISTRY_V1.json',
        'source_manifest': 'docs/stage1_5/audit/source_manifest.json',
        'validation_evidence': {'status': 'PENDING_DOMAIN_SCAN', 'report': 'docs/stage1_5/DOMAIN_VALIDATION_REPORT.md',
            'per_case_evidence_required': True, 'coverage_claim': 'representative_samples_not_entire_domain'},
        'calibration_policy': {'raw_physics_immutable': True, 'residual_model': 'NOT_IMPLEMENTED',
            'record_schema': 'prediction-discrepancy-1.0',
            'required_fields': ['formula_version','parameter_domain_version','behavioral_model_version','parameter_sha256',
                'metric','prediction','reference','unit','prediction_protocol','reference_protocol','validation_evidence',
                'prediction_error','known_limitations','recommended_calibration_action','classification'],
            'classifications': ['NUMERICAL_IMPLEMENTATION_ERROR','FORMULA_ASSUMPTION_INVALID','PARAMETER_SEMANTICS_MISMATCH',
                                'MISSING_BEHAVIORAL_EFFECT','MEASUREMENT_PROTOCOL_MISMATCH','UNRESOLVED']},
    }
    write_new(ROOT/'configs/BLOCK_SPACE_MODEL_V1.json', model)
    write_new(ROOT/'docs/stage1_5/EXPERIMENT_FREEZE.json', model['experiment_freeze'])
    print(f'Prepared sourced Block Space Model v1; {len(protected)} protected files; 41-variable catalog.')


if __name__ == '__main__':
    main()
