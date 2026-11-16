"""Real region policy using the same native Messages HTTP worker as allocation."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from ..allocation.core import write_new
from ..exploration.contracts import require
from ..physics_mapping.model import fingerprint

PROMPT = """You are the physics-guided initial allocation planner for an ideal integer-N CPPLL.
You choose the actual search geometry. The executor runs continuous SLSQP against the original formal M1.
Use the provided calibration, physics relations and local sensitivities. They are point evidence, not certified boxes.
Read best_known and current_tightest_constraint before selecting a neighborhood. A new local result may be worse
than calibration; only improvement_over_best.material indicates meaningful progress. Sensitivity sign conflicts
are working-point dependent: never state a global monotonicity rule from them. Sensitivity probes are not global coverage.
Return exactly one JSON object, no Markdown and no computed M1 values.
For an action use fields: action ("OPTIMIZE"), region_origin ("LLM_PROPOSED"),
normalized_bounds (object of Icp,Rz,C1,C2,f0,Kvco, each [lo,hi]),
active_variables (nonempty subset), seed_ids (zero or more valid_seed_ids), m1_budget (integer),
reason (one or two sentences describing the constraint, coupling and design hypothesis), evidence_ids (nonempty list).
Propose all six bounds yourself with 0 <= lo < hi <= 1. Coordinates are normalized across the entire user axis,
in the specified linear or log scale. Any supplied seed must be inside all six bounds; inspect its exact normalized coordinates.
Bounds that just contain a seed should leave headroom for rounding and enough space to search. If no suitable seed is
available, use an empty seed_ids list; a bounded auxiliary Probe may find a start inside your proposed box.
Request 2 to budget.max_this_decision_M1_calls. A seedless search needs at least 3 calls and spends some on seeding.
Budget includes finite differences and final recheck. All evidence IDs must come from allowed_evidence_ids.
Each SLSQP numerical iteration may need one formal M1 call per active variable plus a base point.
Allow enough iterations to use the local sensitivities; multiple seeds share the same action budget.
Use budget.SLSQP_cost_models_by_active_dimension: initial evaluation, differences, two update opportunities and
action final recheck. Initial differences alone are not enough for useful optimization. The controller prioritizes
a few quality/diverse starts and returns SKIPPED_BUDGET when insufficient; leftover budget may start another seed.
Seedless proposals also pay for Probe; a separate session reserve rechecks the final recommendation.
All seed coordinates are exact global normalized coordinates; check EACH seed against EVERY proposed bound.
You may use the prior decision, its actual observation and newly evaluated points to shift the region or change active variables.
Do not repeat the same effective search. After a completed observation, you may instead return exactly
{"action":"STOP","stop_basis":"BEST_KNOWN_SUFFICIENT|SPEC_SATISFIED|BUDGET|STALLED","reason":"...","evidence_ids":["..."]}
BEST_KNOWN_SUFFICIENT requires the actual best margin >= quality_target. SPEC_SATISFIED means only supported M1
constraints pass, independent of that extra quality goal. Cite current best_known for either; budget/stall claims
must match actual remaining budget or measured stalled_rounds. A legacy STOP without basis means SPEC_SATISFIED.
In FEEDBACK_REOPTIMIZATION_ACCEPTANCE mode, quality stopping requires two actual optimizations, not merely reading feedback.
First decision must propose a region. If validation_feedback is present, repair the identified error.
Never change the user's SystemSpec, model, domain or fixed inputs. Lock time, jitter and M2 cannot pass at this stage."""

TRANSPORT = Path(__file__).resolve().parents[1]/'llm_transport.py'


class ProviderError(RuntimeError):
    """Provider unavailable or failed, distinct from a repairable invalid decision."""


class InvalidResponse(ValueError):
    """Provider returned a response that is not the required decision JSON."""


class InvalidNumericResponse(InvalidResponse):
    """Nonfinite JSON is an invalid physical value, not repairable structure."""
    repairable_structure=False


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ValueError('duplicate JSON member: '+key)
        out[key] = value
    return out


def _reject_constant(value):
    raise ValueError('non-finite JSON constant: '+value)


def strict_json(text):
    parsed = json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    fingerprint(parsed)  # Also rejects nonfinite exponent overflow.
    return parsed


def validate_provider(config):
    defaults = {'provider': 'configured_messages_provider', 'model_env': 'ANTHROPIC_MODEL',
        'base_url_env': 'ANTHROPIC_BASE_URL', 'api_key_env': 'ANTHROPIC_AUTH_TOKEN',
        'auth_mode': 'bearer', 'max_tokens': 4000, 'timeout_s': 55, 'thinking': None}
    require(isinstance(config, dict) and set(config) <= set(defaults), 'Messages config accepts environment names only')
    cfg = defaults | config
    for field in ('model_env', 'base_url_env', 'api_key_env'):
        require(isinstance(cfg[field], str) and re.fullmatch('[A-Z][A-Z0-9_]{1,79}', cfg[field]),
                field+' must name an environment variable')
    require(cfg['auth_mode'] in ('bearer', 'x-api-key') and cfg['provider'] == defaults['provider'], 'unsupported Messages provider/auth')
    require(type(cfg['max_tokens']) is int and 256 <= cfg['max_tokens'] <= 16000, 'invalid max_tokens')
    require(type(cfg['timeout_s']) is int and 1 <= cfg['timeout_s'] <= 180, 'invalid timeout_s')
    require(cfg['thinking'] is None or cfg['thinking'] == {'type': 'disabled'}, 'only explicit disabled thinking option supported')
    return cfg


class LLMRegionPolicy:
    def __init__(self, config, *, prompt=None):
        self.config = validate_provider(config)
        self.prompt = PROMPT if prompt is None else prompt
        require(isinstance(self.prompt, str) and bool(self.prompt.strip()), 'nonempty policy prompt required')
        self.calls = []

    def decide(self, state, directory):
        cfg = self.config
        directory = Path(directory)
        directory.mkdir(exist_ok=False)
        keys = [cfg[k] for k in ('model_env', 'base_url_env', 'api_key_env')]
        meta = {'request_sha256': None, 'state_sha256': fingerprint(state), 'usage': None,
                'real_network_call': False, 'status': 'NOT_STARTED'}
        self.calls.append(meta)
        start = time.perf_counter()
        status_path = directory/'transport_status.json'
        try:
            missing = [name for name in keys if not os.environ.get(name)]
            if missing:
                meta.update(status='LLM_ENVIRONMENT_UNAVAILABLE', missing_environment_names=missing)
                raise ProviderError('LLM_ENVIRONMENT_UNAVAILABLE')
            request = {'model': os.environ[keys[0]], 'max_tokens': cfg['max_tokens'], 'system': self.prompt,
                       'messages': [{'role': 'user', 'content': json.dumps(state, ensure_ascii=False,
                                                                          separators=(',', ':'), allow_nan=False)}]}
            if cfg['thinking'] is not None:
                request['thinking'] = cfg['thinking']
            # Only request data and env *names* go to disk. Guard against accidentally
            # using a token as a model name or inserting it into the planner input.
            if os.environ[keys[2]] in json.dumps(request, ensure_ascii=False):
                meta['status'] = 'CREDENTIAL_IN_REQUEST_PAYLOAD'
                raise ProviderError('CREDENTIAL_IN_REQUEST_PAYLOAD')
            write_new(directory/'request.json', request)
            write_new(directory/'config.json', cfg)
            meta.update(model=request['model'], request_sha256=fingerprint(request))
            command = [sys.executable, '-B', str(TRANSPORT), '--request', str(directory/'request.json'),
                '--config', str(directory/'config.json'), '--response', str(directory/'response.json'),
                '--status', str(status_path), '--redacted-body', str(directory/'response_body.redacted.txt')]
            try:
                process = subprocess.run(command, capture_output=True, timeout=cfg['timeout_s']+2, shell=False,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            except subprocess.TimeoutExpired:
                if status_path.exists():
                    meta.update(json.loads(status_path.read_text(encoding='utf-8')))
                meta['status'] = 'LLM_TOTAL_PROCESS_TIMEOUT'
                raise ProviderError(meta['status']) from None
            if status_path.exists():
                meta.update(json.loads(status_path.read_text(encoding='utf-8')))
            meta['worker_exit_code'] = process.returncode
            if process.returncode != 0:
                if meta['status'] == 'NOT_STARTED':
                    meta['status'] = 'LLM_WORKER_FAILED_BEFORE_NETWORK'
                raise ProviderError(meta['status'])
            try:
                raw = json.loads((directory/'response.json').read_text(encoding='utf-8'))
                meta.update(usage=raw.get('usage'), response_model=raw.get('model'), response_id=raw.get('id'),
                            stop_reason=raw.get('stop_reason'))
                if raw.get('stop_reason') == 'max_tokens':
                    raise ValueError('provider response truncated at max_tokens')
                response = ''.join(x.get('text', '') for x in raw.get('content', []) if x.get('type') == 'text').strip()
                with (directory/'raw_response_text.txt').open('x',encoding='utf-8') as handle:
                    handle.write(response)
                if response.startswith('```') and response.endswith('```') and '\n' in response:
                    response = response.split('\n', 1)[1][:-3].strip()
                decision = strict_json(response)
            except (ValueError, TypeError, AttributeError, OSError) as error:
                meta['status'] = 'INVALID_LLM_RESPONSE_JSON'
                if 'non-finite' in str(error).lower() or 'nonfinite' in str(error).lower() or 'out of range float' in str(error).lower():
                    raise InvalidNumericResponse('response contains invalid nonfinite numeric values: '+str(error)) from None
                raise InvalidResponse('response is not a complete strict JSON decision: '+str(error)) from None
            write_new(directory/'raw_search_decision.json', decision)
            meta['status'] = 'RESPONDED'
            return decision
        finally:
            meta['elapsed_s'] = time.perf_counter()-start
            write_new(directory/'metadata.json', meta)
