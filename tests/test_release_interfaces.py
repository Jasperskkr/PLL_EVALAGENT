"""Responsibility names and legacy spellings use the same implementation."""
import importlib
import json
from pathlib import Path
import pytest
from pll_allocation import pipeline

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('old,new', [
    ('agent.stage9', 'agent.feedback'),
    ('verification.research', 'verification.continuous'),
    ('agent.experiment_a_plus', 'studies.initial_allocation'),
    ('agent.multi_region_study', 'studies.multi_region'),
    ('agent.spec_allocation_ablation', 'studies.ablation'),
    ('agent.spec_allocation_ablation_report', 'studies.ablation_report'),
])
def test_module_compatibility(old, new):
    assert importlib.import_module('pll_allocation.'+old) is importlib.import_module('pll_allocation.'+new)


@pytest.mark.parametrize('legacy', [False, True])
def test_initial_cli_dispatches_unchanged_arguments(monkeypatch, tmp_path, legacy):
    module = importlib.import_module('pll_allocation.agent.initial_allocation')
    captured = []
    def run(*args, **kwargs):
        captured.append((args, kwargs))
        return dict(status='TEST_DISPATCH_ONLY', strategy='TEST', cost={}, failure=None)
    monkeypatch.setattr(module, 'run_initial_allocation', run)
    names = ('--initial-allocation-problem', '--initial-allocation-config') if legacy else ('--problem', '--allocator-config')
    problem = str(ROOT/'configs/problems/nominal.json')
    config = ROOT/'configs/agent/deterministic.json'
    output = str(tmp_path/'new')
    assert pipeline.main([names[0], problem, names[1], str(config), '--out', output]) == 0
    assert captured == [((problem, output), dict(config=json.loads(config.read_text()),
                        provider_config=None, initial_context=None, feedback=None))]


@pytest.mark.parametrize('legacy', [False, True])
def test_verification_cli_dispatches_unchanged_arguments(monkeypatch, tmp_path, legacy):
    module = importlib.import_module('pll_allocation.agent.feedback')
    captured = []
    def run(*args, **kwargs):
        captured.append((args, kwargs))
        return dict(status='TEST_DISPATCH_ONLY', strategy='TEST', cost={}, failure=None)
    monkeypatch.setattr(module, 'run_feedback', run)
    names = ('--stage9-handoff', '--stage9-problem', '--stage9-config') if legacy else ('--handoff', '--verification-problem', '--verification-config')
    problem = str(ROOT/'configs/problems/nominal.json')
    config = ROOT/'configs/verification/verify_only.json'
    handoff, output = str(tmp_path/'handoff.json'), str(tmp_path/'new')
    assert pipeline.main([names[0], handoff, names[1], problem, names[2], str(config), '--out', output]) == 0
    assert captured == [((handoff, output), dict(problem_config=problem,
                        feedback_config=json.loads(config.read_text()), provider_config=None))]


def test_help_uses_responsibility_names(capsys):
    with pytest.raises(SystemExit) as result:
        pipeline.main(['--help'])
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert '--handoff HANDOFF' in help_text and '--problem PROBLEM' in help_text
    assert 'STAGE9' not in help_text and '--stage9' not in help_text
