"""Stage4.1 fixed candidates -> fresh real frequency/step evidence, with holdout gate."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.physics_mapping.model import fingerprint, evaluate
from pll_allocation.physics_mapping.registry import load_registry
from pll_allocation.verification.experiments import read, write
from pll_allocation.verification.verify import example_proposal, verify
from pll_allocation.verification.return_ratio import sweep, protocol as rr_protocol
from pll_allocation.verification.closed_loop_native import simulate_step
from pll_allocation.verification.closed_loop import protocol, analyze, raw_validity, compare_refinements

CANDIDATES = ROOT/'docs/stage4_2/M2_VALIDATION_CANDIDATES.json'
REGISTRY = ROOT/'docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json'


def bindings():
    paths = [CANDIDATES, REGISTRY, ROOT/'configs/verification/closed_loop_stage4_1_v0_1.json']
    paths += list((ROOT/'pll_allocation/verification').glob('*.py'))
    paths += list((ROOT/'pll_allocation/verification').glob('*.cpp'))
    paths += [ROOT/'pll_allocation/physics_mapping/model.py', ROOT/'tools/run_stage41.py',
              ROOT/'tools/summarize_stage41.py', ROOT/'tools/refine_stage41_frequency.py',
              ROOT/'docs/stage4_1/ENGINEERING_VALIDATION_PLAN.md',
              ROOT/'docs/stage4_1/CLOSED_LOOP_PERTURBATION_PROTOCOL.md']
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for p in sorted(paths)}


def inputs():
    registry = load_registry(REGISTRY)
    item = read(CANDIDATES)
    if (item.get('schema_version') != 'pll-m2-candidate-plan-0.1'
            or item['model_versions'] != registry['model_versions']
            or item['block_space_sha256'] != registry['block_space_sha256']
            or item['system_spec_sha256'] != registry['system_spec_sha256']):
        raise ValueError('candidate plan model/spec/version mismatch')
    for candidate in item['candidates']:
        if fingerprint(candidate['joint_block_spec']) != candidate['parameter_sha256']:
            raise ValueError('candidate hash mismatch')
    return item['candidates'], registry


def save_step(folder, p, settings):
    folder.mkdir(parents=True, exist_ok=False)
    write(folder/'request.json', {'parameters': p, 'settings': settings, 'protocol': protocol()})
    try:
        run = simulate_step(p, **settings)
        np.savez_compressed(folder/'trajectory.npz', **{k: run[k] for k in ('trace', 'ref_edges', 'div_edges', 'events')})
        write(folder/'summary.json', {k: v for k, v in run.items() if k not in ('trace', 'ref_edges', 'div_edges', 'events')})
        return run
    except Exception as error:
        write(folder/'failure.json', {'status': 'UNKNOWN', 'reason': repr(error)})
        raise


def steps(folder, p):
    folder.mkdir(parents=True, exist_ok=False); doc = protocol()
    common = dict(onset_s=doc['onset_s'], rise_s=doc['rise_s'], record_interval_s=doc['record_interval_s'])
    variants = [('plus', .01, doc['dt_s'], doc['observation_s']),
                ('minus', -.01, doc['dt_s'], doc['observation_s']),
                ('double_plus', .02, doc['dt_s'], doc['observation_s']),
                ('double_minus', -.02, doc['dt_s'], doc['observation_s']),
                ('fine_plus', .01, doc['fine_dt_s'], doc['observation_s']),
                ('fine_minus', -.01, doc['fine_dt_s'], doc['observation_s']),
                ('long_plus', .01, doc['dt_s'], doc['long_observation_s']),
                ('long_minus', -.01, doc['dt_s'], doc['long_observation_s'])]
    zeros = {}; results = {}; curves = {}
    for name, dt, window in [('base', doc['dt_s'], doc['observation_s']),
                              ('fine', doc['fine_dt_s'], doc['observation_s']),
                              ('long', doc['dt_s'], doc['long_observation_s'])]:
        settings = common | dict(amplitude_rad=0., dt_s=dt, duration_s=doc['onset_s']+window)
        zero = save_step(folder/'raw'/('zero_'+name), p, settings)
        zeros[(dt, window)] = zero
        valid = raw_validity(zero, doc, baseline=True)
        write(folder/('zero_'+name+'_validity.json'), valid)
        if not valid['valid']:
            write(folder/'result.json', {'status': 'UNKNOWN', 'reason': 'unperturbed_working_point_invalid', 'baseline': valid})
            return
    for name, amplitude, dt, window in variants:
        run = save_step(folder/'raw'/name, p, common | dict(amplitude_rad=amplitude, dt_s=dt,
                                                        duration_s=doc['onset_s']+window))
        result, curve = analyze(p, run, zeros[(dt, window)], doc)
        results[name] = result
        if curve is not None:
            curves[name] = curve
            np.savetxt(folder/(name+'_cycle_response.csv'), curve, delimiter=',',
                       header='time_from_onset_s,input_normalized,M2_observed,M1_prediction', comments='')
        write(folder/(name+'_metrics.json'), result)
    convergence = compare_refinements(results, curves, doc)
    result = {'status': 'MEASURED' if convergence['converged'] else 'UNKNOWN',
              'results': results, 'convergence': convergence, 'protocol_sha256': fingerprint(doc)}
    write(folder/'result.json', result)
    print(folder.parent.name, 'steps', result['status'], flush=True)


def run_case(folder, c, *, anchor_result=None):
    folder.mkdir(parents=True, exist_ok=False); start = time.perf_counter()
    write(folder/'candidate.json', c); p = c['joint_block_spec']
    proposal = read(ROOT/c['source_proposal']['path']) if c['source_proposal'] else example_proposal(p, c['candidate_id'])
    if proposal['parameter_sha256'] != c['parameter_sha256']:
        raise ValueError('source proposal mismatch')
    write(folder/'AllocationProposal.json', proposal)
    if anchor_result:
        # Explicit fresh Stage4 anchor receipts; no old simulations counted again.
        write(folder/'frequency_evidence_reference.json', {'fresh_anchor_directory': str(anchor_result.resolve()),
              'reuse_is_not_new_simulation': True})
    else:
        doc = rr_protocol(); runs = {}
        for name, mode, amp, dt, cycles, grid in frequency_variants(doc):
            runs[name] = sweep(folder/'frequency'/'raw'/name, p, mode=mode, amplitude=amp,
                               dt=dt, cycles=cycles, grid=grid, doc=doc)
            print(c['candidate_id'], name, runs[name]['crossing'], flush=True)
        write(folder/'frequency_result.json', runs)
        write(folder/'BW_result.json', verify(proposal, folder/'BW_protocol1_1'))
    steps(folder/'steps', p)
    write(folder/'M1_posthoc.json', evaluate(p).as_dict())
    write(folder/'complete.json', {'wall_elapsed_s': time.perf_counter()-start})


def frequency_variants(doc):
    return [('base', 'series', .01, .4e-9, 12, doc['grid_Hz']),
            ('amplitude_half', 'series', .005, .4e-9, 12, doc['grid_Hz']),
            ('step_half', 'series', .01, .2e-9, 12, doc['grid_Hz']),
            ('window_double', 'series', .01, .4e-9, 24, doc['grid_Hz']),
            ('offset_grid', 'series', .01, .4e-9, 12, doc['offset_grid_Hz']),
            ('independent_clamp', 'clamp', .01, .4e-9, 12, doc['grid_Hz'])]


def main(args):
    candidates, registry = inputs(); out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    write(out/'source_bindings.json', bindings())
    write(out/'run_manifest.json', {'HEAD': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
          'mode': args.mode, 'registry_binding_checks': registry['runtime_binding_checks'],
          'new_LLM_calls': 0, 'started_unix': time.time(), 'protocol': protocol()})
    if args.mode == 'anchors':
        from run_stage4 import run_case as stage4_case
        for c in candidates[:2]:
            proposal = read(ROOT/c['source_proposal']['path']) if c['source_proposal'] else example_proposal(c['joint_block_spec'], c['candidate_id'])
            stage4_case(out/c['candidate_id'], proposal)
        write(out/'complete.json', {'fresh_anchors': True})
        return
    if args.mode == 'holdout':
        lock = read(args.lock)
        if lock['source_bindings'] != bindings() or not lock['development_complete']:
            raise ValueError('holdout source/protocol lock mismatch')
        if lock['holdout_ids'] != [c['candidate_id'] for c in candidates[8:]]:
            raise ValueError('holdout ID mismatch')
        write(out/'holdout_lock_used.json', lock)
        selected = candidates[8:]
    else:
        selected = candidates[:8]
    for c in selected:
        anchor = Path(args.anchors)/c['candidate_id'] if args.mode == 'development' and c in candidates[:2] else None
        run_case(out/c['candidate_id'], c, anchor_result=anchor)
    write(out/'complete.json', {'candidate_ids': [c['candidate_id'] for c in selected], 'completed_unix': time.time()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['anchors', 'development', 'holdout'], required=True)
    parser.add_argument('--out', required=True); parser.add_argument('--anchors'); parser.add_argument('--lock')
    args = parser.parse_args()
    if args.mode == 'development' and not args.anchors:
        parser.error('development requires newly executed --anchors')
    if args.mode == 'holdout' and not args.lock:
        parser.error('holdout requires --lock')
    main(args)
