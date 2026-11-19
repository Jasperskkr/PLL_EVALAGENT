"""Prepare public example inputs and invoke the one official pipeline CLI.

No solver, verifier, historical results or API client lives in this wrapper.
Real LLM examples require an explicit flag and the configured process environment.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'configs/examples/spec_allocation.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def run_cases(names, out, *, allow_paid_llm=False):
    manifest = read(MANIFEST)
    if not names or len(set(names)) != len(names):
        raise ValueError('select at least one case, with no duplicates')
    unknown = set(names) - set(manifest['cases'])
    if unknown:
        raise ValueError('unknown cases: ' + ', '.join(sorted(unknown)))
    base = read(ROOT / manifest['base_config'])
    provider = read(ROOT / manifest['provider_config'])
    paid = any(manifest['cases'][name].get('requires_paid_llm', False) for name in names)
    if paid:
        if not allow_paid_llm:
            raise ValueError('real LLM examples require explicit --allow-paid-llm authorization')
        required = [provider[key] for key in ('model_env', 'api_key_env', 'base_url_env')]
        missing = [name for name in required if not os.environ.get(name, '').strip()]
        if missing:
            raise ValueError('missing process environment variables: ' + ', '.join(missing))
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write(root / 'example_inputs.json', manifest)
    summary = []
    for name in names:
        case = manifest['cases'][name]
        folder = root / name
        folder.mkdir()
        config = base | case['overrides']
        # Authorization is local to explicitly selected real-LLM cases.
        config['allow_paid_llm'] = bool(case.get('requires_paid_llm', False) and allow_paid_llm)
        config_path = folder / 'allocator_config.json'
        write(config_path, config)
        command = [sys.executable, '-m', 'pll_allocation', 'pipeline',
                   '--problem', str(ROOT / case['problem']),
                   '--allocator-config', str(config_path), '--out', str(folder / 'run')]
        if config['allow_paid_llm']:
            command += ['--llm-config', str(ROOT / manifest['provider_config'])]
        write(folder / 'command.json', {'argv': command, 'cwd': str(ROOT)})
        with (folder / 'stdout.log').open('x', encoding='utf-8') as stdout, \
                (folder / 'stderr.log').open('x', encoding='utf-8') as stderr:
            completed = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                       env=os.environ | {'PYTHONIOENCODING': 'utf-8'}, check=False)
        result_path = folder / 'run/allocation_result.json'
        result = read(result_path) if result_path.is_file() else {}
        row = {'case': name, 'mode': config['mode'], 'returncode': completed.returncode,
               'status': result.get('status', 'NO_RESULT'),
               'M1_distinct_feasible_count': result.get('M1_distinct_feasible_count'),
               'M1_quality_count': result.get('M1_quality_count'),
               'M2_supported_pass_count': result.get('M2_supported_pass_count'),
               'm2_target_count': result.get('m2_target_count'),
               'joint_status': result.get('joint_status'),
               'joint_target_reached': result.get('joint_target_reached'),
               'time_to_first_joint_s': result.get('time_to_first_joint_s'),
               'time_to_joint_target_s': result.get('time_to_joint_target_s'),
               'M2_executed': bool(result.get('cost', {}).get('M2_verifications', 0)),
               'cost': result.get('cost'), 'failure': result.get('failure'),
               'result_path': str(result_path)}
        summary.append(row)
        write(folder / 'summary.json', row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    write(root / 'summary.json', {'schema_version': manifest['schema_version'], 'cases': summary,
          'scope': 'Fresh pipeline executions; M2 counts refer to supported metrics only. '
                   'Zero M2 calls means not evaluated. Real LLM responses may vary.'})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='list input cases without running')
    parser.add_argument('--case', action='append', default=[], help='case name; repeat to select multiple')
    parser.add_argument('--out', help='fresh output root, normally experiments/<new_run_id>')
    parser.add_argument('--allow-paid-llm', action='store_true', help='authorize real API calls for selected LLM cases')
    args = parser.parse_args(argv)
    if args.list:
        for name, case in read(MANIFEST)['cases'].items():
            print(name + ': ' + case['description'])
        return 0
    if not args.out:
        parser.error('--out is required when running cases')
    try:
        results = run_cases(args.case, args.out, allow_paid_llm=args.allow_paid_llm)
    except (ValueError, FileExistsError) as error:
        parser.error(str(error))
    return 0 if all(row['returncode'] == 0 and row['status'] != 'NO_RESULT' for row in results) else 2


if __name__ == '__main__':
    raise SystemExit(main())
