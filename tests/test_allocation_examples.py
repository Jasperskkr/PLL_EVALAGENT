"""Public example inputs and the wrapper's authorization/CLI boundaries."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pll_allocation.agent.spec_allocation import validate_config

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('allocation_examples', ROOT / 'tools/run_allocation_examples.py')
EXAMPLES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXAMPLES)


def test_all_public_examples_use_valid_current_inputs():
    manifest = EXAMPLES.read(EXAMPLES.MANIFEST)
    base = EXAMPLES.read(ROOT / manifest['base_config'])
    for case in manifest['cases'].values():
        assert (ROOT / case['problem']).is_file()
        config = validate_config(base | case['overrides'])
        assert config['allow_paid_llm'] is False
    assert (ROOT / manifest['provider_config']).is_file()


def test_llm_examples_cannot_run_without_authorization_or_environment(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('subprocess must not run during failed preflight')
    monkeypatch.setattr(EXAMPLES.subprocess, 'run', forbidden)
    out = tmp_path / 'fresh'
    with pytest.raises(ValueError, match='authorization'):
        EXAMPLES.run_cases(['llm'], out)
    monkeypatch.delenv('ANTHROPIC_AUTH_TOKEN', raising=False)
    with pytest.raises(ValueError, match='ANTHROPIC_AUTH_TOKEN'):
        EXAMPLES.run_cases(['llm'], out, allow_paid_llm=True)
    assert not out.exists()


def test_wrapper_invokes_only_official_cli_and_preserves_failure(tmp_path, monkeypatch):
    calls = []
    def execute(command, **kwargs):
        calls.append(command)
        assert command[1:4] == ['-m', 'pll_allocation', 'pipeline']
        config = EXAMPLES.read(command[command.index('--allocator-config') + 1])
        assert config['mode'] == 'AUTO_HYBRID' and not config['allow_paid_llm']
        assert '--llm-config' not in command
        return SimpleNamespace(returncode=2)
    monkeypatch.setattr(EXAMPLES.subprocess, 'run', execute)
    out = tmp_path / 'fresh'
    assert EXAMPLES.main(['--case', 'auto', '--out', str(out)]) == 2
    saved = json.loads((out / 'summary.json').read_text(encoding='utf-8'))['cases'][0]
    assert saved['status'] == 'NO_RESULT' and saved['M2_supported_pass_count'] is None
    with pytest.raises(FileExistsError):
        EXAMPLES.run_cases(['auto'], out)
    assert len(calls) == 1


def test_authorization_applies_only_to_selected_llm_cases(tmp_path, monkeypatch):
    for name in ('ANTHROPIC_MODEL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL'):
        monkeypatch.setenv(name, 'TEST_VALUE_NOT_A_CREDENTIAL')
    configs = []
    def execute(command, **kwargs):
        config = EXAMPLES.read(command[command.index('--allocator-config') + 1])
        configs.append(config)
        assert ('--llm-config' in command) == config['allow_paid_llm']
        return SimpleNamespace(returncode=2)
    monkeypatch.setattr(EXAMPLES.subprocess, 'run', execute)
    EXAMPLES.run_cases(['auto', 'llm', 'auto_trigger'], tmp_path / 'fresh', allow_paid_llm=True)
    assert [c['allow_paid_llm'] for c in configs] == [False, True, True]
    assert [c['llm_budget'] for c in configs] == [4, 4, 2]


@pytest.mark.parametrize('names', [[], ['nominal', 'nominal'], ['missing']])
def test_invalid_selections_leave_output_untouched(tmp_path, names):
    with pytest.raises(ValueError):
        EXAMPLES.run_cases(names, tmp_path / 'fresh')
    assert not (tmp_path / 'fresh').exists()
