"""Release checks: ownership, preserved algorithms and absence of legacy runtime imports."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('core', 'physics', 'allocate', 'agent', 'repair', 'feedback_agent')


@pytest.mark.parametrize('name', NAMES)
def test_legacy_import_is_same_formal_module(name):
    assert importlib.import_module('pll_allocation.track_a.'+name) is importlib.import_module('pll_allocation.allocation.'+name)


def test_dependency_direction_and_frozen_numerical_implementations():
    from tools.audit_mainline import audit
    result = audit(ROOT)
    assert result['passed'], result


def test_formal_runtime_with_legacy_imports_blocked():
    script = '''
import importlib.abc, sys
class BlockLegacy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "track_b" or fullname.startswith("track_b.") or fullname == "pll_allocation.track_a" or fullname.startswith("pll_allocation.track_a."):
            raise AssertionError("forbidden legacy import: "+fullname)
sys.meta_path.insert(0, BlockLegacy())
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.allocation.allocate import allocate
from pll_allocation.allocation.core import Meter, assess_m1, proposal
from pll_allocation.verification.verify import validate_proposal
from pll_allocation.verification.simulator import simulate
_, model, spec, _ = load_inputs()
meter = Meter()
candidate, meta = allocate("analytical", model, spec, meter, 23)
item = proposal(model, spec, candidate, "analytical", assess_m1(model, spec, candidate, meter), meta, "no-legacy")
validate_proposal(item)
run = simulate(candidate, duration_s=1e-6, onset_s=1e-6)
assert run["summary"]["integration_points"] > 0
print("FORMAL_M1_AND_NATIVE_M2_WITH_LEGACY_IMPORTS_BLOCKED")
'''
    result = subprocess.run([sys.executable, '-B', '-c', script], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert 'FORMAL_M1_AND_NATIVE_M2' in result.stdout


def test_build_refuses_existing_destination_without_overwrite(tmp_path):
    if sys.platform != 'win32':
        pytest.skip('Windows native build contract')
    folder = tmp_path/'existing'
    folder.mkdir()
    sentinel = folder/'kernel.dll'
    sentinel.write_bytes(b'unchanged sentinel')
    result = subprocess.run(['cmd', '/c', str(ROOT/'pll_allocation/verification/build_kernel.cmd'), str(folder)], capture_output=True)
    assert result.returncode == 2
    assert sentinel.read_bytes() == b'unchanged sentinel'


def test_formal_agent_transport_timeout_costed_without_fallback_or_secret(tmp_path, monkeypatch):
    from pll_allocation.allocation import agent
    from pll_allocation.allocation.core import Meter
    for key, value in [('UNIT_MODEL', 'test-model'), ('UNIT_URL', 'http://unused.invalid'),
                       ('UNIT_KEY', 'sentinel-secret-for-test')]:
        monkeypatch.setenv(key, value)
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('test transport', .01)
    monkeypatch.setattr(agent.subprocess, 'run', timeout)
    meter = Meter()
    policy = agent.MessagesPolicy({'model_env': 'UNIT_MODEL', 'base_url_env': 'UNIT_URL',
        'api_key_env': 'UNIT_KEY', 'timeout_s': .01}, tmp_path/'calls', meter)
    with pytest.raises(RuntimeError, match='LLM_TOTAL_PROCESS_TIMEOUT'):
        policy.decide({})
    assert meter.counts['LLM_calls'] == 1 and meter.counts['M1_calls'] == 0
    assert policy.calls[0]['status'] == 'TOTAL_PROCESS_TIMEOUT'
    assert all(b'sentinel-secret-for-test' not in p.read_bytes() for p in tmp_path.rglob('*') if p.is_file())
