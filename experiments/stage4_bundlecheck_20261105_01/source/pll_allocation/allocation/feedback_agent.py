"""Separate, pluggable post-feedback tool loop; never imported by first-shot runner."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
from .allocate import optimize
from .core import assess_m1, fingerprint, write_new
from .repair import interpret_feedback, repair


class MockRepairPolicy:
    policy_id = 'MOCK_FEEDBACK_POLICY_NOT_LLM'

    def decide(self, context):
        done = context['completed_tools']
        kind = context['feedback']['kind']
        if not done:
            return {'tool': 'InterpretVerificationFeedback', 'args': {}, 'reason': 'Inspect bound failure category before selecting a repair.'}
        if kind in ('MODEL_OUT_OF_DOMAIN', 'UNRELIABLE_MEASUREMENT'):
            return {'tool': 'RequestDiagnosis', 'args': {}, 'reason': 'Unknown applicability or measurement requires evidence before changing blocks.'}
        if 'RepairCandidate' not in done:
            return {'tool': 'RepairCandidate', 'args': {}, 'reason': 'Use the failure-specific coupled physical repair; this policy is a mock.'}
        if context['has_repair_candidate']:
            return {'tool': 'SubmitRepairForM2', 'args': {}, 'reason': 'Stage complete changed candidate for independent M2; no success claim.'}
        return {'tool': 'RequestDiagnosis', 'args': {}, 'reason': 'No changed justified candidate; avoid repeating identical M2 input.'}


def run_repair_agent(model, system_spec, candidate, feedback, meter, out, policy, max_steps=6):
    """Policy protocol decide(context)->{tool,args,reason}; numerical tools own floats.

    A real LLM policy can implement this protocol; this module does not relabel the
    deterministic fixture policy as an LLM. No injected M2 evaluator is called.
    """
    interpret_feedback(candidate, feedback)
    root = Path(out)
    root.mkdir(parents=True, exist_ok=False)
    write_new(root/'feedback_input.json', {'candidate': candidate, 'feedback': feedback, 'system_spec': system_spec})
    trace, new, status = [], None, 'STEP_BUDGET_EXHAUSTED'
    for step in range(max_steps):
        context = {'feedback': feedback, 'candidate': candidate, 'system_spec': system_spec,
            'completed_tools': [r['action']['tool'] for r in trace], 'has_repair_candidate': new is not None,
            'last_observation': trace[-1]['observation'] if trace else None,
            'allowed_tools': ['InterpretVerificationFeedback', 'RepairCandidate', 'OptimizeCandidate', 'SubmitRepairForM2', 'RequestDiagnosis', 'Stop'],
            'remaining': {'M1': meter.m1_limit-meter.counts['M1_calls'], 'M2': 0}}
        action = policy.decide(deepcopy(context))
        tool = action.get('tool')
        if tool not in context['allowed_tools']:
            raise ValueError('invalid repair Agent tool')
        if tool == 'InterpretVerificationFeedback':
            observation = interpret_feedback(candidate, feedback)
        elif tool == 'RepairCandidate':
            new, observation = repair(model, system_spec, candidate, feedback, meter)
        elif tool == 'OptimizeCandidate':
            if feedback['kind'] in ('MODEL_OUT_OF_DOMAIN', 'UNRELIABLE_MEASUREMENT'):
                raise ValueError('diagnostic feedback cannot justify blind optimization')
            new, observation = optimize(model, system_spec, meter)
            if new is not None and fingerprint(new) == fingerprint(candidate):
                new = None
                observation['status'] = 'NO_CHANGE_DIAGNOSIS_REQUIRED'
        elif tool == 'SubmitRepairForM2':
            if new is None:
                raise ValueError('changed complete repair candidate required')
            write_new(root/'repair_joint_block_spec.json', new)
            assessment = assess_m1(model, system_spec, new, meter)
            observation = {'M1': assessment, 'M2_status': 'DEFERRED_TO_TRACK_B', 'feedback_source': feedback['source']}
            write_new(root/'repair_submission.json', {'candidate': new, 'parameter_sha256': fingerprint(new), **observation})
            status = 'REPAIR_STAGED_NOT_M2_VERIFIED'
        else:
            observation = {'kind': feedback['kind'], 'reason': action.get('reason', ''), 'M2_status': 'DIAGNOSIS_REQUIRED'}
            status = 'DIAGNOSIS_REQUIRED' if tool == 'RequestDiagnosis' else 'POLICY_STOPPED'
        row = {'step': step+1, 'policy': policy.policy_id, 'action': action, 'observation': observation,
               'decision': action.get('reason', ''), 'cost_to_date': deepcopy(meter.counts)}
        trace.append(row)
        if status != 'STEP_BUDGET_EXHAUSTED':
            break
    write_new(root/'agent_trace.json', trace)
    result = {'status': status, 'policy': policy.policy_id, 'source': feedback['source'],
              'cost': meter.counts, 'real_repair_success_rate': None, 'verified_joint_block_spec': False}
    write_new(root/'result.json', result)
    return result
