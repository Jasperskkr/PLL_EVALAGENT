"""Prewritten target snapshots then equal-budget first-shot experiments."""
from __future__ import annotations
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from .core import file_manifest, fingerprint, load_model, read, write_new
from .runner import run_first


def build_targets(model, plan):
    targets = {'official': deepcopy(model['experiment']['system_spec'])}
    for item in plan['variants']:
        target = deepcopy(targets['official'])
        target['source'] = 'Track A controlled test variant: ' + item['id']
        for spec in target['metrics']:
            if spec['metric'] == 'BW_Hz':
                spec['min'], spec['max'] = item['BW_Hz']
            elif spec['metric'] == 'PM_deg':
                spec['min'] = item['PM_min_deg']
            spec['source'] = target['source']
        targets[item['id']] = target
    return targets


def benchmark(model_path, plan_path, out):
    model, plan = load_model(model_path), read(plan_path)
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    targets = build_targets(model, plan)
    # Entire plan and all target variants saved before any numerical execution.
    write_new(root/'benchmark_plan.json', plan)
    write_new(root/'target_snapshots.json', targets)
    write_new(root/'experiment_freeze.json', {'model_sha256': fingerprint(model),
        'targets_sha256': fingerprint(targets), 'plan_sha256': fingerprint(plan),
        'current_target_M2_feedback': False, 'calibration_cases': plan['calibration_cases']})
    results, rows = [], []
    for target_id, spec in targets.items():
        for strategy in plan['strategies']:
            result = run_first(model, spec, strategy, root/target_id/strategy, plan, seed=plan['random_seed'])
            result['target_id'] = target_id
            results.append(result)
            pred = ((result['assessment'] or {}).get('prediction') or {}).get('metrics', {})
            cost = result['allocation_cost'] or result['cost']
            rows.append({'target': target_id, 'strategy': strategy, 'status': result['status'],
                'BW_Hz': pred.get('BW_Hz'), 'PM_deg': pred.get('PM_deg'), 'Vctrl_V': pred.get('Vctrl_required_V'),
                'min_normalized_margin': (result['margins'] or {}).get('minimum_normalized_margin'),
                'allocation_elapsed_s': result['candidate_generation_elapsed_s'],
                'allocation_analytic_calls': cost['analytic_calls'], 'allocation_M1_calls': cost['M1_calls'],
                'candidate_generations': cost['candidate_generations'], 'total_M1_calls': result['cost']['M1_calls'],
                'M2_calls': result['cost']['M2_calls'], 'LLM_calls': result['cost']['LLM_calls']})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    write_new(root/'all_results.json', results)
    with (root/'comparison.csv').open('x', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    sources = sorted(Path(__file__).parent.glob('*.py')) + [Path(model_path), Path(plan_path)]
    write_new(root/'run_manifest.json', {'scope': 'M1_FIRST_SHOT_ONLY', 'argv': sys.argv,
        'files': file_manifest(sources, 'Track A runtime'), 'M2_calls': 0,
        'statistics': 'descriptive case counts only; not a population first-shot success rate',
        'seed': plan['random_seed'], 'rows': len(rows)})
    lines = ['# Track A first-shot benchmark', '',
        '同目标、同域、同预算；一次正式提交，M2=0。仅M1预测及独立M1实现复核。官方为已知先验案例，变体为提前保存的受控测试；无统计意义成功率。', '',
        '|目标|策略|首次M1状态|BW kHz|PM °|最小归一化裕量|分配秒|解析调用|分配M1|',
        '|---|---|---|---:|---:|---:|---:|---:|---:|']
    def fmt(x, scale=1):
        return '-' if x is None else f'{x/scale:.5g}'
    for row in rows:
        lines.append('|'+ '|'.join([row['target'], row['strategy'], row['status'], fmt(row['BW_Hz'], 1e3),
            fmt(row['PM_deg']), fmt(row['min_normalized_margin']), fmt(row['allocation_elapsed_s']),
            str(row['allocation_analytic_calls']), str(row['allocation_M1_calls'])])+'|')
    lines += ['', '各次首次候选、AllocationProposal、成本事件、Agent日志、后选定扰动诊断均在对应目标/策略子目录。',
        'mock_agent只验收工具工作流；不能计入真实LLM成绩或增量收益。解析和优化的比较受公开nominal先验及工程归一化准则影响。']
    (root/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return rows


def protection_snapshot(root, out):
    """Protect every pre-existing tracked source and historical output, not new results."""
    root = Path(root).resolve()
    tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=root, capture_output=True, check=True).stdout.decode('utf-8').split('\0')
    paths = [root/p for p in tracked if p and not p.startswith(('docs/track_a/', 'configs/track_a/', 'tests/track_a/', 'pll_allocation/track_a/'))
             and p not in ('docs/DECISIONS.md', 'docs/PROJECT_STATUS.md')]
    historical = [p for p in (root/'outputs').rglob('*') if p.is_file() and not p.relative_to(root/'outputs').parts[0].startswith('track_a')]
    snapshot = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths+historical))}
    write_new(out, snapshot)
    return snapshot


def check_protection(root, snapshot):
    root = Path(root)
    changed = [name for name, expected in snapshot.items() if not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest() != expected]
    return {'protected_files': len(snapshot), 'changed': changed, 'all_unchanged': not changed}
