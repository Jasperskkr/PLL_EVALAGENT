"""First handoff and later pool picks share one opt-in physics ordering."""
from copy import deepcopy
import json

from pll_allocation.agent.candidate_pool import select_m2
from pll_allocation.agent.spec_allocation import run_spec_allocation, validate_config, pool_config, rows
from pll_allocation.agent.physics_ranking import choose_physics_candidate
from pll_allocation.exploration.conditional_physics import ConditionalPhysics
from pll_allocation.exploration.contracts import load_problem


CONFIG = {'schema_version': 'pll-spec-allocation-1.0', 'target_count': 3, 'm1_budget': 48,
    'initial_search_m1_budget': 24, 'm2_budget': 2, 'm2_target_count': 2,
    'initial_state_aware_enabled': True, 'physics_ranking_enabled': True}


def test_initial_and_subsequent_selection_use_same_strategy(tmp_path):
    from test_verification_feedback import fake_m2
    invoked = []
    def backend(req, out):
        invoked.append(req['candidate_sha256'])
        return fake_m2(lock=54e-6)(req, out)
    result = run_spec_allocation('configs/problems/nominal.json', tmp_path/'run', config=CONFIG, m2_executor=backend)
    problem = load_problem('configs/problems/nominal.json'); cfg = pool_config(validate_config(CONFIG))
    ledger = rows(tmp_path/'run/initial/candidate_archive.jsonl')
    first = select_m2(ledger, problem, cfg)
    assert invoked[0] == first['parameter_sha256']
    second = select_m2(ledger, problem, cfg, [first])
    assert invoked[1] == second['parameter_sha256']
    h = json.loads((tmp_path/'run/initial/verification_handoff.json').read_text())
    assert h['selection_evidence'] == first['physics_selection']
    events = rows(tmp_path/'run/verification/verification_run_events.jsonl')
    # Native execution is injected TEST only; the ranking and audit paths are real.
    assert result['cost']['M2_verifications'] == 2 and not result['FULL_SYSTEMSPEC_CERTIFIED']


def test_missing_predictions_keep_candidates_and_explicit_legacy_fallback(tmp_path, monkeypatch):
    cfg = CONFIG | {'m2_budget': 0}
    result = run_spec_allocation('configs/problems/nominal.json', tmp_path/'run', config=cfg)
    problem = load_problem('configs/problems/nominal.json'); pool = pool_config(validate_config(cfg))
    eligible = result['candidates']
    monkeypatch.setattr(ConditionalPhysics, 'describe', lambda self, c: {})
    chosen = select_m2(eligible, problem, pool)
    oldpool = deepcopy(pool); oldpool.pop('physics_options')
    original = select_m2(eligible, problem, oldpool)
    assert chosen is not None and chosen['parameter_sha256'] == original['parameter_sha256']
    assert chosen['physics_selection']['legacy_fallback']
    assert chosen['physics_selection']['eligible_count'] > 0


def test_quality_and_distance_gates_survive_physics_ranking(tmp_path):
    cfg = CONFIG | {'m2_budget': 0}
    r = run_spec_allocation('configs/problems/nominal.json', tmp_path/'run', config=cfg)
    problem = load_problem('configs/problems/nominal.json'); pool = pool_config(validate_config(cfg))
    assert select_m2(r['candidates'], problem, pool | {'minimum_margin': 100}) is None
    selected = select_m2(r['candidates'], problem, pool)
    assert select_m2([selected], problem, pool, [selected]) is None


def test_conditional_pass_is_not_hidden_by_nearby_higher_m1_margin(tmp_path):
    from pll_allocation.physics_mapping.model import fingerprint
    result = run_spec_allocation('configs/problems/nominal.json', tmp_path/'base',
        config={'schema_version': 'pll-spec-allocation-1.0', 'target_count': 1, 'm2_budget': 0})
    a = deepcopy(result['candidates'][0]); b = deepcopy(a)
    b['parameters']['values']['Icp']['value'] *= 1.01
    b['parameters']['values']['Kvco']['value'] /= 1.01
    b['parameter_sha256'] = fingerprint(b['parameters'])
    b['judgment']['minimum_normalized_margin'] -= .001
    problem = load_problem('configs/problems/nominal.json')
    cfg = pool_config(validate_config(CONFIG | {'noise_allocation_enabled': True}))
    physics = ConditionalPhysics(problem, cfg['physics_options'])
    ja, jb = (physics.describe(r['parameters'])['predicted_jitter_s'] for r in (a, b))
    assert jb < ja
    next(s for s in problem['specs'] if s['metric'] == 'jitter_s')['max'] = (ja+jb)/2
    assert select_m2([a, b], problem, cfg)['parameter_sha256'] == b['parameter_sha256']
