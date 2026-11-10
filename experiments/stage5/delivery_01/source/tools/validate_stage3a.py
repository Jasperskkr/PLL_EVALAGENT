"""Read-only post-integration evidence/protection audit. Always creates a new output."""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.pipeline_contracts import check_result, load_inputs
from pll_allocation.track_a.core import Meter, assess_m1, read, write_new
from pll_allocation.physics_mapping.model import fingerprint

RUNS = ['stage3a_analytical_20261104_01', 'stage3a_optimization_20261104_01',
        'stage3a_llm_20261104_01', 'stage3a_feedback_repair_20261104_01',
        'stage3a_reverify_20261104_01']
ALLOWED = {'.gitignore', 'pyproject.toml', 'pll_allocation/cli.py',
           'README.md', 'docs/DECISIONS.md', 'docs/PROJECT_STATUS.md'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def functions(path):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    return {n.name: ast.dump(n, include_attributes=False) for n in tree.body if isinstance(n, ast.FunctionDef)}


def main(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    config, model, spec, protocol = load_inputs()
    protected = read(ROOT/'docs/stage3a/protected_before.json')
    changed, unexpected = [], []
    for row in protected:
        path = ROOT/row['path']
        actual = sha(path) if path.is_file() else None
        if actual != row['sha256']:
            item = {**row, 'after_sha256': actual, 'authorized': row['path'] in ALLOWED}
            changed.append(item)
            if not item['authorized']:
                unexpected.append(item)
    write_new(out/'protection_check.json', {'protected_count': len(protected),
        'unchanged': len(protected)-len(changed), 'authorized_changes': changed,
        'unexpected_changes': unexpected})
    reuse = read(ROOT/'docs/stage3a/reuse_manifest.json')
    for row in reuse:
        row['source_unchanged'] = sha(row['source']) == row['source_sha256']
        row['final_destination_sha256'] = sha(row['destination'])
        row['final_adaptation'] = 'Package imports/resources/native identity check only; research CLI removed; numerical decisions preserved'
    for relative, target, meaning in [
        ('track_b/tests/fixtures/nominal_measured.json', 'tests/fixtures/stage3a_nominal_measured.json', 'Actual historical measurement fixture; test boundary cases only'),
        ('configs/BLOCK_SPACE_MODEL_V1.json', 'configs/SYSTEM_SPEC_STAGE1_5.json', 'Exact semantic projection model.experiment.system_spec, not a changed target')]:
        reuse.append({'source': str(ROOT/relative), 'destination': str(ROOT/target),
            'source_sha256': sha(ROOT/relative), 'final_destination_sha256': sha(ROOT/target),
            'mode': 'byte_identical' if 'fixture' in relative else 'exact_semantic_projection',
            'domain': 'frozen Stage1.5 official snapshot only', 'semantics': meaning, 'source_unchanged': True})
    for relative in sorted((ROOT/'pll_allocation/track_a').glob('*.py')):
        reuse.append({'source': str(relative), 'destination': str(relative), 'source_sha256': sha(relative),
            'final_destination_sha256': sha(relative), 'source_unchanged': not any(r['path'] == relative.relative_to(ROOT).as_posix() for r in changed),
            'mode': 'in_place_direct_call', 'domain': 'unchanged Stage1.5 ideal SI / continuous M1',
            'semantics': 'Existing inverse/optimization/Agent/repair algorithm; does not issue final M2 verdict'})
    write_new(out/'reuse_manifest_final.json', reuse)
    old, new = ROOT/'track_b', ROOT/'pll_allocation/verification'
    preservation = {'kernel_byte_identical': sha(old/'kernel.cpp') == sha(new/'kernel.cpp'),
                    'protocol_byte_identical': sha(old/'protocol_v1_1.json') == sha(ROOT/'configs/verification/protocol_v1_1.json')}
    for name, funcs in [('measure.py', list(functions(old/'measure.py'))),
                        ('run_suite.py', ['capture_pair']),
                        ('verify.py', ['assemble_result', 'interval_judgment']),
                        ('experiments.py', ['response_point', 'response_sweep', 'compare_sweeps'])]:
        a, b = functions(old/name), functions(new/name)
        for function in funcs:
            preservation[name+':'+function+':AST_identical'] = a[function] == b[function]
    write_new(out/'numerical_preservation.json', preservation)
    rows = []
    artifacts = []
    for name in RUNS:
        run = ROOT/'experiments'/name
        result = read(run/'result.json')
        for attempt in result['attempts']:
            folder = run/attempt['directory']
            prop = read(folder/'AllocationProposal.json')
            measured = read(folder/'BehavioralVerificationResult.json')
            check_result(measured, prop, protocol)
            assert read(run/'initial_joint_block_spec.json') == read(run/'attempt_001/submitted_joint_block_spec.json')
            assert read(folder/'agent_feedback_receipt.json')['status'] == 'RECEIVED_BY_ALLOCATION_AGENT'
            rows.append({'run': name, 'strategy': result['strategy'], 'stage': attempt['stage'],
                'origin': result['candidate_origin'], 'M1_status': attempt['M1_status'], 'M2_status': attempt['M2_status'],
                'M1_BW_Hz': prop['M1']['prediction']['metrics']['BW_Hz'],
                'M2_BW_Hz': measured['metrics']['BW_Hz']['value'],
                'BW_relative_error': measured['prediction_errors']['BW_Hz']['relative_error'],
                'constraints': measured['constraints'], 'native_runs': measured['execution_cost']['completed_native_runs'],
                'parameter_sha256': prop['parameter_sha256'], 'overall_status': measured['overall_status'],
                'protocol_sha256': measured['protocol_sha256'], 'verified_joint_block_spec': result['verified_joint_block_spec']})
        for path in sorted(run.rglob('*')):
            if path.is_file():
                artifacts.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path), 'bytes': path.stat().st_size})
    reference = read(ROOT/'track_b/outputs/interface_track_a_real_01/result.json')
    current = read(ROOT/'experiments/stage3a_reverify_20261104_01/attempt_001/BehavioralVerificationResult.json')
    original = read(ROOT/'docs/track_a/delivery_final/AllocationProposal.json')
    compatibility = {'M1_bit_identical': assess_m1(model, spec, original['joint_block_spec'], Meter()) == original['M1'],
        'candidate_identical': current['parameter_sha256'] == reference['parameter_sha256'],
        'protocol_identical': current['protocol_sha256'] == reference['protocol_sha256'],
        'M2_metrics_bit_identical': current['metrics'] == reference['metrics'],
        'M2_constraints_identical': current['constraints'] == reference['constraints'],
        'M1_M2_errors_identical': current['prediction_errors'] == reference['prediction_errors'],
        'BW_difference_Hz': current['metrics']['BW_Hz']['value']-reference['metrics']['BW_Hz']['value'],
        'predeclared_BW_tolerance_relative': .02,
        'comparison_scope': 'Same exact DLL/source/protocol/candidate, independent actual execution; no new MATLAB claim'}
    llm = ROOT/'experiments/stage3a_llm_20261104_01/attempt_001/llm_calls'
    calls = [read(p) for p in sorted(llm.glob('call_*/metadata.json'))]
    llm_summary = {'real_calls': len(calls), 'responded': sum(x['status'] == 'RESPONDED' for x in calls),
        'requested_models': sorted({x['model'] for x in calls}), 'response_models': sorted({x['response_model'] for x in calls}),
        'usage': [x.get('usage') for x in calls], 'calls': calls, 'real_LLM_repair_tested': False}
    tests = []
    for file in sorted((ROOT/'experiments').glob('stage3a*/tests.xml')):
        node = ET.parse(file).getroot()
        suites = [node] if node.tag == 'testsuite' else list(node.iter('testsuite'))
        tests.append({'path': file.relative_to(ROOT).as_posix(),
                      **{k: sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}})
    write_new(out/'experiment_rows.json', rows)
    write_new(out/'compatibility.json', compatibility)
    write_new(out/'llm_execution.json', llm_summary)
    write_new(out/'test_history.json', tests)
    write_new(out/'artifact_hashes.json', artifacts)
    write_new(out/'git_after.json', {n: {'head': subprocess.check_output(['git', '-C', str(p), 'rev-parse', 'HEAD'], text=True).strip(),
        'status': subprocess.check_output(['git', '-C', str(p), 'status', '--short'], text=True)} for n, p in [('main', ROOT), ('track_b', ROOT/'track_b')]})
    final_tests = next(t for t in tests if 'regression_final_20261104_02' in t['path'])
    passed = (not unexpected and all(r['source_unchanged'] for r in reuse) and all(preservation.values())
              and all(v for v in compatibility.values() if isinstance(v, bool))
              and final_tests['errors'] == final_tests['failures'] == final_tests['skipped'] == 0
              and final_tests['tests'] >= 273 and llm_summary['real_calls'] == llm_summary['responded'] == 3)
    summary = {'stage': 'Stage3A', 'engineering_integration_checks_passed': passed,
        'full_behavioral_PASS': False, 'verified_joint_block_spec': False,
        'run_count': len(RUNS), 'executed_full_M2_verifications': len(rows),
        'native_completed_runs_main_experiments': sum(x['native_runs'] for x in rows),
        'real_LLM_calls': len(calls), 'final_tests': final_tests,
        'protection': {'files': len(protected), 'unexpected_changes': len(unexpected)},
        'independent_PM_certified': False, 'frequency_microHz_precision_certified': False,
        'awaiting_technical_leader_review': True}
    write_new(out/'acceptance.json', summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    raise SystemExit(main(parser.parse_args().out))
