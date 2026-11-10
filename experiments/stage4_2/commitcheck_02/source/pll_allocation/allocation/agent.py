"""Minimal tool-driven Agent; deterministic math, policy decisions and logs separated."""
from __future__ import annotations
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from .allocate import analytical, optimize, sensitivity
from .core import assess_m1, fingerprint, values, write_new
from .physics import RELATIONS, propagate

TOOLS = ['ReadSystemSpec', 'InspectBlockSpace', 'QueryPhysicalRelations', 'PropagateConstraints',
         'AnalyzeSensitivity', 'SolveInverseAllocation', 'OptimizeCandidate', 'EvaluateM1',
         'SubmitCandidateForM2', 'InterpretVerificationFeedback', 'Stop']


class MockPolicy:
    policy_id = 'MOCK_TOOL_POLICY_NOT_LLM'
    def decide(self, context):
        done = context['completed_tools']
        prefix = ['ReadSystemSpec', 'InspectBlockSpace', 'QueryPhysicalRelations', 'PropagateConstraints']
        for tool in prefix:
            if tool not in done:
                return {'tool': tool, 'args': {}, 'reason': 'Mock workflow inspection step; no real LLM.'}
        if context['constraint_status'] == 'PROVEN_INFEASIBLE':
            return {'tool': 'Stop', 'args': {}, 'reason': 'Analytical necessary-condition certificate.'}
        for tool in ['SolveInverseAllocation', 'AnalyzeSensitivity', 'OptimizeCandidate']:
            if tool not in done:
                return {'tool': tool, 'args': {}, 'reason': 'Mock comparison path using deterministic physics tools.'}
        handles = context['candidate_handles']
        if not handles:
            return {'tool': 'Stop', 'args': {}, 'reason': 'No legal candidate found.'}
        best = max(handles, key=lambda h: context['candidate_handles'][h].get('selection_score', -1e9))
        return {'tool': 'SubmitCandidateForM2', 'args': {'handle': best},
                'reason': 'Mock chooses largest declared engineering selection score; independent runner assessment follows.'}


class MessagesPolicy:
    """Configured native Messages transport, raw request/response and failure cost saved."""
    policy_id = 'REAL_LLM_TOOL_POLICY'
    def __init__(self, config, root, meter):
        self.config, self.root, self.meter = config, Path(root), meter
        self.calls = []

    def decide(self, context):
        cfg = self.config
        required = [cfg.get(k, default) for k, default in [('model_env', 'ANTHROPIC_MODEL'),
            ('base_url_env', 'ANTHROPIC_BASE_URL'), ('api_key_env', 'ANTHROPIC_AUTH_TOKEN')]]
        if not all(os.environ.get(k) for k in required):
            raise RuntimeError('LLM_ENVIRONMENT_UNAVAILABLE')
        if len(self.calls) >= cfg.get('max_calls', 4):
            raise RuntimeError('LLM_CALL_BUDGET_EXHAUSTED')
        directory = self.root / f'call_{len(self.calls)+1:03d}'
        directory.mkdir(parents=True, exist_ok=False)
        prompt = ('You are the PLL allocation decision policy. Choose the next deterministic tool, do not calculate '
            'high-precision values yourself. Return only JSON {"tool":name,"args":{},"reason":string}. '
            'Allowed tools: ' + ', '.join(TOOLS) + '. Inspection information is already in context; tools can be skipped. '
            'SolveInverseAllocation returns a complete physics inverse candidate handle. AnalyzeSensitivity returns '
            'M1 derivatives. OptimizeCandidate runs bounded constrained optimization and sensitivity if needed. '
            'EvaluateM1 and SubmitCandidateForM2 require args.handle from candidate_handles. Submit stages the '
            'first official candidate; M2 is unavailable and will be explicitly deferred. Stop if infeasibility proven. '
            'Choose a meaningful numerical strategy and explain why. Select between candidate handles using '
            'engineering margin and cost; never claim verified PASS. The fixed target and Block Space cannot change. '
            'No current-target M2 feedback is available. At most four network decisions; prioritize solving then submitting.')
        request = {'model': os.environ[required[0]], 'max_tokens': cfg.get('max_tokens', 1500),
            'system': prompt, 'messages': [{'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}]}
        write_new(directory/'request.json', request)
        write_new(directory/'config.json', cfg)
        meta = {'model': request['model'], 'real_network_call': True, 'usage': None}
        self.calls.append(meta)
        self.meter.charge('LLM_calls')
        start = time.perf_counter()
        transport = Path(__file__).parents[1]/'llm_transport.py'
        command = [sys.executable, '-B', str(transport), '--request', str(directory/'request.json'),
            '--config', str(directory/'config.json'), '--response', str(directory/'response.json'),
            '--status', str(directory/'transport_status.json')]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=cfg.get('timeout_s', 45), shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if (directory/'transport_status.json').exists():
                meta.update(json.loads((directory/'transport_status.json').read_text(encoding='utf-8')))
            if completed.returncode != 0:
                raise RuntimeError('LLM_TRANSPORT_FAILED')
            raw = json.loads((directory/'response.json').read_text(encoding='utf-8'))
            meta.update(usage=raw.get('usage'), response_model=raw.get('model'))
            response = ''.join(x.get('text', '') for x in raw.get('content', []) if x.get('type') == 'text').strip()
            if response.startswith('```'):
                response = response.split('\n', 1)[1].rsplit('```', 1)[0]
            action = json.loads(response)
            write_new(directory/'action.json', action)
            meta['status'] = 'RESPONDED'
            return action
        except subprocess.TimeoutExpired:
            if (directory/'transport_status.json').exists():
                meta.update(json.loads((directory/'transport_status.json').read_text(encoding='utf-8')))
            meta['status'] = 'TOTAL_PROCESS_TIMEOUT'
            raise RuntimeError('LLM_TOTAL_PROCESS_TIMEOUT') from None
        except Exception as error:
            meta.update(status='FAILED', error_type=type(error).__name__)
            raise
        finally:
            meta['elapsed_s'] = time.perf_counter() - start
            write_new(directory/'metadata.json', meta)


def run_agent(model, system_spec, meter, root, policy, *, max_steps=14):
    root = Path(root)
    handles, history, sens = {}, [], None
    constraints = propagate(model, system_spec)
    trace_path = root/'agent_trace.jsonl'
    trace_path.open('x', encoding='utf-8').close()
    selected, stop = None, 'STEP_BUDGET_EXHAUSTED'
    for step in range(max_steps):
        context = {'schema_version': 'agent-context-1.0', 'system_spec': system_spec,
            'block_space': {k: {a: v for a, v in axis.items() if a in ('unit', 'default', 'range', 'choices', 'fixed')}
                            for k, axis in model['variables'].items()},
            'relations': RELATIONS, 'constraint_status': constraints['status'],
            'completed_tools': [h['action']['tool'] for h in history],
            'candidate_handles': {h: {k: v for k, v in m.items() if k in ('selection_score', 'status', 'rationale', 'cheap_prediction', 'M1')}
                                  for h, (_, m) in handles.items()},
            'last_observation': history[-1]['observation'] if history else None,
            'remaining': {'steps': max_steps-step, 'cheap': meter.cheap_limit-meter.counts['analytic_calls'],
                          'M1': meter.m1_limit-meter.counts['M1_calls'], 'M2': 0}}
        before = time.perf_counter()
        action, observation = None, None
        try:
            action = policy.decide(deepcopy(context))
            if not isinstance(action, dict) or action.get('tool') not in TOOLS or not isinstance(action.get('args', {}), dict):
                raise ValueError('invalid agent action')
            tool, args = action['tool'], action.get('args', {})
            if tool == 'ReadSystemSpec':
                observation = system_spec
            elif tool == 'InspectBlockSpace':
                observation = context['block_space']
            elif tool == 'QueryPhysicalRelations':
                observation = RELATIONS
            elif tool == 'PropagateConstraints':
                observation = constraints
            elif tool == 'AnalyzeSensitivity':
                sens = sensitivity(model, system_spec, meter)
                observation = sens
            elif tool in ('SolveInverseAllocation', 'OptimizeCandidate'):
                c, meta = analytical(model, system_spec, meter) if tool == 'SolveInverseAllocation' else optimize(model, system_spec, meter, sens)
                if c:
                    handle = f'candidate_{len(handles)+1:02d}'
                    handles[handle] = (c, meta)
                    write_new(root/(handle+'.json'), {'candidate': c, 'metadata': meta})
                    observation = {'handle': handle, 'metadata': {k: meta[k] for k in ('status', 'selection_score', 'rationale') if k in meta}}
                else:
                    observation = meta
            elif tool == 'EvaluateM1':
                c, meta = handles[args['handle']]
                result = assess_m1(model, system_spec, c, meter)
                meta['M1'] = result
                observation = result
            elif tool == 'SubmitCandidateForM2':
                selected = args['handle']
                c, _ = handles[selected]
                write_new(root/'submission_request.json', {'candidate': c, 'parameter_sha256': fingerprint(c),
                    'M2_status': 'DEFERRED_TO_TRACK_B', 'reason': action.get('reason', '')})
                observation = {'status': 'STAGED_FOR_RUNNER', 'M2_status': 'DEFERRED_TO_TRACK_B'}
                stop = 'SUBMITTED'
            elif tool == 'InterpretVerificationFeedback':
                observation = {'status': 'NO_M2_FEEDBACK_IN_FIRST_SHOT', 'feedback_accepted': False}
            else:
                observation = {'status': 'STOPPED_BY_POLICY'}
                stop = 'PROVEN_INFEASIBLE' if constraints['status'] == 'PROVEN_INFEASIBLE' else 'POLICY_STOPPED'
            row = {'step': step+1, 'policy': policy.policy_id, 'action': action, 'observation': observation,
                   'decision': action.get('reason', ''), 'elapsed_s': time.perf_counter()-before, 'cost_to_date': deepcopy(meter.counts)}
        except Exception as error:
            stop = 'POLICY_OR_TOOL_FAILED'
            row = {'step': step+1, 'policy': policy.policy_id, 'action': action,
                   'observation': {'status': 'ERROR', 'error_type': type(error).__name__, 'reason': str(error)},
                   'elapsed_s': time.perf_counter()-before, 'cost_to_date': deepcopy(meter.counts)}
        history.append(row)
        with trace_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
        if selected or stop != 'STEP_BUDGET_EXHAUSTED':
            break
    meta = {'status': stop, 'policy': policy.policy_id, 'trace': trace_path.name,
            'LLM_calls': getattr(policy, 'calls', []), 'mock': isinstance(policy, MockPolicy)}
    if selected:
        candidate, info = handles[selected]
        return candidate, {**meta, 'selected_handle': selected, 'solver_metadata': info}
    return None, meta
