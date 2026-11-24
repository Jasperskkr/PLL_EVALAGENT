"""Opt-in discrete VCO acceptance probes using the existing Runner and native M2."""
from copy import deepcopy
from pathlib import Path

from ..agent.candidates import CandidateArchive
from ..agent.handoff import build_handoff
from ..agent.subregion_context import export_context
from ..agent.subregion_tools import envelope
from ..allocation.core import write_new
from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import check_candidate, judge, make_parameters, number, require, resolve_problem
from ..exploration.engine import model_identity
from ..physics_mapping.model import MappingResult, Status, fingerprint, parse_parameters
from ..region_explorer import RegionExplorer
from .contract import _problem


def analyze_vco_acceptance_region(candidate, *, problem, out, experiment_id,
                                  kvco_values=None, vlock_values=None,
                                  sample_budget=64, m1_budget=64, m2_budget=0,
                                  m2_timeout_s=180, revalidation_problem=None):
    """Probe discrete points; no rectangle, interpolant or unsampled area is PASS.

    CP/LF stay fixed. Old search bounds remain explicit and distinct from the
    formal model domain. An optional new legal problem must preserve SystemSpec.
    Native M2 uses the original audited handoff and verification request, with
    at most four calls. M1 budget includes every audit and native posthoc call.
    """
    _problem(problem)
    p = parse_parameters(candidate['parameters'])
    require(candidate['parameter_sha256'] == fingerprint(candidate['parameters']) and
            candidate['model_fingerprint'] == model_identity()['model_sha256'] and
            candidate['problem_sha256'] == problem['problem_sha256'], 'source candidate identity mismatch')
    raw = candidate['formal_M1_result']; formal = MappingResult(**(raw | {'status': Status(raw['status'])}))
    require(candidate['judgment'] == judge(problem, candidate['parameters'], formal) and
            candidate['judgment']['m1_feasibility'] == 'FEASIBLE' and
            check_candidate(problem, candidate['parameters'])['status'] == 'NECESSARY_CONDITIONS_SATISFIED',
            'source candidate must pass original formal M1/domain')
    require(isinstance(experiment_id, str) and bool(experiment_id), 'independent experiment_id required')
    for key, value, lo, hi in [('sample_budget', sample_budget, 1, 256), ('m1_budget', m1_budget, 1, 256),
                               ('m2_budget', m2_budget, 0, 4)]:
        require(type(value) is int and lo <= value <= hi, key+': bounded integer required')
    require(m1_budget > 2*m2_budget, 'reserve M1 calls for all M2 audits and posthoc measurements')
    require(0 < number(m2_timeout_s, 'm2_timeout_s') <= 3600, 'bounded M2 timeout required')
    active = resolve_problem(revalidation_problem) if revalidation_problem is not None else deepcopy(problem)
    if revalidation_problem is not None:
        require(active['problem_id'] != problem['problem_id'] and active['specs'] == problem['specs'] and
                active['fixed_parameters'] == problem['fixed_parameters'] and active['topology'] == problem['topology'],
                'new independent Problem must preserve original SystemSpec and fixed topology')
    target = p['N']*p['f_ref']; preferred = (target-p['f0'])/p['Kvco']
    kvs = kvco_values if kvco_values is not None else [p['Kvco']*.8, p['Kvco'], p['Kvco']*1.2]
    span = p['Vctrl_max']-p['Vctrl_min']
    vs = vlock_values if vlock_values is not None else [p['Vctrl_min']+.25*span, preferred, p['Vctrl_min']+.75*span]
    require(bool(kvs) and bool(vs) and len(kvs)*len(vs) <= 4096, 'bounded nonempty discrete sample plan required')
    for v in kvs:
        require(number(v, 'Kvco sample') > 0, 'positive Kvco samples required')
    for v in vs:
        number(v, 'Vlock sample')
    for kv in kvs:
        for v in vs:
            number(target-kv*v, 'derived f0')
    kvs, vs = sorted(set(kvs)), sorted(set(vs))
    root = Path(out).resolve(); root.mkdir(parents=True, exist_ok=False)
    context = export_context(active, [], root/'context', cost={'M1_calls': 0}, scope='VCO_ACCEPTANCE_EMPTY_CONTEXT')
    ex = RegionExplorer(context, root/'executor', m1_budget=m1_budget, reserved_final_calls=m2_budget)
    archive = CandidateArchive(ex, root/'candidate_archive.jsonl')
    result = {'schema_version': 'pll-vco-acceptance-samples-1.0', 'experiment_id': experiment_id,
        'source_candidate_id': candidate['evidence_id'], 'source_candidate_sha256': candidate['parameter_sha256'],
        'source_problem_sha256': problem['problem_sha256'], 'problem': active,
        'system_spec_sha256': fingerprint(problem['specs']), 'model': model_identity(),
        'target_frequency_hz': target,
        'fixed_cp_lf': {k: candidate['parameters']['values'][k] for k in ('Icp', 'Rz', 'C1', 'C2')},
        'sampling_plan': {'kvco_hz_per_v': kvs, 'vlock_v': vs},
        'budget': {'sample_limit': sample_budget, 'M1_limit': m1_budget, 'M2_limit': m2_budget,
                   'M1_calls': 0, 'M2_calls': 0, 'samples_attempted': 0},
        'points': [], 'M1_feasible_points': [], 'M1_failed_points': [], 'M1_unknown_points': [],
        'domain_rejected_points': [], 'M2_passed_points': [], 'M2_failed_points': [], 'M2_unknown_points': [],
        'unverified_points': [], 'FULL_SYSTEMSPEC_CERTIFIED': False,
        'unverified_region': 'ALL_UNSAMPLED_POINTS; NO_CONTINUOUS_M1_OR_M2_CERTIFICATION',
        'domain_scope': 'Search bounds are user constraints; neither they nor sampling extrema are model validity boundaries'}
    evaluated = {}
    try:
        for kv in kvs:
            for v in vs:
                index = len(result['points'])
                point = {'point_id': f'VCO{index+1:04d}', 'kvco_hz_per_v': kv, 'vlock_v': v,
                    'f0_hz': target-kv*v, 'sampling_status': 'PENDING',
                    'M1_status': 'NOT_EVALUATED', 'M2_status': 'NOT_EVALUATED'}
                result['points'].append(point)
                if result['budget']['samples_attempted'] >= sample_budget or ex.counts['M1_calls'] >= m1_budget-2*m2_budget:
                    point['sampling_status'] = 'NOT_EVALUATED_BUDGET'
                    continue
                result['budget']['samples_attempted'] += 1
                overrides = {k: p[k] for k in FREE_IDS}; overrides.update(f0=point['f0_hz'], Kvco=kv)
                point['outside_original_axes'] = [k for k, x in overrides.items()
                    if not problem['parameters'][k]['min'] <= x <= problem['parameters'][k]['max']]
                point['original_search_domain_status'] = 'OUTSIDE_ORIGINAL_SEARCH_DOMAIN' if point['outside_original_axes'] else 'INSIDE_ORIGINAL_SEARCH_DOMAIN'
                try:
                    params = make_parameters(active, overrides)
                except (ValueError, KeyError, TypeError) as error:
                    point.update(sampling_status='SEARCH_DOMAIN_REJECTED', domain_reason=str(error))
                    continue
                screen = check_candidate(active, params); point['screening'] = screen
                if screen['status'] != 'NECESSARY_CONDITIONS_SATISFIED':
                    point.update(sampling_status='FORMAL_DOMAIN_OR_NECESSARY_CONDITION_REJECTED', domain_reason=screen['reason'])
                    continue
                d = envelope(ex, decision_id=point['point_id'], region_id=point['point_id'],
                    bounds={k: [0., 1.] for k in FREE_IDS}, budget=1,
                    seed=(active['exploration']['seed']+index) % 2**32, proposals=1)
                # Existing explicit measured-feedback proposal adapter; no new solver.
                ex.execute(d, candidate_stream=[params], tool_name='FEEDBACK_SEED_FRESH_M1')
                archive.sync(); row = ex.rows[-1]
                point.update(sampling_status='M1_EVALUATED', parameter_sha256=row['parameter_sha256'],
                    M1_status=row['M1_status'], M1_evidence_id=row['evidence_id'],
                    M1_feasibility=row['judgment']['m1_feasibility'], metrics=row['metrics'],
                    constraint_margins=row['judgment']['constraints'])
                if row['judgment']['m1_feasibility'] == 'FEASIBLE':
                    evaluated[point['point_id']] = next(r for r in archive.entries if r['parameter_sha256'] == row['parameter_sha256'])
        if m2_budget:
            from ..verification.continuous import execute_request, verification_request
            # Endpoints of the sampled feasible list are representatives, not certified boundaries.
            feasible = [pt for pt in result['points'] if pt['point_id'] in evaluated]
            order = feasible[:1]+feasible[-1:] if len(feasible) > 1 else feasible
            order += [pt for pt in feasible if pt not in order]
            for point in order[:m2_budget]:
                row = evaluated[point['point_id']]
                audit = ex.recheck_recommendation(row)
                if not audit.get('passed'):
                    point['M2_reason'] = 'ORIGINAL_HANDOFF_AUDIT_NOT_PASSED'
                    continue
                h = build_handoff(ex, archive, row, audit, {'termination_reason': 'VCO_ACCEPTANCE_POINT_AUDIT'}, ex.cost())
                write_new(root/(point['point_id']+'_handoff.json'), h)
                request = verification_request(h, run_id=experiment_id, observation_id=point['point_id'], timeout_s=m2_timeout_s)
                result['budget']['M2_calls'] += 1  # Failed native attempts consume budget too.
                observation = execute_request(request, root/point['point_id'])
                result['budget']['M1_calls'] += observation['cost']['posthoc_M1_calls']
                point.update(M2_status=observation['supported_metrics_status'],
                    M2_overall_status=observation['overall_status'], M2_observation=observation,
                    M2_request_sha256=request['request_sha256'], M2_evidence_scope='NATIVE_SUPPORTED_METRICS_ONLY')
    except Exception as error:
        result['failure'] = type(error).__name__+': '+str(error)
        raise
    finally:
        ex.close()
        result['budget']['M1_calls'] += ex.counts['M1_calls']
        require(result['budget']['M1_calls'] <= m1_budget and result['budget']['M2_calls'] <= m2_budget,
                'acceptance analysis budget exceeded')
        for pt in result['points']:
            pid = pt['point_id']
            if pt['sampling_status'].endswith('REJECTED'):
                result['domain_rejected_points'].append(pid)
            elif pt.get('M1_feasibility') == 'FEASIBLE':
                result['M1_feasible_points'].append(pid)
            elif pt.get('M1_feasibility') == 'INFEASIBLE':
                result['M1_failed_points'].append(pid)
            elif pt['M1_status'] != 'NOT_EVALUATED':
                result['M1_unknown_points'].append(pid)
            if pt['M2_status'] in ('PASS', 'FAIL', 'UNKNOWN'):
                result[{'PASS': 'M2_passed_points', 'FAIL': 'M2_failed_points', 'UNKNOWN': 'M2_unknown_points'}[pt['M2_status']]].append(pid)
            else:
                result['unverified_points'].append(pid)
        write_new(root/'vco_acceptance_region.json', result)
    return result
