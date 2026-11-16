"""Strategy contract and compact state for the existing real Messages policy."""
from copy import deepcopy

from ..exploration.contracts import active_m1_specs, check_candidate, number, require, screen_problem
from ..exploration.physics_region_builder import FOCI, STRATEGIES, validate_request
from ..physics_mapping.model import fingerprint
from ..region_explorer.contracts import OBJECTIVE, SCHEMA
from .candidates import material_change
from .planner_state import compact_sample, sensitivity, sensitivity_conflicts
from .region_policy import LLMRegionPolicy
from .subregion_prior import physics_relations

SCHEMA_VERSION = 'pll-physics-tool-decision-1.0'
PROMPT = '''You plan initial allocation for the current ideal continuous CPPLL.
Choose physical strategies and tool use; do not guess six independent parameter bounds or fabricate metrics.
BUILD_PHYSICS_REGION computes complete jointly legal seeds using the ORIGINAL GLOBAL DOMAIN and the original
inverse_at_shape, checks gain/tuning intersection, then constructs unverified local boxes AROUND those seeds.
This avoids excluding the necessary Icp/Kvco/Rz combination with a premature box. Construction is NOT M1 PASS.
All formal M1, Sobol, numerical differences, failed calls and final rechecks are charged by one RegionExplorer.
Return one compact JSON object, no Markdown, with schema_version="pll-physics-tool-decision-1.0",
state_sha256 (copy current state), action, reason (brief testable physical hypothesis), evidence_ids.
Actions and additional fields:
BUILD_PHYSICS_REGION: request={schema_version:"pll-physics-region-request-1.0", request_id:unique short string,
problem_sha256:copy problem.problem_sha256, model_fingerprint:copy model.model_sha256,
strategy:one of HIGH_PM_LF_SHAPE/BW_TARGETED_INVERSE/GAIN_SPLIT_EXPLORATION/VCO_TUNING_EXPLORATION/DIVERSITY_EXPLORATION,
target_bw_fraction:[lo,hi] within[0,1] of the current supported BW target interval (e.g.[0.5,0.5] is midpoint),
physics_focus:nonempty subset of LF_SHAPE/LOOP_GAIN/GAIN_SPLIT/TUNING/DIVERSITY,
tuning_preference:INTERIOR/LOW_VOLTAGE/HIGH_VOLTAGE/DIVERSE, seed_count:1..8,
region_width_policy:LOCAL/BALANCED/BROAD, budget:{construction_attempts:positive <=budget.max_build_attempts,
m1_calls:positive <=budget.max_this_decision_M1_calls and >=seed_count}, evidence_ids:valid IDs}.
Strategies are general preferences, not case-specific recipes. Select actual strategy/targets/diversity/width/budget yourself.
HIGH_PM uses high capacitor-ratio shapes; BW_TARGETED jointly inverts BW; GAIN_SPLIT varies Icp/Kvco at fixed product;
VCO_TUNING varies operating points at compatible gain; DIVERSITY rejects neighborhoods already sampled.
Builder attempts are hard limited even if no M1 is used. Failure is a strategy result, never proof of global infeasibility.
OPTIMIZE_LOCAL: region_id (an available constructed region), seed_ids (nonempty formal_M1_seed_ids from that region),
active_variables (nonempty subset of Icp,Rz,C1,C2,f0,Kvco), m1_budget <=budget.max_this_decision_M1_calls.
Use the tool's ACTUAL box; you cannot silently replace it. SLSQP cost depends on active dimension; use supplied cost models.
PROBE_REGION: region_id (available constructed region), m1_budget>=1, sample_count (1..128).
MEASURE_LOCAL_SENSITIVITY: region_id, seed_id (formal seed in that region), m1_budget (allow up to12 calls).
Uses the existing Stage7 finite-difference stencil with actual M1 charges. Partial stencils remain UNKNOWN.
STOP: stop_basis=SPEC_SATISFIED/BUDGET/STALLED. Cite actual best_known for SPEC_SATISFIED, actual low remaining budget
for BUDGET, or measured stalled_rounds for STALLED. STOP does not certify pending metrics or mean optimizer convergence.
REVERIFY: no additional fields beyond the common decision fields. Only available when external_feedback has a
current UNKNOWN supported measurement or a failed execution; cite that exact EXT evidence and explain why
repeating the unchanged protocol can resolve uncertainty. The outer controller owns the actual M2 budget/run.
Initial action must BUILD_PHYSICS_REGION, except an input feedback seed freshly rechecked by this run may be optimized directly.
After construction inspect actual formal seed outcomes. When promising,
OPTIMIZE_LOCAL with enough calls for meaningful updates; further calls receive actual observations. You can change
physical strategy if no seed was built, choose an already evaluated alternative seed/region or stop honestly.
This search tool does not itself execute M2. When invoked by Stage9, external_feedback contains the outer
controller's real native M2 observations and evidence links. Read measurements, failed_constraints,
remaining_budgets and verification_history before choosing a physical strategy. M1 feasibility alone cannot
repair M2 FAIL. For BW mismatch use the measured diagnostic offset to choose a different target_bw_fraction;
this is a local hypothesis, not a global correction theorem. For capture/lock-time failures explore f0,
Kvco and tuning preference as well as LF/gain; f0 is flat in M1, so M1 SLSQP cannot optimize lock time directly.
For UNKNOWN do not infer physical FAIL: a distinct candidate may be explored, or STOP with a valid basis.
Actual supported-M2 success is decided only by the outer verifier; never declare full SystemSpec PASS.
External feedback, when present, has explicit model/protocol provenance,
not verified M2 PASS. It may motivate a new strategy or reactivate f0 in optimization, never change hard domain/spec.
Physics boundaries: q=1+C2/C1 sets a PM CEILING, not actual PM; Icp*Kvco sets loop gain coupled with LF;
Vreq=(N*fref-f0)/Kvco must be interior. With Kvco2=0, f0 has NO direct BW/PM sensitivity. It may matter to future
dynamic M2 capture but never claim f0 alone improves current M1 bandwidth. Local sensitivities apply only at their
bound operating point. Unmeasured boxes are not certified feasible. If validation_feedback is supplied repair that
specific error; a rejected action never executed. Do not add unsupported keys or write long prose.
JSON nesting example ONLY (replace strategy/options/count/budgets/evidence based on current state):
{"schema_version":"pll-physics-tool-decision-1.0","state_sha256":"COPY_STATE_HASH","action":"BUILD_PHYSICS_REGION",
"reason":"YOUR_PHYSICAL_HYPOTHESIS","evidence_ids":["COPY_ALLOWED_ID"],
"request":{"schema_version":"pll-physics-region-request-1.0","request_id":"UNIQUE_ID",
"problem_sha256":"COPY_PROBLEM_HASH","model_fingerprint":"COPY_MODEL_HASH","strategy":"BW_TARGETED_INVERSE",
"target_bw_fraction":[0.5,0.5],"physics_focus":["LOOP_GAIN"],"tuning_preference":"INTERIOR",
"seed_count":1,"region_width_policy":"BALANCED","budget":{"construction_attempts":1,"m1_calls":1},
"evidence_ids":["COPY_ALLOWED_ID"]}}
IMPORTANT: request.evidence_ids is a SIBLING of request.budget. The budget object has EXACTLY TWO integer keys:
construction_attempts and m1_calls. Never put evidence_ids inside budget. The validator will not relocate fields.
Read actual metrics against the numeric Spec limits. A normalized BW margin of 1 does NOT mean BW is at its bound.
For OPTIMIZE_LOCAL assign at least budget.SLSQP_cost_models_by_active_dimension[d].minimum_action_budget
when available; a smaller allocation may be safely skipped or only allow an incomplete stencil.'''


def validate_config(raw):
    required = {'schema_version', 'policy', 'total_m1_budget', 'initial_m1_budget', 'initial_sobol_samples',
        'max_decisions', 'max_llm_calls', 'validation_retries', 'max_round_m1', 'construction_attempt_budget',
        'max_build_attempts', 'seed', 'slsqp'}
    require(isinstance(raw, dict) and set(raw) == required and raw['schema_version'] == 'pll-initial-allocation-1.0',
            'complete initial allocation configuration required')
    c = deepcopy(raw)
    require(c['policy'] in ('LLM_PHYSICS_TOOL', 'DETERMINISTIC_PHYSICS_TOOL'), 'unsupported integrated policy')
    for k in required-{'schema_version', 'policy', 'slsqp'}:
        require(type(c[k]) is int and c[k] >= 0, k+': nonnegative integer required')
    require(1 <= c['max_decisions'] <= 10 and c['max_decisions'] <= c['max_llm_calls'] <= 20 and c['validation_retries'] <= 2,
            'bounded decisions/calls/retries required')
    require(3 <= c['total_m1_budget'] and c['initial_m1_budget'] < c['total_m1_budget']-1 and
            2 <= c['max_round_m1'] <= c['total_m1_budget'], 'M1/calibration/final reserve budget conflict')
    require(1 <= c['initial_m1_budget'] <= 128 and 1 <= c['initial_sobol_samples'] <= 4096 and
            1 <= c['max_build_attempts'] <= 64 and c['construction_attempt_budget'] >= c['max_build_attempts'] and
            c['construction_attempt_budget'] <= 1024 and c['seed']+c['max_decisions'] < 2**32, 'bounded construction/seed config required')
    s = c['slsqp']
    require(isinstance(s, dict) and set(s) == {'maxiter', 'finite_difference_step'} and
            type(s['maxiter']) is int and 1 <= s['maxiter'] <= 200 and
            0 < number(s['finite_difference_step'], 'eps') <= .01, 'SLSQP settings required')
    return c


def validate_feedback(raw, problem, model_fingerprint):
    """Future Stage9 input only: never updates M1 archive or certifies M2."""
    if raw is None:
        return None
    require(isinstance(raw, dict) and set(raw) == {'schema_version', 'problem_sha256', 'model_fingerprint',
        'observations', 'preferred_physics_focus', 'historical_failure_ids'} and raw['schema_version'] == 'pll-search-feedback-1.0',
        'versioned external feedback required')
    require(raw['problem_sha256'] == problem['problem_sha256'] and raw['model_fingerprint'] == model_fingerprint,
            'external feedback problem/model mismatch')
    require(isinstance(raw['observations'], list) and len(raw['observations']) <= 32, 'bounded external observations required')
    for o in raw['observations']:
        required = {'evidence_id', 'candidate_sha256', 'model_level', 'protocol',
            'measurements', 'failed_constraints', 'm1_m2_deviation'}
        require(isinstance(o, dict) and required <= set(o) <= required | {'parameters'},
                'explicit feedback candidate/protocol/deviation required')
        require(isinstance(o['evidence_id'], str) and o['evidence_id'].startswith('EXT:') and
                isinstance(o['candidate_sha256'], str) and len(o['candidate_sha256']) == 64 and
                o['model_level'] in ('M1', 'M2') and isinstance(o['protocol'], str) and bool(o['protocol']), 'feedback provenance required')
        require(isinstance(o['failed_constraints'], list) and all(isinstance(s, str) for s in o['failed_constraints']) and
                isinstance(o['measurements'], dict) and isinstance(o['m1_m2_deviation'], dict), 'structured external metrics required')
        if 'parameters' in o:
            require(fingerprint(o['parameters']) == o['candidate_sha256'] and
                    check_candidate(problem, o['parameters'])['status'] == 'NECESSARY_CONDITIONS_SATISFIED',
                    'feedback parameters must match candidate hash and original domain; fresh M1 required before seed use')
    require(len({o['evidence_id'] for o in raw['observations']}) == len(raw['observations']), 'duplicate external evidence')
    require(isinstance(raw['preferred_physics_focus'], list) and all(f in FOCI for f in raw['preferred_physics_focus']) and
            isinstance(raw['historical_failure_ids'], list) and all(isinstance(s, str) for s in raw['historical_failure_ids']), 'feedback directions/IDs required')
    fingerprint(raw)  # Reject NaN/Inf; no evaluation or trust upgrade.
    return deepcopy(raw) | {'scope': 'CALLER_SUPPLIED_EXTERNAL_FEEDBACK_NOT_VERIFIED_BY_THIS_RUN'}


def build_state(loop, round_number, correction):
    ex = loop.explorer; loop.archive.sync()
    best = loop.archive.best(); summary = loop.archive.summary()
    ordered = sorted(loop.archive.entries, key=lambda r: (r['judgment']['m1_feasibility'] != 'FEASIBLE',
                       -r['judgment']['minimum_normalized_margin'], r['evidence_id']))
    sample_rows = ordered[:12]
    recent = ex.rows[-8:]
    relations = physics_relations(ex.context['model'])
    derivative_context = deepcopy(ex.context)
    for h in loop.history:
        for o in h['observations']:
            if o.get('sensitivity'):
                derivative_context['sensitivity']['representatives'].extend(o['sensitivity']['representatives'])
    derivatives = sensitivity(derivative_context, ex.evidence)
    for derivative in derivatives:
        ex.evidence[derivative['evidence_id']] = derivative
    region_summaries = []
    for rid, region in loop.tool_regions.items():
        seeds = [ex.evidence[i] for i in region['formal_seed_ids'] if ex.evidence[i]['M1_status'] == 'OK']
        region_summaries.append({'region_id': rid, 'source': 'TOOL_COMPUTED_AROUND_JOINT_SEED',
            'strategy': region['strategy'], 'normalized_bounds': region['normalized_bounds'],
            'formal_M1_seed_ids': [s['evidence_id'] for s in seeds],
            'seeds': [compact_sample(s, ex.problem) for s in seeds], 'whole_region_M1_certified': False})
    stalled = 0
    for record in reversed(loop.history):
        if record['progress']['material']:
            break
        stalled += 1
    available = ex.cost()['search_available_M1_calls']
    from ..region_explorer.explorer import slsqp_cost_model
    p = {'schema_version': 'pll-physics-tool-planner-state-1.0', 'round': round_number,
        'problem': deepcopy(ex.problem), 'model': deepcopy(ex.context['model']), 'relations': relations,
        'necessary_conditions': screen_problem(ex.problem), 'best_known': compact_sample(best, ex.problem) if best else None,
        'best_calibration': compact_sample(summary['best_calibration'], ex.problem) if summary['best_calibration'] else None,
        'best_new': compact_sample(summary['best_new'], ex.problem) if summary['best_new'] else None,
        'improvement_over_calibration': summary['improvement_over_calibration'],
        'tightest_constraint': min((c for c in best['judgment']['constraints'] if c['enabled'] and c['normalized_margin'] is not None),
                                  key=lambda c: c['normalized_margin'], default=None) if best else None,
        'samples': [compact_sample(s, ex.problem) for s in sample_rows],
        'recent_outcomes': [compact_sample(s, ex.problem) | {'reason': s.get('reason')} for s in recent],
        'available_tool_regions': region_summaries,
        'local_sensitivity': derivatives,
        'sensitivity_conflicts': sensitivity_conflicts(derivatives),
        'sensitivity_status': 'ACTUAL_LOCAL_STENCILS' if derivatives else 'NOT_MEASURED_NO_DERIVATIVE_CLAIM',
        'budget': {'total_M1_hard_limit': loop.integrated_config['total_m1_budget'],
            'initial_charged_M1': loop.initial_calls, 'session_new_M1': ex.counts['M1_calls'],
            'search_available_M1': available, 'final_recheck_reserved_M1': ex.reserved_final_calls,
            'max_this_decision_M1_calls': min(loop.config['max_round_m1'], available),
            'construction_attempts_used': loop.construction_attempts,
            'construction_attempts_remaining': loop.integrated_config['construction_attempt_budget']-loop.construction_attempts,
            'max_build_attempts': min(loop.integrated_config['max_build_attempts'],
                loop.integrated_config['construction_attempt_budget']-loop.construction_attempts),
            'calls_remaining': loop.config['max_llm_calls']-loop.calls,
            'SLSQP_cost_models_by_active_dimension': {str(i): slsqp_cost_model(i) for i in range(1, 7)}},
        'history': deepcopy(loop.compact_history), 'stalled_rounds': stalled,
        'external_feedback': deepcopy(loop.external_feedback), 'validation_feedback': correction,
        'feedback_seed_rechecks': deepcopy(loop.feedback_seed_rechecks),
        'capability_boundary': deepcopy(ex.context['capability_boundary']),
        'physics_boundaries': ['f0 does not directly affect ideal M1 BW/PM; dynamic capture effects not evaluated',
            'local derivatives are working-point dependent; no global sign theorem',
            'tool regions and sampling coverage never certify a continuous feasible set'],
        'M2_status': 'NOT_EVALUATED'}
    ids = {r['evidence_id'] for r in relations} | {s['evidence_id'] for s in sample_rows+recent}
    ids |= {o['observation_id'] for h in loop.history for o in h['observations']}
    ids |= set(loop.tool_evidence_ids)
    ids |= {i for r in region_summaries for i in r['formal_M1_seed_ids']}
    ids |= {s['evidence_id'] for s in derivatives}
    if loop.external_feedback:
        ids |= {o['evidence_id'] for o in loop.external_feedback['observations']}
    if best:ids.add(best['evidence_id'])
    p['allowed_evidence_ids'] = sorted(ids)
    p['state_sha256'] = fingerprint(p)
    return p


def adapt(raw, loop, state, round_number):
    common = {'schema_version', 'state_sha256', 'action', 'reason', 'evidence_ids'}
    require(isinstance(raw, dict) and common <= set(raw) and raw['schema_version'] == SCHEMA_VERSION and
            raw['state_sha256'] == state['state_sha256'], 'current versioned tool decision required')
    action = raw['action']
    require(action in ('BUILD_PHYSICS_REGION', 'OPTIMIZE_LOCAL', 'PROBE_REGION', 'MEASURE_LOCAL_SENSITIVITY', 'STOP', 'REVERIFY'), 'unknown action')
    require(isinstance(raw['reason'], str) and 0 < len(raw['reason']) <= 3000 and
            isinstance(raw['evidence_ids'], list) and bool(raw['evidence_ids']) and
            all(isinstance(i, str) and i in state['allowed_evidence_ids'] for i in raw['evidence_ids']), 'valid reason/evidence required')
    require(loop.history or action == 'BUILD_PHYSICS_REGION' or
            (loop.feedback_seed_rechecks and action in ('OPTIMIZE_LOCAL', 'PROBE_REGION', 'MEASURE_LOCAL_SENSITIVITY', 'STOP', 'REVERIFY')),
            'first integrated decision must build physics region or consume an explicitly rechecked feedback seed')
    effective = deepcopy({k: v for k, v in raw.items() if k not in ('state_sha256', 'reason', 'evidence_ids')})
    if isinstance(effective.get('request'), dict):
        effective['request'] = {k: v for k, v in effective['request'].items() if k not in ('request_id', 'evidence_ids')}
    sig = fingerprint(effective)
    require(sig not in loop.tool_signatures, 'repeated effective physics-tool action; switch strategy or STOP')
    if action == 'REVERIFY':
        require(set(raw)==common,'REVERIFY accepts only common fields')
        observations=(loop.external_feedback or {}).get('observations',[])
        cited=[o for o in observations if o['evidence_id'] in raw['evidence_ids'] and
               o['measurements'].get('schema_version')=='pll-m2-feedback-summary-1.0' and
               (o['measurements'].get('supported_metrics_status')=='UNKNOWN' or
                o['measurements'].get('execution_status')!='COMPLETED')]
        require(bool(cited),'REVERIFY requires cited unresolved actual M2 feedback, not a known physical FAIL')
        loop.reverification_request=deepcopy(raw)
        d={'schema_version':SCHEMA,'context_sha256':loop.explorer.context['context_sha256'],
            'decision_id':'PT:'+str(round_number)+':REVERIFY','action':'STOP',
            'region':{'region_id':'TOOL:REVERIFY','parent_region_id':None},
            'normalized_bounds':{k:[0.,1.] for k in loop.explorer.problem['parameters']},
            'active_variables':[],'seed_ids':[],'m1_budget':0,'search_method':'NONE','settings':{},
            'objective':OBJECTIVE,'reason':raw['reason'],
            'evidence_ids':[],'random_seed':loop.config['seed']+round_number}
        loop.explorer.validate(d)
    elif action == 'BUILD_PHYSICS_REGION':
        require(set(raw) == common | {'request'}, 'BUILD needs request only, no guessed box')
        request = validate_request(raw['request'], loop.explorer.problem, loop.explorer.context['model']['model_sha256'],
            set(state['allowed_evidence_ids']), attempts_left=state['budget']['max_build_attempts'],
            m1_left=state['budget']['max_this_decision_M1_calls'])
        require(request['request_id'] not in loop.build_request_ids, 'request_id already used')
        d = deepcopy(raw) | {'request': request}
    else:
        stop = action == 'STOP'
        extra = {'stop_basis'} if stop else {'region_id', 'seed_ids', 'active_variables', 'm1_budget'} if action == 'OPTIMIZE_LOCAL' else (
            {'region_id', 'seed_id', 'm1_budget'} if action == 'MEASURE_LOCAL_SENSITIVITY' else {'region_id', 'm1_budget', 'sample_count'})
        require(set(raw) == common | extra, 'unexpected tool action fields')
        rid = raw.get('region_id')
        if not stop:require(isinstance(rid, str) and rid in loop.tool_regions, 'unknown tool-computed region')
        if stop:
            basis = raw['stop_basis']; best = loop.archive.best(feasible_only=True)
            require(basis in ('SPEC_SATISFIED', 'BUDGET', 'STALLED'), 'explicit stop basis required')
            if basis == 'SPEC_SATISFIED':require(best is not None and best['evidence_id'] in raw['evidence_ids'], 'STOP must cite actual feasible best')
            if basis == 'BUDGET':require(state['budget']['search_available_M1'] < 3 or state['budget']['construction_attempts_remaining'] == 0, 'budget stop contradicts available budget')
            if basis == 'STALLED':require(state['stalled_rounds'] >= 2, 'stall needs two measured unimproved rounds')
            bounds = {k: [0., 1.] for k in loop.explorer.problem['parameters']}
            d = {'action': 'STOP', 'region': {'region_id': 'TOOL:STOP', 'parent_region_id': None},
                 'normalized_bounds': bounds, 'active_variables': [], 'seed_ids': [], 'm1_budget': 0, 'search_method': 'NONE', 'settings': {}}
        else:
            region = loop.tool_regions[rid]
            require(type(raw['m1_budget']) is int and 1 <= raw['m1_budget'] <= state['budget']['max_this_decision_M1_calls'], 'round/session M1 budget exceeded')
            optimize = action == 'OPTIMIZE_LOCAL'
            measure = action == 'MEASURE_LOCAL_SENSITIVITY'
            if measure:
                require(raw['seed_id'] in region['formal_seed_ids'], 'sensitivity center must be an actual formal seed in this region')
            if optimize:
                require(isinstance(raw['seed_ids'], list) and bool(raw['seed_ids']) and
                        all(s in region['formal_seed_ids'] for s in raw['seed_ids']), 'only formal seeds in actual tool region allowed')
            d = {'action': 'OPTIMIZE' if optimize else 'PROBE',
                 'region': {'region_id': rid, 'parent_region_id': None}, 'normalized_bounds': region['normalized_bounds'],
                 'active_variables': raw['active_variables'] if optimize else list(loop.explorer.problem['parameters']),
                 'seed_ids': raw['seed_ids'] if optimize else [], 'm1_budget': raw['m1_budget'],
                 'search_method': 'SLSQP' if optimize else 'SOBOL',
                 'settings': deepcopy(loop.config['slsqp']) if optimize else {'sample_count': 12 if measure else raw['sample_count']}}
        d.update(schema_version=SCHEMA, context_sha256=loop.explorer.context['context_sha256'],
                 decision_id='PT:'+str(round_number)+':'+action, objective=OBJECTIVE, reason=raw['reason'],
                 evidence_ids=[i for i in raw['evidence_ids'] if i in loop.explorer.evidence],
                 random_seed=loop.config['seed']+round_number)
        loop.explorer.validate(d)
        if action == 'MEASURE_LOCAL_SENSITIVITY':
            loop.sensitivity_actions[d['decision_id']] = raw['seed_id']
    loop.tool_signatures.add(sig)
    return d


class DeterministicToolPolicy:
    """Explicit deterministic baseline; never a real LLM claim."""
    calls = ()

    def decide(self, state, directory):
        common = {'schema_version': SCHEMA_VERSION, 'state_sha256': state['state_sha256'],
                  'reason': 'Predeclared deterministic global physical inverse and local maximin optimization.',
                  'evidence_ids': ['REL:shape', 'REL:inverse_gain']}
        regions = [r for r in state['available_tool_regions'] if r['formal_M1_seed_ids']]
        if not regions:
            return common | {'action': 'BUILD_PHYSICS_REGION', 'request': {
                'schema_version': 'pll-physics-region-request-1.0', 'request_id': 'DET:'+str(state['round']),
                'problem_sha256': state['problem']['problem_sha256'], 'model_fingerprint': state['model']['model_sha256'],
                'strategy': 'HIGH_PM_LF_SHAPE', 'target_bw_fraction': [.5, .5], 'physics_focus': ['LF_SHAPE', 'GAIN_SPLIT'],
                'tuning_preference': 'INTERIOR', 'seed_count': 3, 'region_width_policy': 'BALANCED',
                'budget': {'construction_attempts': state['budget']['max_build_attempts'], 'm1_calls': min(3, state['budget']['max_this_decision_M1_calls'])},
                'evidence_ids': ['REL:shape', 'REL:inverse_gain']}}
        if not any(h['action'] == 'OPTIMIZE' for h in state['history']):
            region = max(regions, key=lambda r: max(s['worst_normalized_margin'] for s in r['seeds']))
            seed = max(region['seeds'], key=lambda s: s['worst_normalized_margin'])
            return common | {'action': 'OPTIMIZE_LOCAL', 'region_id': region['region_id'], 'seed_ids': [seed['evidence_id']],
                             'active_variables': list(state['problem']['parameters']), 'm1_budget': state['budget']['max_this_decision_M1_calls']}
        best = state['best_known']
        return common | {'action': 'STOP', 'stop_basis': 'SPEC_SATISFIED' if best and best['m1_feasibility'] == 'FEASIBLE' else 'STALLED',
                         'evidence_ids': [best['evidence_id']] if best else ['REL:shape']}


def make_policy(config, provider_config):
    return (LLMRegionPolicy(provider_config or {}, prompt=PROMPT) if config['policy'] == 'LLM_PHYSICS_TOOL'
            else DeterministicToolPolicy())
