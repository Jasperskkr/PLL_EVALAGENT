"""Route selection must not silently fall back, discard options or mask failures."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pll_allocation import pipeline
from pll_allocation.agent.spec_allocation import search_config, validate_config
from pll_allocation.agent.physics_tool_policy import validate_config as validate_search

ROOT = Path(__file__).resolve().parents[1]
PROBLEM = str(ROOT/'configs/problems/nominal.json')


def fake_run(calls, **updates):
    def run(*args, **kwargs):
        calls.append((args, kwargs))
        Path(args[1] if 'config' in kwargs else args[0]).mkdir()
        return {'status': 'M1_POOL_ONLY', 'strategy': 'DETERMINISTIC', 'cost': {}, 'failure': None} | updates
    return run


@pytest.mark.parametrize('explicit_problem', [False, True])
def test_default_and_problem_only_dispatch_new_multi_candidate(monkeypatch, tmp_path, explicit_problem):
    from pll_allocation.agent import spec_allocation
    calls = []
    monkeypatch.setattr(spec_allocation, 'run_spec_allocation', fake_run(calls))
    monkeypatch.setattr(pipeline, 'run_pipeline', lambda *a, **k: pytest.fail('old fallback forbidden'))
    out = tmp_path/'run'
    args = ['--out', str(out)] + (['--problem', PROBLEM] if explicit_problem else [])
    assert pipeline.main(args) == 0
    assert Path(calls[0][0][0]).resolve() == Path(PROBLEM)
    assert calls[0][1]['config']['schema_version'] == 'pll-spec-allocation-1.0'
    assert calls[0][1]['config']['allow_paid_llm'] is False
    receipt = json.loads((out/'execution_route.json').read_text(encoding='utf-8'))
    assert receipt['execution_route'] == 'CONTINUOUS_SPEC_ALLOCATION' and not receipt['compatibility_route']


@pytest.mark.parametrize('options', [
    ['--strategy', 'llm_agent'], ['--strategy', 'analytical'], ['--config', 'missing.json'],
    ['--m2-budget', '0'], ['--repair-budget', '0'], ['--proposal', 'missing.json'],
    ['--seed', '0'], ['--llm-config', 'missing.json'], ['--method', 'A'],
    ['--allocator-config', 'missing.json'],
    ['--problem', PROBLEM, '--strategy', 'analytical'],
    ['--problem', PROBLEM, '--m2-budget', '0'],
    ['--problem', PROBLEM, '--legacy-frozen'],
    ['--explore-problem', PROBLEM, '--feedback-from', 'missing'],
    ['--explore-problem', PROBLEM, '--llm-config', 'missing.json'],
    ['--region-context', 'missing', '--search-decisions', 'missing', '--region-m1-budget', '1',
     '--feedback-from', 'missing'],
    ['--llm-region-context', 'missing', '--planner-config', 'missing', '--subregion-config', 'missing'],
    ['--multispec', 'missing', '--exploration-budget', '0'],
])
def test_invalid_or_cross_route_options_fail_before_output_or_provider(tmp_path, monkeypatch, options):
    monkeypatch.setattr(pipeline, 'read', lambda *a: pytest.fail('invalid route must fail before reading any input'))
    out = tmp_path/'untouched'
    assert pipeline.main(['--out', str(out), *options]) == 2
    assert not out.exists()


def test_old_frozen_cli_requires_explicit_opt_in(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(pipeline, 'run_pipeline', fake_run(calls, execution_route='LEGACY_FROZEN'))
    out = tmp_path/'legacy'
    assert pipeline.main(['--legacy-frozen', '--out', str(out)]) == 0
    assert calls[0][0] == (str(out), 'analytical')
    assert json.loads((out/'execution_route.json').read_text())['compatibility_route']


def test_partial_result_preserves_provider_failure_and_nonzero_exit(monkeypatch, tmp_path):
    from pll_allocation.agent import spec_allocation
    calls = []
    failure = {'type': 'ProviderError', 'reason': 'REAL_LLM_NOT_AUTHORIZED'}
    monkeypatch.setattr(spec_allocation, 'run_spec_allocation', fake_run(calls, failure=failure))
    out = tmp_path/'partial'
    assert pipeline.main(['--out', str(out)]) == 2
    assert json.loads((out/'execution_route.json').read_text())['failure'] == failure


@pytest.mark.parametrize('command', ['run', 'suite'])
def test_historical_v1_cli_requires_explicit_opt_in(tmp_path, command):
    out = tmp_path/'v1'
    args = [sys.executable, '-m', 'pll_allocation', command, '--out', str(out)]
    if command == 'run':
        args += ['--problem', 'missing.json']
    done = subprocess.run(args, cwd=ROOT, capture_output=True, encoding='utf-8')
    assert done.returncode == 2 and '--legacy-v1' in done.stderr
    assert not out.exists()


@pytest.mark.parametrize('mode', ['DETERMINISTIC', 'AUTO_HYBRID', 'LLM_PHYSICS_GUIDED'])
def test_nested_pool_cannot_conflict_with_policy(mode):
    config = validate_config({'schema_version': 'pll-spec-allocation-1.0', 'mode': mode})
    child = search_config(config, 32)
    validate_search(child)
    child['policy'] = ('LLM_PHYSICS_TOOL' if child['policy'] == 'DETERMINISTIC_PHYSICS_TOOL'
                       else 'DETERMINISTIC_PHYSICS_TOOL')
    with pytest.raises(ValueError, match='conflicts'):
        validate_search(child)
