"""One-time audited extraction; all destinations must be new. Run at project root."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.physics_mapping.model import fingerprint


def main():
    src = ROOT/'track_b'
    dst = ROOT/'pll_allocation/verification'
    dst.mkdir(exist_ok=False)
    rows = []

    def save(origin, target, data, semantics):
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        rows.append({'source': str(origin.resolve()), 'destination': str(target.resolve()),
                     'source_sha256': hashlib.sha256(origin.read_bytes()).hexdigest(),
                     'destination_sha256': hashlib.sha256(data).hexdigest(),
                     'mode': 'byte_identical' if data == origin.read_bytes() else 'adapted',
                     'domain': 'unchanged Stage1.5 ideal SI domain; protocol1.1; Windows native event model',
                     'semantics': semantics})

    for name in ('simulator.py', 'measure.py', 'experiments.py', 'run_suite.py', 'verify.py'):
        code = (src/name).read_text(encoding='utf-8')
        code = re.sub(r'from (experiments|simulator|measure|run_suite) import', r'from .\1 import', code)
        code = re.sub(r'^ *if str\(HERE.parent\) not in sys.path: *sys.path.insert\(0,str\(HERE.parent\)\)\n', '', code, flags=re.M)
        code = code.replace("    if str(HERE.parent) not in sys.path:\n        sys.path.insert(0,str(HERE.parent))\n", '')
        code = code.replace("    if str(HERE.parent) not in sys.path: sys.path.insert(0,str(HERE.parent))\n", '')
        code = code.replace("from pathlib import Path", "from pathlib import Path\nfrom .resources import CONFIGS")
        code = code.replace("HERE/'baseline/BLOCK_SPACE_MODEL_V1.json'", "CONFIGS/'BLOCK_SPACE_MODEL_V1.json'")
        code = code.replace("HERE/'protocol_v1_1.json'", "CONFIGS/'verification/protocol_v1_1.json'")
        code = code.replace("HERE/'protocol.json'", "CONFIGS/'verification/protocol_v1_1.json'")
        if name == 'simulator.py':
            code = code.replace("    lib=ctypes.CDLL(str(library)); fn=lib.simulate", "    from .build_identity import check_build\n    check_build()\n    lib=ctypes.CDLL(str(library)); fn=lib.simulate")
        elif name == 'experiments.py':
            code = code[:code.index('\ndef pilot(')] + '\n'
        elif name == 'run_suite.py':
            start = code.index('def comparison_after_measurement(')
            stop = code.index('\ndef run_frequency_suite(')
            capture = code[code.index('def capture_pair('):code.index('\ndef run_capture_suite(')]
            code = ('"""Extracted Track B convergence comparison and paired capture; no suite/history reads."""\n'
                    'from pathlib import Path\n'
                    'from .experiments import compare_sweeps, protocol, save_run, write\n\n'
                    + code[start:stop] + '\n\n' + capture)
            code = code.replace('def comparison_after_measurement(p,measurements):',
                                'def comparison_after_measurement(p,measurements,*,protocol_document=None):')
            code = code.replace("cfg=protocol()['frequency_response']", "cfg=(protocol_document or protocol())['frequency_response']")
        elif name == 'verify.py':
            code = code[:code.index("\nif __name__=='__main__':")] + '\n'
            code = code.replace('comparison_after_measurement(p,responses)', 'comparison_after_measurement(p,responses,protocol_document=doc)')
        save(src/name, dst/name, code.encode('utf-8'),
             'Package-relative imports/config paths; remove research CLI/suite; preserve numerical operations and judgment')
    for name in ('kernel.cpp', 'build_kernel.cmd'):
        data = (src/name).read_bytes()
        if name.endswith('.cmd'):
            data += b'\r\nif errorlevel 1 exit /b 1\r\npython "%~dp0build_identity.py"\r\n'
        save(src/name, dst/name, data, 'Unchanged kernel; build command additionally records source/binary binding')
    save(src/'build/kernel.dll', dst/'build/kernel.dll', (src/'build/kernel.dll').read_bytes(),
         'Audited existing MSVC DLL; source and binary identities independently bound before use')
    save(src/'protocol_v1_1.json', ROOT/'configs/verification/protocol_v1_1.json',
         (src/'protocol_v1_1.json').read_bytes(), 'Unchanged formal Track B protocol1.1')
    model = json.loads((ROOT/'configs/BLOCK_SPACE_MODEL_V1.json').read_text(encoding='utf-8'))
    doc = json.loads((src/'protocol_v1_1.json').read_text(encoding='utf-8'))
    old_doc = json.loads((src/'protocol.json').read_text(encoding='utf-8'))
    for key in ('max_BW_refinement_relative_difference', 'max_transfer_refinement_relative_difference',
                'max_transfer_refinement_phase_deg'):
        assert old_doc['frequency_response'][key] == doc['frequency_response'][key]
    with (ROOT/'configs/SYSTEM_SPEC_STAGE1_5.json').open('x', encoding='utf-8') as stream:
        json.dump(model['experiment']['system_spec'], stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    config = {'schema_version': 'pll-unified-pipeline-1.0', 'model': 'BLOCK_SPACE_MODEL_V1.json',
              'system_spec': 'SYSTEM_SPEC_STAGE1_5.json', 'equations': 'PLL_EQUATION_REGISTRY_V1.json',
              'protocol': 'verification/protocol_v1_1.json',
              'bindings': {'model_sha256': fingerprint(model), 'versions': model['versions'],
                           'system_spec_sha256': fingerprint(model['experiment']['system_spec']),
                           'protocol_sha256': fingerprint(doc),
                           'equations_sha256': fingerprint(json.loads((ROOT/'configs/PLL_EQUATION_REGISTRY_V1.json').read_text(encoding='utf-8'))),
                           'kernel_sha256': hashlib.sha256((dst/'kernel.cpp').read_bytes()).hexdigest()},
              'budgets': {'cheap_calls': 2000, 'M1_calls': 16, 'M2_verifications': 1, 'feedback_repairs': 0},
              'seed': 23, 'llm': json.loads((ROOT/'configs/track_a/benchmark_plan.json').read_text(encoding='utf-8'))['llm']}
    with (ROOT/'configs/pipeline_stage3a.json').open('x', encoding='utf-8') as stream:
        json.dump(config, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    with (ROOT/'docs/stage3a/reuse_manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(rows, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print('Extracted', len(rows), 'audited artifacts; no historical output copied')


if __name__ == '__main__':
    main()
