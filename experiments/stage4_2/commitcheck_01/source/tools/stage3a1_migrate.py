"""Mechanical relocation after backup, plus independently reusable test fixtures."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
MODULES = ('core', 'physics', 'allocate', 'agent', 'repair', 'feedback_agent')


def main():
    backup = ROOT/'docs/stage3a1/pre_migration/backup_manifest.json'
    if not backup.is_file():
        raise RuntimeError('reviewable pre-migration backup required')
    rows = []

    def copy(source, target, content=None, mode='byte_identical'):
        data = source.read_bytes() if content is None else content.encode('utf-8')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        rows.append({'source': source.relative_to(ROOT).as_posix(),
            'destination': target.relative_to(ROOT).as_posix(),
            'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'destination_sha256': hashlib.sha256(data).hexdigest(), 'mode': mode,
            'domain': 'frozen Stage1.5 ideal SI domain and unchanged protocols; not circuit realization capability',
            'semantics': 'Production algorithm relocation or small historical test evidence only'})

    for name in MODULES:
        original = ROOT/'pll_allocation/track_a'/(name+'.py')
        copy(original, ROOT/'pll_allocation/allocation'/(name+'.py'))
        wrapper = ('"""Legacy import alias; implementation is owned by allocation."""\n'
            'import importlib as _importlib\nimport sys as _sys\n'
            f'_sys.modules[__name__] = _importlib.import_module("pll_allocation.allocation.{name}")\n')
        original.write_text(wrapper, encoding='utf-8')
    fixture = ROOT/'tests/fixtures/verification'
    for source, name in [('track_b/baseline/python_crosscheck.py', 'python_crosscheck.py'),
                         ('track_b/protocol.json', 'protocol_v1_0.json'),
                         ('docs/track_a/delivery_final/AllocationProposal.json', 'analytical_proposal_stage3a.json')]:
        copy(ROOT/source, fixture/name)
    # Retain compact actual Stage3A measurements; no trajectories or historical directory dependency.
    for strategy, source in [('analytical', 'experiments/stage3a_analytical_20261104_01/attempt_001/BehavioralVerificationResult.json'),
                             ('sensitivity_optimization', 'experiments/stage3a_optimization_20261104_01/attempt_001/BehavioralVerificationResult.json'),
                             ('random', 'experiments/stage3a_feedback_repair_20261104_01/attempt_001/BehavioralVerificationResult.json'),
                             ('nominal', 'track_b/outputs/interface_nominal_02/result.json')]:
        copy(ROOT/source, fixture/(strategy+'_M2_stage3a.json'))
    for name in ('test_measurements.py', 'test_verification.py'):
        source = ROOT/'track_b/tests'/name
        code = source.read_text(encoding='utf-8')
        code = code.replace('from experiments import', 'from pll_allocation.verification.experiments import')
        code = code.replace('from measure import', 'from pll_allocation.verification.measure import')
        code = code.replace('from simulator import', 'from pll_allocation.verification.simulator import')
        code = code.replace('from verify import', 'from pll_allocation.verification.verify import')
        code = code.replace('HERE,candidate,protocol,response_point', 'HERE,candidate,response_point')
        code = code.replace('HERE,candidate,read,protocol', 'HERE,candidate,read')
        code = code.replace('import pytest\n', 'import pytest\nfrom pathlib import Path\n'
            'FIXTURES = Path(__file__).resolve().parents[1]/"fixtures"\n'
            'from pll_allocation.verification.resources import CONFIGS\n'
            'from pll_allocation.verification.experiments import protocol as formal_protocol\n'
            'def protocol():\n    return __import__("json").loads((FIXTURES/"verification/protocol_v1_0.json").read_text(encoding="utf-8"))\n')
        code = code.replace("HERE/'baseline/python_crosscheck.py'", "FIXTURES/'verification/python_crosscheck.py'")
        code = code.replace("HERE/'tests/fixtures/nominal_measured.json'", "FIXTURES/'stage3a_nominal_measured.json'")
        code = code.replace("HERE/'protocol_v1_1.json'", "CONFIGS/'verification/protocol_v1_1.json'")
        copy(source, ROOT/'tests/verification'/name, code, 'imports_and_fixture_paths_only; v1.0 regression explicitly local fixture')
    bindings = json.loads((ROOT/'configs/pipeline_stage3a.json').read_text(encoding='utf-8'))['bindings']
    with (fixture/'frozen_bindings.json').open('x', encoding='utf-8') as stream:
        json.dump(bindings, stream, indent=2)
    with (ROOT/'docs/stage3a1/migration_manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(rows, stream, ensure_ascii=False, indent=2)
    print('Migrated six byte-identical implementation modules; old imports alias forward; tests/fixtures extracted')


if __name__ == '__main__':
    main()
