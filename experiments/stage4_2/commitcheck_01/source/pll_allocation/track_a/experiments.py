"""Reproducible simulated repair exercise; no fake M2 success statistics."""
from pathlib import Path
from .core import Meter, fingerprint, make_candidate, write_new
from .repair import KINDS, repair
from .feedback_agent import MockRepairPolicy, run_repair_agent


def simulated_repairs(model, system_spec, out):
    root = Path(out)
    root.mkdir(parents=True, exist_ok=False)
    candidate = make_candidate(model)
    rows = []
    for kind in sorted(KINDS):
        feedback = {'schema_version': 'allocation-feedback-1.0', 'parameter_sha256': fingerprint(candidate),
            'source': 'SIMULATED', 'kind': kind,
            'verdict': 'UNKNOWN' if kind in ('MODEL_OUT_OF_DOMAIN', 'UNRELIABLE_MEASUREMENT') else 'FAIL',
            'measurements': {'BW_Hz': {'value': 310000, 'unit': 'Hz', 'reliable': True}},
            'note': 'Synthetic failure routing fixture; not a measured candidate result.'}
        meter = Meter()
        new, decision = repair(model, system_spec, candidate, feedback, meter)
        row = {'kind': kind, 'feedback': feedback, 'original_candidate': candidate,
               'repair_candidate': new, 'decision': decision, 'cost': meter.counts}
        write_new(root/(kind+'.json'), row)
        write_new(root/(kind+'_cost.json'), meter.events)
        rows.append(row)
    write_new(root/'summary.json', {'source': 'SIMULATED_ONLY', 'M2_calls': 0, 'cases': len(rows),
        'real_repair_success_rate': None, 'rows': [{'kind': r['kind'], 'action': r['decision']['action']} for r in rows]})
    return rows


def simulated_agent_repairs(model, system_spec, out):
    root = Path(out)
    root.mkdir(parents=True, exist_ok=False)
    candidate = make_candidate(model)
    results = []
    for kind in sorted(KINDS):
        feedback = {'schema_version': 'allocation-feedback-1.0', 'parameter_sha256': fingerprint(candidate),
            'source': 'SIMULATED', 'kind': kind,
            'verdict': 'UNKNOWN' if kind in ('MODEL_OUT_OF_DOMAIN', 'UNRELIABLE_MEASUREMENT') else 'FAIL',
            'measurements': {'BW_Hz': {'value': 310000, 'unit': 'Hz', 'reliable': True}}}
        meter = Meter()
        result = run_repair_agent(model, system_spec, candidate, feedback, meter, root/kind, MockRepairPolicy())
        write_new(root/kind/'cost_events.json', meter.events)
        results.append({'kind': kind, **result})
    write_new(root/'summary.json', {'source': 'SIMULATED_ONLY', 'real_LLM_calls': 0,
        'M2_calls': 0, 'real_repair_success_rate': None, 'results': results})
    return results
