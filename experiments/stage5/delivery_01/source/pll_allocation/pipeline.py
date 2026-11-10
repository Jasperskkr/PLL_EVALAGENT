"""Unified SystemSpec -> existing Track A -> real Track B -> Agent feedback runner."""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
from .allocation import AllocationStrategyPolicy
from .block_space.contracts import check_parameters
from .pipeline_contracts import check_result, load_inputs, make_feedback, m2_label
from .physics_mapping.model import fingerprint
from .allocation.core import Meter, assess_m1, proposal, read, validate_proposal, write_new
from .verification import verify
from .verification.verify import validate_proposal as validate_m2_proposal


def source_identity():
    package = Path(__file__).parent
    paths = [package/n for n in ('pipeline.py', 'pipeline_contracts.py', 'llm_transport.py', 'scenarios.py')]
    for name in ('allocation', 'physics_mapping', 'block_space', 'verification'):
        paths.extend(sorted((package/name).glob('*.py')))
    paths.extend([package/'verification/kernel.cpp'])
    for name in ('kernel.dll', 'identity.json'):
        p = package/'verification/build'/name
        if p.is_file():
            paths.append(p)
    return [{'path': str(p.resolve()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]


def run_pipeline(out, strategy='analytical', *, config_path=None, proposal_path=None,
                 m2_budget=None, repair_budget=None, llm_config=None, policy=None, measurement_extension=None,
                 scenario_path=None, seed=None, feedback_from=None):
    if measurement_extension and not proposal_path:
        raise ValueError('Stage4 measured evidence requires explicit existing-proposal reverification; cannot contaminate a new first shot')
    config, model, spec, protocol = load_inputs(config_path)
    scenario, binding, scenario_file_hash = None, None, None
    if scenario_path:
        from .scenarios import load_scenario, raw_hash
        scenario, spec, binding = load_scenario(scenario_path, config, spec)
        scenario_file_hash = raw_hash(scenario_path)
    if scenario_path and (proposal_path or measurement_extension):
        raise ValueError('research scenarios require new allocation or explicit bound feedback continuation')
    parent_history = []
    if feedback_from:
        if not scenario_path or proposal_path:
            raise ValueError('feedback continuation requires explicit research scenario')
        parent = Path(feedback_from).resolve()
        prior = read(parent/'AllocationProposal.json')
        prior_result = read(parent/'BehavioralVerificationResult.json')
        if prior.get('scenario_binding') != binding:
            raise ValueError('feedback continuation scenario mismatch')
        validate_proposal(model, prior)
        check_result(prior_result, prior, protocol)
        if prior_result['overall_status'] != 'FAIL':
            raise ValueError('feedback continuation requires certified hard FAIL')
        feedback = make_feedback(prior, prior_result, protocol, {'M2_verifications': m2_budget or 1})
        if feedback['kind'] not in ('BW', 'MULTIPLE', 'PM', 'COLD_START_CAPTURE', 'TUNING_UNREACHABLE'):
            raise ValueError('no actionable certified failure feedback')
        parent_history = [{'candidate': deepcopy(prior['joint_block_spec']), 'feedback': feedback}]
    budget = deepcopy(config['budgets'])
    if m2_budget is not None:
        budget['M2_verifications'] = m2_budget
    if repair_budget is not None:
        budget['feedback_repairs'] = repair_budget
    if (any(type(n) is not int or n < 0 for n in budget.values())
            or budget['M2_verifications'] < 1 or budget['feedback_repairs'] >= budget['M2_verifications']):
        raise ValueError('positive M2 budget must cover first shot and every allowed repair')
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    raw = root/'raw'
    raw.mkdir()
    start = time.perf_counter()
    inputs_hash = fingerprint([model, spec, protocol, config])
    sources = source_identity()
    for name, value in [('input_system_spec', spec), ('block_space_snapshot', model),
                        ('topology_snapshot', model['topology']), ('protocol_snapshot', protocol),
                        ('pipeline_config', config), ('source_manifest', sources)]:
        write_new(root/(name+'.json'), value)
    if scenario:
        write_new(root/'research_scenario.json', scenario)
    if feedback_from:
        write_new(root/'feedback_parent.json', {'path': str(parent), 'proposal_sha256': fingerprint(prior),
            'result_sha256': fingerprint(prior_result), 'feedback': feedback,
            'origin': 'DETERMINISTIC_REPAIR_OF_REAL_M2; parent calls not recounted'})
    llm = deepcopy(llm_config if llm_config is not None else config['llm'])
    # No credentials are read into reports; only environment variable names and model identity.
    llm_identity = {'config': llm, 'requested_model': os.environ.get(llm.get('model_env', 'ANTHROPIC_MODEL')),
                    'environment_available': all(bool(os.environ.get(llm.get(k, d))) for k, d in
                        [('model_env', 'ANTHROPIC_MODEL'), ('api_key_env', 'ANTHROPIC_AUTH_TOKEN'),
                         ('base_url_env', 'ANTHROPIC_BASE_URL')])} if strategy == 'llm_agent' else None
    policy = policy or AllocationStrategyPolicy(strategy, llm, config['seed'] if seed is None else seed)
    meter = Meter(budget['cheap_calls'], budget['M1_calls'])
    write_new(root/'run_manifest.json', {'schema_version': 'pll-pipeline-manifest-1.0',
        'created_at': datetime.now().astimezone().isoformat(), 'strategy': strategy,
        'candidate_origin': 'FEEDBACK_CONTINUATION' if feedback_from else 'EXISTING_PROPOSAL_REVERIFICATION' if proposal_path else 'NEW_ALLOCATION',
        'run_scope': 'RESEARCH_SCENARIO' if scenario else 'FORMAL_FROZEN_SNAPSHOT',
        'scenario_binding': binding, 'scenario_file_sha256': scenario_file_hash,
        'seed': config['seed'] if seed is None else seed,
        'first_shot_scope': 'No current-run M2 feedback before initial submission; design M1 calls counted',
        'versions': model['versions'], 'block_space_sha256': fingerprint(model),
        'system_spec_sha256': fingerprint(spec), 'protocol_id': protocol['protocol_id'],
        'protocol_sha256': fingerprint(protocol), 'protocol_hash_encoding': 'sorted_compact_json_utf8',
        'budget': budget, 'llm': llm_identity, 'source_manifest_sha256': fingerprint(sources),
        'environment': {'python': sys.version, 'platform': platform.platform(),
            'dependencies': {n: importlib.metadata.version(n) for n in ('numpy', 'scipy')}},
        'cost_scope': 'M2_verifications count full TB invocations, each contains paired capture plus four full sweeps; native runs separately counted',
        'state': 'STARTED; terminal state is result.json'})
    trace_file = root/'allocation_trace.jsonl'
    trace_file.open('x', encoding='utf-8').close()

    def trace(event, **details):
        with trace_file.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'event': event, 'elapsed_s': time.perf_counter()-start,
                                      **({'scenario_binding': binding} if binding else {}),
                                      **details}, ensure_ascii=False, allow_nan=False)+'\n')

    history, attempts, failure = deepcopy(parent_history), [], None
    status, candidate = 'NO_CANDIDATE', None
    try:
        preflight = None
        if scenario:
            from .allocation.physics import propagate
            preflight = propagate(model, spec)
            write_new(root/'physics_preflight.json', {'scenario_binding': binding, **preflight})
            trace('PHYSICS_PREFLIGHT', observation=preflight)
            if preflight['status'] == 'PROVEN_INFEASIBLE':
                status = 'INFEASIBLE_UNDER_M1_ASSUMPTIONS'
                write_new(root/'infeasibility.json', {'status': status, 'scenario_binding': binding,
                    'certificate': preflight, 'scope': 'ideal continuous M1 and declared capacitor choices; not absolute CPPLL physical impossibility'})
        for index in range(1 + budget['feedback_repairs']):
            if status == 'INFEASIBLE_UNDER_M1_ASSUMPTIONS':
                break
            folder = root/f'attempt_{index+1:03d}'
            folder.mkdir()
            stage = 'FIRST_SHOT' if index == 0 and not feedback_from else 'FEEDBACK_REPAIR'
            before = time.perf_counter()
            if proposal_path and index == 0:
                original = read(proposal_path)
                validate_m2_proposal(original)
                validate_proposal(model, original)
                write_new(root/'source_proposal.json', original)
                candidate = deepcopy(original['joint_block_spec'])
                metadata = {'status': 'EXISTING_PROPOSAL_REVERIFICATION',
                            'original_strategy': original['allocation_strategy'],
                            'original_proposal_sha256': fingerprint(original), 'real_LLM_calls_this_run': 0}
            else:
                candidate, metadata = policy.propose(deepcopy(model), deepcopy(spec), meter, folder, deepcopy(history))
            write_new(folder/'allocation_metadata.json', metadata)
            if candidate is None:
                status = metadata.get('status', 'NO_CANDIDATE')
                trace('POLICY_STOP', stage=stage, metadata=metadata)
                break
            # Frozen before formal M1 and before any full behavioral TB of this submission.
            write_new(folder/'submitted_joint_block_spec.json', candidate)
            if index == 0:
                write_new(root/'initial_joint_block_spec.json', candidate)
            trace('SUBMISSION_SAVED', stage=stage, parameter_sha256=fingerprint(candidate),
                  generation_elapsed_s=time.perf_counter()-before, reason=metadata)
            domain = check_parameters(model, candidate)
            write_new(folder/'constraint_checks.json', domain)
            assessment = assess_m1(model, spec, candidate, meter)
            if binding:
                assessment['scenario_binding'] = deepcopy(binding)
            write_new(folder/'M1_prediction.json', assessment)
            item = proposal(model, spec, candidate, strategy, assessment, metadata,
                            root.name+f'-{index+1:03d}-'+fingerprint(candidate)[:12])
            if scenario:
                item.update(research_scenario=deepcopy(scenario), scenario_binding=deepcopy(binding))
            write_new(folder/'AllocationProposal.json', item)
            if measurement_extension:
                # Explicit, version-bound research evidence; original M2 verdict stays independent.
                from .verification.return_ratio_validity import load_extension
                extension = load_extension(measurement_extension, item)
                write_new(folder/'measurement_extension.json', extension)
                diagnostic = {'schema_version': 'allocation-feedback-1.0',
                    'parameter_sha256': fingerprint(candidate), 'source': 'M2',
                    'kind': 'UNRELIABLE_MEASUREMENT', 'verdict': 'UNKNOWN',
                    'evidence_source': 'M2_STAGE4_RESEARCH_EXTENSION',
                    'structured_feedback': extension['structured_feedback'],
                    'metrics': extension['metrics'], 'prediction_errors': extension['prediction_errors'],
                    'reason': extension['scientific_status']}
                receipt = policy.receive_feedback(deepcopy(candidate), deepcopy(diagnostic))
                write_new(folder/'measurement_extension_agent_receipt.json', receipt)
            if index == 0:
                write_new(root/'AllocationProposal.json', item)
            attempt = {'stage': stage, 'parameter_sha256': fingerprint(candidate),
                       'validation_level': assessment['validation_level'],
                       'M1_status': 'M1_PASS' if assessment['judgment']['verdict'] == 'M1_SPEC_PASS'
                           else 'M1_FAIL' if assessment['judgment']['verdict'] == 'M1_SPEC_FAIL' else 'M1_UNKNOWN',
                       'directory': folder.name, 'M2_status': 'M2_UNKNOWN'}
            attempt.update(generation_elapsed_s=time.perf_counter()-before, scenario_binding=binding,
                first_shot_kind='LLM_TOOL_ASSISTED_FIRST_SHOT' if strategy == 'llm_agent' and stage == 'FIRST_SHOT' else stage)
            attempts.append(attempt)
            if domain['declared_domain'] != 'IN_DECLARED_DOMAIN' or domain['model_validity'] != 'VALID':
                status = 'M2_UNKNOWN'
                trace('CONSTRAINT_REJECTED', domain=domain)
                break
            validate_proposal(model, item)
            if scenario:
                from .verification.scenario import validate_research_proposal, verify_research
                validate_research_proposal(item)
            else:
                validate_m2_proposal(item)
            if meter.counts['M2_calls'] >= budget['M2_verifications']:
                status = 'M2_BUDGET_EXHAUSTED'
                break
            # Recheck formal assets before every real invocation, rather than trusting policy metadata.
            current_config, current_model, current_spec, current_protocol = load_inputs(config_path)
            if scenario:
                current_scenario, current_spec, current_binding = load_scenario(scenario_path, current_config, current_spec)
                if current_binding != binding or current_scenario != scenario or raw_hash(scenario_path) != scenario_file_hash:
                    raise RuntimeError('SCENARIO_MUTATED_DURING_RUN')
            if fingerprint([current_model, current_spec, current_protocol, current_config]) != inputs_hash:
                raise RuntimeError('INPUT_BINDING_CHANGED_DURING_RUN')
            meter.charge('M2_calls', stage=stage, parameter_sha256=fingerprint(candidate))
            event = meter.events[-1]
            trace('M2_STARTED', stage=stage, parameter_sha256=fingerprint(candidate))
            before = time.perf_counter()
            try:
                measured = (verify_research if scenario else verify)(deepcopy(item), raw/f'attempt_{index+1:03d}')
                check_result(measured, item, protocol)
                event['status'] = 'RETURNED'
            except Exception as error:
                event.update(status='ERROR', error_type=type(error).__name__, reason=str(error))
                raise
            finally:
                event['elapsed_s'] = time.perf_counter()-before
            write_new(folder/'BehavioralVerificationResult.json', measured)
            status = m2_label(measured)
            attempt.update(M2_status=status, M2_overall_status=measured['overall_status'],
                           metrics=measured['metrics'], constraints=measured.get('constraints', []),
                           prediction_errors=measured.get('prediction_errors', {}),
                           execution_cost=measured['execution_cost'],
                           M1_posthoc_calls=int(measured.get('M1_posthoc') is not None))
            trace('M2_COMPLETED', stage=stage, status=status, overall_status=measured['overall_status'])
            if measured['overall_status'] == 'PASS':
                break
            feedback = make_feedback(item, measured, protocol,
                {'M2_verifications': budget['M2_verifications']-meter.counts['M2_calls'],
                 'feedback_repairs': budget['feedback_repairs']-index})
            write_new(folder/'structured_feedback.json', feedback)
            acknowledgement = policy.receive_feedback(deepcopy(candidate), deepcopy(feedback))
            write_new(folder/'agent_feedback_receipt.json', acknowledgement)
            trace('FEEDBACK_RECEIVED_BY_AGENT', stage=stage, feedback_kind=feedback['kind'], receipt=acknowledgement)
            history.append({'candidate': deepcopy(candidate), 'feedback': feedback})
            # UNKNOWN measurements and model-domain errors warrant diagnosis, not automatic parameter changes.
            if feedback['kind'] in ('UNRELIABLE_MEASUREMENT', 'MODEL_OUT_OF_DOMAIN'):
                break
    except Exception as error:
        failure = {'type': type(error).__name__, 'reason': str(error)}
        status = 'PIPELINE_ERROR'
        trace('ERROR', failure=failure)
    if fingerprint([model, spec, protocol, config]) != inputs_hash or source_identity() != sources:
        status, failure = 'PIPELINE_ERROR', {'type': 'RuntimeError', 'reason': 'INPUT_OR_SOURCE_MUTATED'}
    if scenario and raw_hash(scenario_path) != scenario_file_hash:
        status, failure = 'PIPELINE_ERROR', {'type': 'RuntimeError', 'reason': 'SCENARIO_MUTATED_DURING_RUN'}
    write_new(root/'cost_events.json', meter.events)
    if candidate is not None:
        write_new(root/'final_joint_block_spec.json', candidate)
    native_summaries = [read(p)['summary'] for p in raw.rglob('summary.json')]
    native_failures = [read(p) for p in raw.rglob('failure.json')]
    cost = {**meter.counts, 'native_completed_runs': len(native_summaries),
            'native_failed_attempts': len(native_failures),
            'integration_points': sum(s['integration_points'] for s in native_summaries),
            'native_elapsed_s': sum(s['elapsed_s'] for s in native_summaries),
            'native_failure_elapsed_s': sum(s['elapsed_s'] for s in native_failures),
            'M1_posthoc_calls': sum(a.get('M1_posthoc_calls', 0) for a in attempts),
            'M1_total_calls': meter.counts['M1_calls']+sum(a.get('M1_posthoc_calls', 0) for a in attempts),
            'total_elapsed_s': time.perf_counter()-start, 'monetary_cost': None}
    result = {'schema_version': 'pll-unified-run-result-1.0', 'status': status, 'strategy': strategy,
              'candidate_origin': 'FEEDBACK_CONTINUATION' if feedback_from else 'EXISTING_PROPOSAL_REVERIFICATION' if proposal_path else 'NEW_ALLOCATION',
              'scenario_binding': binding, 'feedback_parent': str(parent) if feedback_from else None,
              'attempts': attempts, 'cost': cost, 'failure': failure,
              'first_shot': attempts[0] if attempts and not feedback_from else None,
              'verified_joint_block_spec': status == 'M2_PASS',
              'full_behavioral_pass': status == 'M2_PASS',
              'LLM_execution': 'REAL_REQUESTS_ONLY' if strategy == 'llm_agent' and not proposal_path else 'NOT_APPLICABLE',
              'feedback_received_by_agent': bool(history)}
    if strategy == 'llm_agent':
        result['LLM_allocation_status'] = ('NOT_APPLICABLE_M1_INFEASIBLE' if status == 'INFEASIBLE_UNDER_M1_ASSUMPTIONS'
            else 'REAL_LLM_EXECUTED' if candidate is not None and meter.counts['LLM_calls'] else 'REAL_LLM_NOT_EXECUTED')
    write_new(root/'result.json', result)
    lines = [f'# Unified PLL run: {root.name}', '', f'Status: {status}',
             f'Strategy: {strategy}; origin: {result["candidate_origin"]}',
             f'Full behavioral PASS: {result["full_behavioral_pass"]}', '',
             'M1 prediction and independently measured M2 are separate. Partial BW acceptance retains overall UNKNOWN.', '']
    for a in attempts:
        lines += [f'## {a["stage"]}: {a["M1_status"]} / {a["M2_status"]}', '',
                  '|Required metric|M2 status|', '|---|---|']
        lines += [f'|{c["metric"]}|{c["status"]}|' for c in a.get('constraints', [])]
    lines += ['', f'Cost: {json.dumps(cost)}', f'Failure: {json.dumps(failure)}']
    with (root/'report.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines)+'\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--strategy', default='analytical',
                        choices=['nominal', 'analytical', 'sensitivity_optimization', 'random', 'llm_agent'])
    parser.add_argument('--config')
    parser.add_argument('--proposal', help='Existing Track A proposal: explicit reverification, never a new LLM call')
    parser.add_argument('--m2-budget', type=int)
    parser.add_argument('--repair-budget', type=int)
    parser.add_argument('--llm-config', help='Existing Messages transport configuration JSON; environment names only')
    parser.add_argument('--measurement-extension', help='Explicit Stage4 research evidence; no M2 certification upgrade')
    parser.add_argument('--scenario', help='Versioned research threshold overlay; frozen assets unchanged')
    parser.add_argument('--seed', type=int, help='Declared random draw seed')
    parser.add_argument('--feedback-from', help='Prior bound attempt directory with real certified hard FAIL')
    args = parser.parse_args(argv)
    try:
        result = run_pipeline(args.out, args.strategy, config_path=args.config, proposal_path=args.proposal,
                              m2_budget=args.m2_budget, repair_budget=args.repair_budget,
                              llm_config=read(args.llm_config) if args.llm_config else None,
                              measurement_extension=args.measurement_extension, scenario_path=args.scenario,
                              seed=args.seed, feedback_from=args.feedback_from)
        print(json.dumps({k: result[k] for k in ('status', 'strategy', 'cost', 'failure')}, ensure_ascii=False))
        return 2 if result['status'] in ('PIPELINE_ERROR', 'NO_CANDIDATE', 'POLICY_OR_TOOL_FAILED') else 0
    except (ValueError, KeyError, FileExistsError) as error:
        print(json.dumps({'status': 'INPUT_OR_OUTPUT_ERROR', 'reason': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
