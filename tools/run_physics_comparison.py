"""Small equal-budget comparison; invokes only the existing formal Pipeline CLI."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def summarize_run(folder):
    # Imports here keep this tool runnable directly from a source checkout.
    sys.path.insert(0, str(ROOT))
    from pll_allocation.physics_mapping.predictors import predict_rms_jitter
    result = read(folder/'allocation_result.json'); cost = result['cost']
    problem = read(folder/'problem_resolved.json')
    limit = next((s['max'] for s in problem['specs'] if s['enabled'] and s['metric'] == 'jitter_s' and 'max' in s), None)
    candidates = []
    representative = list(result['candidates'])
    best = result.get('conditional_noise_summary', {}).get('best_candidate')
    if best and best['parameter_sha256'] not in {r['parameter_sha256'] for r in representative}:
        representative.append(best)
    for row in representative:
        prediction = predict_rms_jitter(row['parameters'])
        candidates.append({'parameter_sha256': row['parameter_sha256'],
            'parameters_SI': {k: row['parameters']['values'][k] for k in problem['parameters']},
            'BW_Hz': row['metrics']['BW_Hz'], 'PM_deg': row['metrics']['PM_deg'], **prediction})
    known = [r for r in candidates if r['predicted_jitter_s'] is not None]
    m2 = folder/'verification/m2_verifications.jsonl'
    first = json.loads(m2.read_text(encoding='utf-8').splitlines()[0]) if m2.exists() and m2.stat().st_size else None
    observation = first['observation'] if first else None
    return {'M1_calls': cost['M1_calls'], 'M1_feasible_count': result['M1_distinct_feasible_count'],
        'conditional_jitter_pass_count': sum(r['predicted_jitter_s'] <= limit for r in known) if limit is not None else None,
        'best_predicted_jitter_s': min((r['predicted_jitter_s'] for r in known), default=None),
        'jitter_limit_s': limit,
        'first_M2_candidate_sha256': first['request']['candidate_sha256'] if first else None,
        'first_M2_lock_time_s': observation['metrics']['lock_time_s']['value'] if observation else None,
        'first_M2_supported_status': observation['supported_metrics_status'] if observation else 'NOT_EVALUATED',
        'first_M2_metric_status': {v['metric']: v['status'] for v in observation['constraints']} if observation else {},
        'M2_slots': cost['M2_verifications'], 'native_calls': cost['completed_native_runs'],
        'wall_time_s': cost['wall_time_s'], 'status': result['status'], 'failure': result['failure'],
        'initial_termination': result['initial_termination'], 'verification_termination': result['verification_termination'],
        'conditional_noise_summary': result.get('conditional_noise_summary'), 'candidates': candidates}


def write_summary(out, folders):
    summary = {name: summarize_run(folder) for name, folder in folders.items()}
    (out/'comparison.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    text = ['# 同预算功能级快速对照', '', 'K=5，M1上限96，M2上限3；确定性、零API。预测 jitter 单位ps，Lock单位µs。',
        '只有两道输入，无重复随机试验；不支持统计优越性结论。', '']
    for problem in ('nominal', 'tight'):
        text += ['## '+problem, '', '| 指标 | Baseline | Noise-Aware | Enhanced |', '|---|---:|---:|---:|']
        for label, key, scale in [('M1 Calls', 'M1_calls', 1), ('M1可行候选数', 'M1_feasible_count', 1),
            ('条件Jitter达标数', 'conditional_jitter_pass_count', 1), ('最佳预测Jitter(ps)', 'best_predicted_jitter_s', 1e12),
            ('首次M2 Lock(µs)', 'first_M2_lock_time_s', 1e6), ('首次M2支持项状态', 'first_M2_supported_status', 1),
            ('M2 Slots', 'M2_slots', 1), ('Native Calls', 'native_calls', 1), ('总耗时(s)', 'wall_time_s', 1)]:
            values = []
            for mode in ('baseline', 'noise_aware', 'enhanced'):
                value = summary[problem+'_'+mode][key]
                values.append(str(value) if not isinstance(value, (int, float)) else f'{value*scale:.6g}')
            text.append('| '+label+' | '+' | '.join(values)+' |')
        text.append('')
    (out/'comparison.md').write_text('\n'.join(text)+'\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--baseline-dir', type=Path, help='Reuse preserved pre-change nominal_baseline/tight_baseline only')
    args = parser.parse_args(); out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    base = read(ROOT/'configs/agent/spec_allocation.json')
    base.update(target_count=5, m1_budget=96, m2_budget=3, m2_target_count=3)
    modes = {'baseline': {}, 'noise_aware': {'noise_allocation_enabled': True},
        'enhanced': dict.fromkeys(('analytic_features_enabled', 'noise_allocation_enabled',
                                  'initial_state_aware_enabled', 'physics_ranking_enabled'), True)}
    folders = {}; runs = []
    for problem in ('nominal', 'tight'):
        for mode, flags in modes.items():
            name = problem+'_'+mode
            if mode == 'baseline' and args.baseline_dir:
                folders[name] = args.baseline_dir.resolve()/name
                runs.append({'case': name, 'source': 'PRESERVED_PRE_CHANGE_BASELINE', 'path': str(folders[name])})
                continue
            config = out/(name+'_config.json')
            config.write_text(json.dumps(base | flags, indent=2), encoding='utf-8')
            folders[name] = out/name
            command = [sys.executable, '-m', 'pll_allocation', 'pipeline', '--problem',
                str(ROOT/'configs/problems'/f'{problem}.json'), '--allocator-config', str(config), '--out', str(folders[name])]
            started = time.perf_counter()
            with (out/(name+'.log')).open('x', encoding='utf-8') as log:
                run = subprocess.run(command, cwd=ROOT, env=os.environ | {'PYTHONUTF8': '1'}, stdout=log, stderr=subprocess.STDOUT)
            runs.append({'case': name, 'command': command, 'returncode': run.returncode,
                         'elapsed_s': time.perf_counter()-started})
            (out/'execution_manifest.json').write_text(json.dumps(runs, indent=2), encoding='utf-8')
            if run.returncode or not (folders[name]/'allocation_result.json').exists():
                raise RuntimeError('Formal comparison run failed; preserved log: '+str(out/(name+'.log')))
    write_summary(out, folders)


if __name__ == '__main__':
    main()
