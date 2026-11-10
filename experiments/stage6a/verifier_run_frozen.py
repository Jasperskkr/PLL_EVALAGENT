"""Run only the frozen Stage 6A order through the sole formal module CLI."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pll_allocation.physics_mapping.model import fingerprint


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def source_check(plan):
    actual = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in plan['source_identity']}
    wrong = [name for name, value in actual.items() if value != plan['source_identity'][name]]
    if wrong:
        raise RuntimeError('FROZEN_SOURCE_CHANGED:'+str(wrong))
    return actual


def baseline_comparison(run, out):
    historical = ROOT/'experiments/stage5/firstshot_01/runs/S0__analytical/attempt_001'
    current = run/'attempt_001'
    old_m1 = read(historical/'M1_prediction.json')
    old_m1.pop('scenario_binding', None)
    new_m1 = read(current/'M1_prediction.json')
    old_m2 = read(historical/'BehavioralVerificationResult.json')
    new_m2 = read(current/'BehavioralVerificationResult.json')
    keys = ['metrics', 'constraints', 'overall_status', 'verified_joint_block_spec',
        'validation_level', 'M1_posthoc', 'prediction_errors', 'PM_diagnostic_only', 'reliability',
        'simulation_settings', 'source_hashes']
    # Research S0 has equal thresholds but a deliberately different BW reason string.
    def semantic_m2(result):
        semantic = {key: deepcopy(result[key]) for key in keys}
        for check in semantic['constraints']:
            check.pop('reason', None)
        return semantic
    checks = {'complete_candidate_equal':read(historical/'submitted_joint_block_spec.json') == read(current/'submitted_joint_block_spec.json'),
        'complete_M1_semantics_equal':old_m1 == new_m1,
        'M2_semantics_equal':semantic_m2(old_m2) == semantic_m2(new_m2)}
    write(out/'E0_baseline_comparison.json', {'checks':checks, 'all_passed':all(checks.values()),
        'historical':str(historical), 'current':str(current), 'M2_semantic_fields':keys,
        'excluded':'candidate ids/scenario metadata, BW explanation prose and nondeterministic timing; numerical metrics, uncertainty, targets/status and model identity included'})
    if not all(checks.values()):
        raise RuntimeError('BASELINE_SEMANTICS_MISMATCH')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['baseline', 'remaining'], required=True)
    args = parser.parse_args()
    plan_path = ROOT/'experiments/stage6a/frozen_01/experiment_plan.json'
    plan = read(plan_path)
    assert plan['plan_sha256'] == fingerprint({k:v for k,v in plan.items() if k!='plan_sha256'}) == 'c3d017a6fb3eac69e362aa42e400a6a244de91b0e5074d9617ed7ec08026162f'
    out = ROOT/'experiments/stage6a/m2_01'
    if args.phase == 'baseline':
        if not out.exists():
            out.mkdir(parents=True, exist_ok=False)
            (out/'receipts').mkdir()
            write(out/'source_start.json', source_check(plan))
        else:
            assert (out/'receipts/preflight_failure_01.json').is_file()
            assert not (out/'runs').exists(), 'Resume only before any candidate execution'
            write(out/'preflight_resume_01.json', {'reason':'canonical proposal hash validation corrected before any M2', 'source':source_check(plan)})
    else:
        assert read(out/'E0_baseline_comparison.json')['all_passed']
    names = plan['candidate_order'][:1] if args.phase == 'baseline' else plan['candidate_order'][1:]
    for name in names:
        source_check(plan)
        binding = plan['candidate_bindings'][name]
        proposal = ROOT/binding['proposal_file']
        assert fingerprint(read(proposal)) == binding['proposal_sha256']
        assert read(proposal)['parameter_sha256'] == binding['parameter_sha256']
        run = out/'runs'/name
        formal_args = ['pipeline','--strategy','analytical','--proposal',str(proposal.relative_to(ROOT)),
            '--m2-budget','1','--repair-budget','0','--out',str(run.relative_to(ROOT))]
        timing = out/'receipts'/(name+'_timing.json')
        cmd = [sys.executable,'-B',str(ROOT/'experiments/stage6a/verifier_pipeline_timing.py'),str(timing),*formal_args]
        start = time.perf_counter()
        process = subprocess.run(cmd,cwd=ROOT,capture_output=True)
        elapsed = time.perf_counter()-start
        (out/'receipts'/(name+'_stdout.txt')).write_bytes(process.stdout)
        (out/'receipts'/(name+'_stderr.txt')).write_bytes(process.stderr)
        source_check(plan)
        record = {'name':name,'command':cmd,'equivalent_formal_command':['python','-B','-m','pll_allocation',*formal_args],
            'returncode':process.returncode,'process_wall_s':elapsed,'proposal_sha256':binding['proposal_sha256'],
            'proposal_raw_sha256':hashlib.sha256(proposal.read_bytes()).hexdigest(),
            'parameter_sha256':binding['parameter_sha256'],'plan_sha256':plan['plan_sha256']}
        if (run/'result.json').is_file():
            result = read(run/'result.json')
            record.update(pipeline_status=result['status'],cost=result['cost'],failure=result['failure'])
            measurement = read(run/'attempt_001/BehavioralVerificationResult.json')
            record['measurements'] = measurement['metrics']
            native = []
            for path in (run/'raw').rglob('summary.json'):
                summary = read(path)['summary']
                component = 'capture' if 'capture' in path.parts else 'BW_response'
                native.append({'path':str(path.relative_to(ROOT)),'component':component,**summary})
            record['native_components'] = {component:{'runs':sum(x['component']==component for x in native),
                'elapsed_s':sum(x['elapsed_s'] for x in native if x['component']==component),
                'integration_points':sum(x['integration_points'] for x in native if x['component']==component)} for component in ('capture','BW_response')}
            write(out/'receipts'/(name+'_native.json'),native)
        write(out/'receipts'/(name+'_receipt.json'),record)
        print(json.dumps({'name':name,'returncode':process.returncode,'wall_s':elapsed,'status':record.get('pipeline_status'),
            'BW':record.get('measurements',{}).get('BW_Hz'), 'lock_time':record.get('measurements',{}).get('lock_time_s')},allow_nan=False),flush=True)
        if name == 'E0_analytical':
            baseline_comparison(run,out)
        if process.returncode != 0:
            raise RuntimeError('FORMAL_PIPELINE_FAILED:'+name)
    write(out/(args.phase+'_source_end.json'), source_check(plan))


if __name__ == '__main__':
    main()
