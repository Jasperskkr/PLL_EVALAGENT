"""VCO sizing preferences and measured feedback, separate from formal verdicts."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from ..agent.handoff import SCHEMA as NOMINAL_SCHEMA, validate_handoff
from ..allocation.core import write_new
from ..exploration.contracts import check_candidate, judge, number, require
from ..exploration.engine import model_identity
from ..physics_mapping.model import MappingResult, Status, fingerprint, parse_parameters

GUIDANCE_SCHEMA = 'pll-vco-sizing-guidance-1.0'
FEEDBACK_SCHEMA = 'pll-vco-physical-feedback-1.0'
UNITS = {'target_frequency_hz': 'Hz', 'preferred_vlock_v': 'V',
         'preferred_kvco_hz_per_v': 'Hz/V', 'nominal_f0_hz': 'Hz',
         'vlock_v': 'V', 'kvco_local_hz_per_v': 'Hz/V', 'f0_local_hz': 'Hz',
         'frequency_tolerance_hz': 'Hz'}
HARD_UNITS = {'vlock_v': 'V', 'kvco_local_hz_per_v': 'Hz/V', 'f0_local_hz': 'Hz'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def interval(item, unit, label, *, allow_point=False):
    require(isinstance(item, dict) and item.get('unit') == unit, label+': canonical unit required')
    lo, hi = (number(item[k], label+'.'+k) for k in ('min', 'max'))
    require(lo <= hi if allow_point else lo < hi, label+': ordered interval required')
    return lo, hi


def evidence(item, label):
    require(isinstance(item, list) and bool(item) and all(isinstance(x, dict) and
            isinstance(x.get('uri'), str) and x['uri'] and isinstance(x.get('sha256'), str) and
            len(x['sha256']) == 64 and all(c in '0123456789abcdef' for c in x['sha256']) for x in item),
            label+': evidence URI and SHA256 required')


def _problem(problem):
    require(problem['problem_sha256'] == fingerprint({k: v for k, v in problem.items()
            if k != 'problem_sha256'}), 'problem fingerprint mismatch')


def validate_source(handoff):
    """Accept native multi-point delivery or the original signed M1-only handoff.

    Check recorded evidence without rerunning physics or loading a native DLL.
    Hashes bind supplied records; they are not cryptographic authentication.
    """
    if handoff.get('schema_version') == NOMINAL_SCHEMA:
        validate_handoff(handoff)
        return handoff['problem'], [handoff['recommended_nominal']]
    require(handoff.get('schema_version') == 'pll-sizing-targets-1.0', 'unsupported source handoff')
    problem = handoff['problem']; _problem(problem)
    require(handoff['evidence_scope'] == 'NATIVE_M2_SUPPORTED_METRICS_ONLY' and
            handoff['FULL_SYSTEMSPEC_CERTIFIED'] is False and
            handoff['candidate_count'] == len(handoff['candidates']), 'invalid multi-candidate delivery')
    seen = set()
    from ..verification.continuous import judge_measurements
    from ..verification.experiments import protocol
    for row in handoff['candidates']:
        key = fingerprint(row['parameters'])
        require(row['parameter_sha256'] == key and key not in seen, 'candidate hash/duplicate mismatch')
        seen.add(key)
        require(row['model_fingerprint'] == model_identity()['model_sha256'] and
                row['problem_sha256'] == problem['problem_sha256'], 'candidate model/problem mismatch')
        require(check_candidate(problem, row['parameters'])['status'] == 'NECESSARY_CONDITIONS_SATISFIED',
                'source candidate outside original domain or necessary conditions')
        raw = row['formal_M1_result']; result = MappingResult(**(raw | {'status': Status(raw['status'])}))
        require(result.status == Status.OK and row['metrics'] == result.metrics and
                row['judgment'] == judge(problem, row['parameters'], result) and
                row['judgment']['m1_feasibility'] == 'FEASIBLE', 'source formal M1 evidence mismatch')
        require(row['M2_evidence_scope'] == 'NATIVE' and row['M2_supported_status'] == 'PASS' and
                bool(row['M2_observations']), 'native M2 evidence required for multi-point delivery')
        record = row['M2_observations'][-1]; request, measured = record['request'], record['observation']
        parameters = validate_handoff(request['handoff'])
        require(parameters == row['parameters'] == request['parameters'] and
                request['handoff']['problem'] == problem and request['candidate_sha256'] == key and
                request['problem_sha256'] == problem['problem_sha256'] and
                request['specs'] == problem['specs'] and
                request['candidate_id'] == row['evidence_id'] and request['protocol'] == protocol() and
                request['request_sha256'] == fingerprint({k: v for k, v in request.items()
                                                         if k != 'request_sha256'}) and
                request['protocol_sha256'] == fingerprint(request['protocol']), 'M2 request binding mismatch')
        require(all(measured[k] == request[k] for k in
                    ('candidate_sha256', 'request_sha256', 'problem_sha256', 'protocol_sha256')) and
                measured['M2_model_fingerprint'] == fingerprint(request['M2_model']) and
                row['M2_status'] == measured['overall_status'] and
                measured['cost']['completed_native_runs'] > 0 and
                measured['evidence_id'].startswith('M2:'), 'native observation binding mismatch')
        judgment = judge_measurements(request, measured['capture'], measured['frequency_response_comparison'])
        require(judgment['supported_metrics_status'] == 'PASS' and all(measured[k] == judgment[k] for k in
                ('supported_metrics_status', 'overall_status', 'constraints', 'metrics', 'FULL_SYSTEMSPEC_CERTIFIED')),
                'recorded native verdict mismatch')
    return problem, handoff['candidates']


def _options(options):
    require(options is None or isinstance(options, dict), 'independent design policy must be a JSON object')
    opts = deepcopy(options or {})
    require(set(opts) <= {'hard_constraints', 'required_tuning_margin', 'cp_compliance', 'target_confirmation'}, 'unknown VCO option')
    hard = opts.setdefault('hard_constraints', {})
    require(isinstance(hard, dict) and set(hard) <= set(HARD_UNITS), 'unsupported block hard constraint')
    for name, bounds in hard.items():
        interval(bounds, HARD_UNITS[name], name, allow_point=True)
    margin = opts.setdefault('required_tuning_margin', {'voltage_v': None, 'frequency_hz': None})
    require(set(margin) == {'voltage_v', 'frequency_hz'}, 'explicit voltage/frequency margin required')
    for k, v in margin.items():
        if v is not None:
            require(number(v, k) >= 0, 'negative tuning margin')
    cp = opts.setdefault('cp_compliance', None)
    if cp is not None:
        interval(cp, 'V', 'CP compliance'); evidence(cp.get('evidence'), 'CP compliance')
        require(isinstance(cp.get('conditions'), dict) and bool(cp['conditions']), 'CP measurement conditions required')
        require(isinstance(cp.get('source_candidate_sha256'), str) and len(cp['source_candidate_sha256']) == 64,
                'CP compliance must bind its source candidate (including Icp)')
    confirmation = opts.setdefault('target_confirmation', {'max_frequency_error_hz': None})
    require(isinstance(confirmation, dict) and set(confirmation) == {'max_frequency_error_hz'},
            'target_confirmation: max_frequency_error_hz required')
    if confirmation['max_frequency_error_hz'] is not None:
        require(number(confirmation['max_frequency_error_hz'], 'max_frequency_error_hz') > 0,
                'positive trusted frequency error limit required')
    return opts


def build_guidance(handoff, *, source_uri, options=None):
    problem, rows = validate_source(handoff); opts = _options(options)
    source_hash = handoff.get('handoff_sha256', fingerprint(handoff))
    cp = opts['cp_compliance']
    require(cp is None or cp['source_candidate_sha256'] in {r['parameter_sha256'] for r in rows},
            'CP compliance source candidate is not in this handoff')
    entries = []
    for row in rows:
        p = parse_parameters(row['parameters']); target = p['N']*p['f_ref']
        entries.append({'source_candidate_id': row['evidence_id'],
            'source_candidate_sha256': row['parameter_sha256'], 'source_handoff_sha256': source_hash,
            'native_verification_handoff_sha256': (row['M2_observations'][-1]['request']['handoff']['handoff_sha256']
                if row.get('M2_observations') else handoff.get('handoff_sha256')),
            'model_fingerprint': row['model_fingerprint'], 'problem_sha256': problem['problem_sha256'],
            'nominal_block_spec': deepcopy(row['parameters']),
            'cp_lf_parameters': {k: deepcopy(row['parameters']['values'][k]) for k in ('Icp', 'Rz', 'C1', 'C2')},
            'target_frequency_hz': target, 'preferred_vlock_v': (target-p['f0'])/p['Kvco'],
            'preferred_kvco_hz_per_v': p['Kvco'], 'nominal_f0_hz': p['f0'],
            'units': deepcopy(UNITS),
            'control_voltage_limits': {'min': p['Vctrl_min'], 'max': p['Vctrl_max'], 'unit': 'V',
                'source': 'DECLARED_SYSTEM_MODEL', 'physically_verified': False},
            'cp_compliance': deepcopy(cp) if cp and cp['source_candidate_sha256'] == row['parameter_sha256'] else None,
            'joint_cp_vco_valid_interval_status': 'UNCONFIRMED_REQUIRES_MATCHED_PHYSICAL_EVIDENCE',
            'required_tuning_margin': deepcopy(opts['required_tuning_margin']) |
                {'units': {'voltage_v': 'V', 'frequency_hz': 'Hz'},
                 'status': 'USER_SPECIFIED' if any(v is not None for v in opts['required_tuning_margin'].values())
                           else 'UNSPECIFIED_REQUIRES_DESIGN_REQUIREMENT'},
            'hard_constraints': deepcopy(opts['hard_constraints']),
            'target_confirmation': deepcopy(opts['target_confirmation']),
            'exact_f0_match_required': False, 'exact_kvco_match_required': False,
            'hard_requirements': ['Reach target in legal control voltage range',
                'Vlock in measured common CP/VCO valid interval', 'Meet specified tuning margins',
                'Reliable startup and divider drive', 'Extract local Kvco at actual target point',
                'Revalidate actual parameters through original M1/M2 gates'],
            'preference_fields': ['preferred_vlock_v', 'preferred_kvco_hz_per_v', 'nominal_f0_hz'],
            'source_evidence_status': {'M1': 'FEASIBLE',
                'M2': row.get('M2_status', 'NOT_EVALUATED'),
                'M2_supported': row.get('M2_supported_status', 'NOT_EVALUATED')},
            'FULL_SYSTEMSPEC_CERTIFIED': False})
    return {'schema_version': GUIDANCE_SCHEMA, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'contract_revision': '1.1', 'design_policy_sha256': fingerprint(opts),
        'generator': 'pll_allocation.vco_sizing.contract', 'source_uri': str(source_uri),
        'source_handoff_sha256': source_hash,
        'source_handoff_hash_kind': 'NATIVE_SIGNED_PAYLOAD' if 'handoff_sha256' in handoff else 'CANONICAL_JSON_SHA256',
        'system_spec_identity': {'problem_id': problem['problem_id'], 'problem_sha256': problem['problem_sha256'],
                                 'system_spec_sha256': fingerprint(problem['specs']), 'specs': deepcopy(problem['specs'])},
        'candidate_count': len(entries), 'candidates': entries,
        'feedback_schema_version': FEEDBACK_SCHEMA,
        'authority': 'Sizing guidance only; formal M1/M2 retain SystemSpec verdict authority'}


def export_guidance(handoff_path, output_path=None, *, options=None):
    source = Path(handoff_path).resolve()
    out = Path(output_path).resolve() if output_path else source.with_name('vco_sizing_guidance.json')
    data = source.read_bytes()
    item = build_guidance(json.loads(data.decode('utf-8-sig')), source_uri=source, options=options)
    item['source_file_sha256'] = hashlib.sha256(data).hexdigest()
    write_new(out, item)
    return item


def validate_guidance(guidance, handoff, *, options=None, source_handoff_path=None, return_report=False):
    """Compare against caller-owned policy, never policy copied from guidance.

    With no options only the default policy is trusted. Python callers without
    source bytes get an explicit NOT_CHECKED report; CLI always supplies a path.
    Hash equality is consistency, not authentication of files or experiments.
    """
    require(isinstance(guidance.get('generated_at'), str), 'guidance generation timestamp required')
    require(datetime.fromisoformat(guidance['generated_at']).tzinfo is not None, 'timezone-aware generation time required')
    expected = build_guidance(handoff, source_uri=guidance['source_uri'], options=options)
    if 'contract_revision' not in guidance:
        # Legacy 1.0 has no policy digest or confirmation field. Its actual
        # requirements still must equal the independently supplied policy.
        expected.pop('contract_revision'); expected.pop('design_policy_sha256')
        for entry in expected['candidates']:
            entry.pop('target_confirmation')
        require(_options(options)['target_confirmation']['max_frequency_error_hz'] is None,
                'legacy guidance requires re-export for frequency confirmation policy')
    ignored = {'generated_at', 'source_file_sha256'}
    require({k: v for k, v in guidance.items() if k not in ignored} ==
            {k: v for k, v in expected.items() if k not in ignored}, 'guidance/source binding mismatch')
    report = {'policy_status': 'MATCHED_DEFAULT_POLICY' if options is None else 'MATCHED_CALLER_POLICY',
              'design_policy_sha256': fingerprint(_options(options)),
              'source_file_bytes_status': 'NOT_CHECKED_PARSED_JSON_ONLY',
              'authentication_status': 'NOT_AUTHENTICATED'}
    if source_handoff_path is not None:
        data = Path(source_handoff_path).read_bytes()
        require(guidance.get('source_file_sha256') == hashlib.sha256(data).hexdigest(),
                'source file SHA256 mismatch or missing digest')
        require(json.loads(data.decode('utf-8-sig')) == handoff, 'source file/parsed handoff mismatch')
        report.update(source_file_bytes_status='VERIFIED', source_file_sha256=hashlib.sha256(data).hexdigest())
    return report if return_report else guidance


def _cp_intersection(guidance_entry, feedback_cp, conditions):
    """Ordinary feedback can restrict comparable CP evidence, never replace it."""
    sources = []; ranges = []
    for origin, cp in (('GUIDANCE', guidance_entry['cp_compliance']), ('FEEDBACK', feedback_cp)):
        if cp is None:
            continue
        ranges.append(interval(cp, 'V', 'CP compliance'))
        evidence(cp.get('evidence'), 'CP compliance')
        require(cp.get('source_candidate_sha256') == guidance_entry['source_candidate_sha256'],
                'CP compliance candidate/Icp mismatch')
        require(cp.get('conditions') == conditions, 'CP/VCO conditions mismatch; evidence is not comparable')
        sources.append({'origin': origin, 'evidence_sha256': fingerprint(cp), 'measurement': deepcopy(cp)})
    return ((max(r[0] for r in ranges), min(r[1] for r in ranges)) if ranges else None), sources


def _root_estimate(samples, target):
    brackets = [(a, b) for a, b in zip(samples, samples[1:])
                if (a['frequency_hz']-target)*(b['frequency_hz']-target) < 0]
    estimates = [{'vlock_v': a['vctrl_v']+(target-a['frequency_hz'])*(b['vctrl_v']-a['vctrl_v'])/
                  (b['frequency_hz']-a['frequency_hz']), 'bracketing_samples': [deepcopy(a), deepcopy(b)]}
                 for a, b in brackets]
    return {'status': 'INTERPOLATED_NOT_REMEASURED' if estimates else 'UNCONFIRMED',
            'estimated_vlock_v': estimates[0]['vlock_v'] if len(estimates) == 1 else None,
            'estimates': estimates, 'scope': 'DISCRETE_BRACKETS_ONLY; NO_MEASURED_ROOT_CERTIFICATION'}


def assess_feedback(feedback, guidance, handoff, *, options=None, source_handoff_path=None):
    """Validate measured data and derive a local tangent. Never issue a MOS/SystemSpec PASS.

    Only a measured target point establishes reachability. Sparse samples and
    externally reported failure retain their stated measurement scope.
    """
    validation = validate_guidance(guidance, handoff, options=options,
                                  source_handoff_path=source_handoff_path, return_report=True)
    f = deepcopy(feedback)
    require(f.get('schema_version') == FEEDBACK_SCHEMA and f.get('units') == UNITS, 'feedback schema/units mismatch')
    matches = [g for g in guidance['candidates'] if g['source_candidate_sha256'] == f['source_candidate_sha256']]
    require(len(matches) == 1, 'unknown feedback candidate')
    g = matches[0]
    require(all(f[k] == g[k] for k in ('source_candidate_id', 'source_handoff_sha256', 'problem_sha256')) and
            f['target_frequency_hz'] == g['target_frequency_hz'], 'feedback source/target binding mismatch')
    require(isinstance(f.get('experiment_id'), str) and bool(f['experiment_id']), 'independent experiment_id required')
    mos = f['mos_design']; evidence([mos['netlist']], 'MOS netlist')
    require(isinstance(mos.get('sizes_and_biases'), dict) and bool(mos['sizes_and_biases']), 'MOS sizes/biases required')
    env = f['conditions']
    require(all(isinstance(env.get(k), str) and bool(env[k]) for k in ('pdk', 'corner')), 'PDK/corner required')
    number(env['temperature_c'], 'temperature_c'); require(number(env['supply_v'], 'supply_v') > 0, 'supply must be positive')
    evidence(f['evidence'], 'measurement')
    require(isinstance(f['measurement_method'], str) and bool(f['measurement_method']), 'measurement method required')
    require(f['validation_status'] in ('MEASURED', 'FAILED', 'INCOMPLETE') and
            isinstance(f['failure_reasons'], list) and all(isinstance(x, str) for x in f['failure_reasons']),
            'validation status/failure reasons required')
    require(f['validation_status'] != 'FAILED' or bool(f['failure_reasons']), 'failed feedback requires reason')
    for name in ('startup_status', 'divider_drive_status'):
        require(f[name] in ('PASS', 'FAIL', 'UNKNOWN'), name+': explicit status required')
    cp_range, cp_sources = _cp_intersection(g, f.get('cp_compliance'), env)
    if f['tuning_samples'] == []:
        require(f['validation_status'] in ('FAILED', 'INCOMPLETE') and
                f['vco_valid_control_voltage'] is None and f['target_reachable'] is None and
                all(f[k] is None for k in ('vlock_v', 'kvco_local_hz_per_v', 'f0_local_hz')),
                'missing measurements require explicit failed/incomplete status and null operating point')
        checks = {'startup': f['startup_status'], 'divider_drive': f['divider_drive_status'],
                  'frequency': 'UNKNOWN', 'physical_evidence': 'FAIL' if f['validation_status'] == 'FAILED' else 'UNKNOWN'}
        return {'schema_version': 'pll-vco-feedback-assessment-1.0', 'experiment_id': f['experiment_id'],
            'source_candidate_sha256': g['source_candidate_sha256'], 'feedback_sha256': fingerprint(f),
            'source_candidate_id': g['source_candidate_id'], 'source_handoff_sha256': g['source_handoff_sha256'],
            'problem_sha256': g['problem_sha256'], 'model_fingerprint': g['model_fingerprint'],
            'guidance_validation': validation, 'cp_evidence_sources': cp_sources,
            'target_operating_point_confirmed': False, 'target_root': {'status': 'UNCONFIRMED'},
            'frequency_residual_hz': None, 'frequency_measurement_basis': None,
            'reachability_status': 'UNKNOWN_NO_VALID_TUNING_MEASUREMENTS', 'actual_local_parameters': None,
            'nominal_parameter_errors': None, 'measured_tuning_range_hz': None,
            'common_valid_voltage_interval': None, 'joint_valid_interval_status': 'UNCONFIRMED',
            'physical_checks': checks, 'physical_status': 'REQUIREMENTS_FAILED' if 'FAIL' in checks.values() else 'UNKNOWN',
            'failure_reasons': deepcopy(f['failure_reasons']),
            'M1_status': 'NOT_EVALUATED', 'M2_status': 'NOT_EVALUATED', 'FULL_SYSTEMSPEC_CERTIFIED': False}
    limits = interval(f['vco_valid_control_voltage'], 'V', 'VCO valid voltage')
    cp = cp_range is not None
    cp_range = cp_range if cp else (-math.inf, math.inf)
    rails = interval(g['control_voltage_limits'], 'V', 'declared voltage')
    common = (max(rails[0], limits[0], cp_range[0]), min(rails[1], limits[1], cp_range[1]))
    samples = f['tuning_samples']
    require(isinstance(samples, list) and len(samples) >= 2, 'at least two tuning samples required')
    for s in samples:
        require(set(s) == {'vctrl_v', 'frequency_hz'} and number(s['frequency_hz'], 'frequency_hz') > 0,
                'positive measured frequency required')
        number(s['vctrl_v'], 'vctrl_v')
    require(all(a['vctrl_v'] < b['vctrl_v'] for a, b in zip(samples, samples[1:])), 'ordered unique voltage samples required')
    require(samples[0]['vctrl_v'] <= limits[0] and samples[-1]['vctrl_v'] >= limits[1], 'scan must cover claimed VCO interval')
    require(f['target_reachable'] is None or type(f['target_reachable']) is bool, 'tri-state target_reachable required')
    tol = number(f['frequency_tolerance_hz'], 'frequency_tolerance_hz')
    require(0 <= tol < g['target_frequency_hz']*.01, 'frequency tolerance must be <1% of target')
    checks = {'startup': f['startup_status'], 'divider_drive': f['divider_drive_status'],
              'physical_evidence': 'PASS' if f['validation_status'] == 'MEASURED' else
                  'FAIL' if f['validation_status'] == 'FAILED' else 'UNKNOWN'}
    result = {'schema_version': 'pll-vco-feedback-assessment-1.0', 'experiment_id': f['experiment_id'],
        'source_candidate_sha256': g['source_candidate_sha256'], 'feedback_sha256': fingerprint(f),
        'source_candidate_id': g['source_candidate_id'], 'source_handoff_sha256': g['source_handoff_sha256'],
        'problem_sha256': g['problem_sha256'], 'model_fingerprint': g['model_fingerprint'],
        'guidance_validation': validation, 'cp_evidence_sources': cp_sources,
        'target_operating_point_confirmed': False, 'frequency_residual_hz': None,
        'frequency_measurement_basis': None,
        'reachability_status': 'UNKNOWN', 'actual_local_parameters': None, 'nominal_parameter_errors': None,
        'common_valid_voltage_interval': {'min': common[0], 'max': common[1], 'unit': 'V'} if cp and common[0] < common[1] else None,
        'joint_valid_interval_status': 'UNCONFIRMED' if not cp else 'REPORTED_MATCHED_CONDITIONS' if common[0] < common[1] else 'NO_COMMON_INTERVAL',
        'M1_status': 'NOT_EVALUATED', 'M2_status': 'NOT_EVALUATED', 'FULL_SYSTEMSPEC_CERTIFIED': False}
    legal_samples = [s for s in samples if rails[0] <= s['vctrl_v'] <= rails[1] and
                     limits[0] <= s['vctrl_v'] <= limits[1]]
    require(bool(legal_samples), 'no samples inside legal VCO voltage range')
    frequencies = [s['frequency_hz'] for s in legal_samples]
    result['measured_tuning_range_hz'] = {'min': min(frequencies), 'max': max(frequencies), 'unit': 'Hz',
                                         'scope': 'SAMPLED_ONLY'}
    result['target_root'] = _root_estimate([s for s in legal_samples
        if not cp or common[0] <= s['vctrl_v'] <= common[1]], g['target_frequency_hz'])
    if f['target_reachable'] is False:
        require(not any(abs(v-g['target_frequency_hz']) <= tol for v in frequencies) and
                not min(frequencies) <= g['target_frequency_hz'] <= max(frequencies),
                'unreachable report contradicts measured tuning samples')
        require(all(f[k] is None for k in ('vlock_v', 'kvco_local_hz_per_v', 'f0_local_hz')), 'unreachable point must be null')
        result['reachability_status'] = 'FREQUENCY_UNREACHABLE_IN_REPORTED_SCAN'; checks['frequency'] = 'FAIL'
    elif f['target_reachable'] is True:
        v = number(f['vlock_v'], 'vlock_v'); kv = number(f['kvco_local_hz_per_v'], 'Kvco_local')
        require(kv > 0, 'positive local Kvco required by current model')
        anchor = next((s for s in samples if s['vctrl_v'] == v), None)
        require(anchor is not None, 'operating point requires an actual measured voltage sample')
        measured_hz = anchor['frequency_hz']; residual = measured_hz-g['target_frequency_hz']
        lo, hi = f['kvco_extraction_voltages_v']
        require(number(lo, 'extraction low') < v < number(hi, 'extraction high'), 'local slope must bracket Vlock')
        a = next((s for s in samples if s['vctrl_v'] == lo), None)
        b = next((s for s in samples if s['vctrl_v'] == hi), None)
        require(a is not None and b is not None and math.isclose(kv, (b['frequency_hz']-a['frequency_hz'])/(hi-lo),
                rel_tol=1e-6), 'local Kvco must match reported bracketing secant')
        require(limits[0] <= lo < hi <= limits[1] and
                lo == max(s['vctrl_v'] for s in samples if s['vctrl_v'] < v) and
                hi == min(s['vctrl_v'] for s in samples if s['vctrl_v'] > v),
                'local slope requires nearest measured neighbors inside valid VCO interval')
        f0 = measured_hz-kv*v
        require(math.isclose(number(f['f0_local_hz'], 'f0_local_hz'), f0, rel_tol=1e-9, abs_tol=1e-6), 'local tangent intercept mismatch')
        precision = f.get('target_point_measurement')
        uncertainty = None
        if precision is not None:
            require(isinstance(precision, dict) and isinstance(precision.get('method'), str) and precision['method'],
                    'frequency measurement precision method required')
            uncertainty = number(precision['frequency_uncertainty_hz'], 'frequency_uncertainty_hz')
            require(uncertainty >= 0, 'negative frequency uncertainty')
            evidence(precision.get('evidence'), 'frequency measurement evidence')
            require(all(e in f['evidence'] for e in precision['evidence']), 'frequency measurement evidence not linked to feedback')
        trusted_error = _options(options)['target_confirmation']['max_frequency_error_hz']
        roundoff = 4*math.ulp(float(g['target_frequency_hz']))
        confirmed = (f['validation_status'] == 'MEASURED' and abs(residual) <= tol and
            ((precision is None and abs(residual) <= roundoff) or
             (precision is not None and trusted_error is not None and abs(residual) <= uncertainty and
              abs(residual)+uncertainty <= trusted_error)))
        result.update(frequency_residual_hz=residual, measured_anchor_frequency_hz=measured_hz,
            target_operating_point_confirmed=confirmed,
            frequency_measurement_basis={'reported_tolerance_hz': tol, 'precision': deepcopy(precision),
                'trusted_max_frequency_error_hz': trusted_error, 'legacy_roundoff_allowance_hz': roundoff,
                'evidence': deepcopy(f['evidence']), 'method': f['measurement_method']})
        if confirmed:
            result['target_root'] = {'status': 'MEASURED_WITHIN_TRUSTED_ACCURACY' if precision else 'LEGACY_EXACT_SAMPLE',
                'measured_vlock_v': v, 'measured_frequency_hz': measured_hz, 'frequency_residual_hz': residual,
                'scope': 'MEASURED_POINT_WITH_REPORTED_ACCURACY; NO_CURVE_TRANSLATION'}
        legal = rails[0] <= v <= rails[1] and limits[0] <= v <= limits[1]
        checks['frequency'] = 'FAIL' if not legal else 'PASS' if confirmed else 'UNKNOWN'
        checks['common_voltage'] = 'PASS' if cp and common[0] < v < common[1] else 'FAIL' if cp else 'UNKNOWN'
        margin_v = min(v-common[0], common[1]-v)
        common_frequencies = [s['frequency_hz'] for s in samples if common[0] <= s['vctrl_v'] <= common[1]]
        margin_hz = min(g['target_frequency_hz']-min(common_frequencies), max(common_frequencies)-g['target_frequency_hz']) if common_frequencies else None
        result['measured_tuning_margin'] = {'voltage_v': margin_v if cp else None, 'frequency_hz': margin_hz if cp else None,
                                             'scope': 'REPORTED_COMMON_INTERVAL_AND_SAMPLES'}
        for name, value in (('voltage_v', margin_v), ('frequency_hz', margin_hz)):
            required = g['required_tuning_margin'][name]
            checks['margin_'+name] = ('UNKNOWN' if required is None or not cp or value is None else
                                     'PASS' if value >= required else 'FAIL')
        actual = {'vlock_v': v, 'kvco_local_hz_per_v': kv, 'f0_local_hz': f0}
        checks.update({name: 'PASS' if bounds['min'] <= actual[name] <= bounds['max'] else 'FAIL'
                       for name, bounds in g['hard_constraints'].items()})
        result.update(reachability_status='MEASURED_TARGET_REACHED' if confirmed else
                'APPROXIMATE_MEASURED_POINT' if abs(residual) <= tol else 'UNCONFIRMED_MEASURED_POINT',
            actual_local_parameters=actual,
            local_slope_extraction={'method': 'NEAREST_BRACKETING_SECANT', 'voltage_window_v': [lo, hi],
                                    'scope': 'FINITE_DIFFERENCE_ESTIMATE_AT_TARGET'},
            nominal_parameter_errors={'vlock_error_v': v-g['preferred_vlock_v'],
                'kvco_error_hz_per_v': kv-g['preferred_kvco_hz_per_v'],
                'kvco_relative_error': kv/g['preferred_kvco_hz_per_v']-1,
                'f0_local_error_hz': f0-g['nominal_f0_hz'],
                'target_match_status': 'EXACT_MATCH' if kv == g['preferred_kvco_hz_per_v'] and f0 == g['nominal_f0_hz'] else 'NOMINAL_DEVIATION',
                'f0_local_semantics': 'MEASURED_ANCHOR_TANGENT_INTERCEPT; NOT_MEASURED_ZERO_VOLT_FREQUENCY'})
    else:
        require(all(f[k] is None for k in ('vlock_v', 'kvco_local_hz_per_v', 'f0_local_hz')),
                'unknown operating point must be null')
        checks['frequency'] = 'UNKNOWN'
    result['physical_checks'] = checks
    result['failure_reasons'] = deepcopy(f['failure_reasons'])
    result['physical_status'] = ('REQUIREMENTS_FAILED' if 'FAIL' in checks.values() else
        'UNKNOWN' if 'UNKNOWN' in checks.values() else 'READY_FOR_SYSTEM_REVALIDATION')
    return result
