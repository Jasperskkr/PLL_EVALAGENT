"""Bounded conditional tool observations; prediction evidence has no verdict authority."""
from copy import deepcopy

from ..exploration.physics_region_builder import available_physical_objectives, OBJECTIVE_REQUEST_SCHEMA
from ..physics_mapping.model import fingerprint


def conditional_observation(explorer, rows):
    physics = getattr(explorer, 'conditional_physics', None)
    if physics is None:
        return None
    options = physics.options
    binding = fingerprint(options)
    candidates, seen = [], set()
    for row in rows:
        key = row['parameter_sha256']
        if key in seen:
            continue
        seen.add(key)
        info = physics.describe(row['parameters'])
        item = {'schema_version': 'pll-conditional-observation-1.0',
            'source_evidence_id': row['evidence_id'], 'candidate_sha256': key,
            'problem_sha256': explorer.problem['problem_sha256'],
            'model_fingerprint': explorer.context['model']['model_sha256'],
            'tool_options_sha256': binding,
            'source_M1_status': row['M1_status'],
            'scope': 'CONDITIONAL_PREDICTION_NOT_FORMAL_M1_OR_M2',
            'formal_M2_status': 'UNKNOWN', 'capture_certified': False}
        if options['noise_allocation_enabled']:
            item['noise'] = {k: deepcopy(info.get(k)) for k in (
                'predicted_jitter_s', 'dominant_noise_source', 'noise_source_fractions',
                'jitter_margin_s', 'conditional_noise_status', 'noise_profile_identity',
                'prediction_validity', 'applicability', 'reason')}
            item['noise']['jitter_limit_s'] = physics.limit
        if 'analytic_features' in info:
            features = info['analytic_features']
            item['dynamics'] = {k: deepcopy(features.get(k)) for k in (
                'omega_n_rad_s', 'zeta_approx', 'initial_frequency_error_Hz',
                'tuning_rail_margin_V', 'slip_risk', 'predicted_lock_time_s', 'prediction_validity')}
        digest = fingerprint(item)
        item.update(evidence_id='CPRED:'+digest, prediction_sha256=digest)
        explorer.evidence[item['evidence_id']] = deepcopy(item)
        candidates.append(item)
        if len(candidates) >= 24:
            break
    allowed = available_physical_objectives(options)
    return {'schema_version': 'pll-conditional-tool-capabilities-1.0',
        'tool_options_sha256': binding, 'allowed_physical_objectives': allowed,
        'request_schema_versions': ['pll-physics-region-request-1.0']+([OBJECTIVE_REQUEST_SCHEMA] if allowed else []),
        'initial_control_V': .15 if options['initial_state_aware_enabled'] else None,
        'delta_offsets_V': deepcopy(options['delta_offsets_V']) if options['initial_state_aware_enabled'] else None,
        'jitter_limit_s': physics.limit if options['noise_allocation_enabled'] else None,
        'candidates': candidates,
        'authority': 'Planner chooses enabled objectives, regions and bounded tool budgets; Runner validates and executes',
        'limitations': ['Noise is conditional on the bound research profile, integration band and linear locked model',
            'Damping is approximate; slip risk and FAST_LOCK are heuristics, not a capture guarantee',
            'Missing predictions stay UNKNOWN; no prediction supplies a formal M2 PASS',
            'External provenance-bound feedback remains advisory and requires fresh checks by the existing Runner']}
