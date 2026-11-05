"""Read-only research mapping index. It neither changes a model nor executes a solver."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import re

from pll_allocation.block_space.contracts import load_model
from .model import fingerprint

ROOT = Path(__file__).resolve().parents[2]
CAPABILITIES = {'ANALYTICAL_INVERSE', 'NUMERICAL_INVERSE', 'PHYSICS_SCREENING',
                'BEHAVIORAL_ONLY', 'UNSUPPORTED'}
REQUIRED = {'system_metric_id', 'unit', 'enabled_in_frozen_SystemSpec', 'definition',
            'related_block_variables', 'equation_ids', 'forward_model', 'inverse_capability',
            'constraint_propagation_method', 'supported_domain', 'verification_evidence',
            'model_limitations', 'available_solver_tool', 'confidence_status'}


def load_registry(path, *, root=ROOT):
    root = Path(root).resolve()
    item = json.loads(Path(path).read_text(encoding='utf-8'))
    if item.get('schema_version') != 'pll-physics-mapping-registry-0.1' or item.get('status') != 'RESEARCH_REVIEW_ONLY':
        raise ValueError('unsupported research registry schema/status')
    if item.get('replaces_formal_model') is not False:
        raise ValueError('registry cannot replace the frozen model')
    expected = {'configs/BLOCK_SPACE_MODEL_V1.json', 'configs/SYSTEM_SPEC_STAGE1_5.json',
        'configs/PLL_EQUATION_REGISTRY_V1.json', 'configs/verification/protocol_v1_1.json',
        'pll_allocation/physics_mapping/model.py', 'pll_allocation/physics_mapping/validation.py',
        'pll_allocation/block_space/contracts.py', 'pll_allocation/allocation/physics.py',
        'pll_allocation/allocation/allocate.py', 'pll_allocation/allocation/core.py',
        'pll_allocation/verification/verify.py', 'pll_allocation/verification/kernel.cpp',
        'pll_allocation/verification/simulator.py', 'pll_allocation/_legacy/physics/cp.py'}
    bindings = item.get('source_bindings', [])
    if {row['path'] for row in bindings} != expected or len(bindings) != len(expected):
        raise ValueError('incomplete or unexpected frozen source bindings')
    binding_checks=[]
    for row in bindings:
        if (row.get('byte_policy') != 'EXACT_OR_CRLF_LF_EQUIVALENT'
                or not all(re.fullmatch('[0-9a-f]{64}', row.get(key,'')) for key in ('sha256','normalized_lf_sha256'))):
            raise ValueError('invalid source hash/byte policy')
        content=(root/row['path']).read_bytes()
        exact=hashlib.sha256(content).hexdigest()==row['sha256']
        if hashlib.sha256(content.replace(b'\r\n',b'\n')).hexdigest()!=row['normalized_lf_sha256']:
            raise ValueError('registry source binding mismatch: '+row['path'])
        binding_checks.append({'path':row['path'],'match':'EXACT_BYTES' if exact else 'EXPLICIT_CRLF_LF_EQUIVALENCE'})
    model = load_model(root/'configs/BLOCK_SPACE_MODEL_V1.json')
    if item['model_versions'] != model['versions'] or item['block_space_sha256'] != fingerprint(model):
        raise ValueError('registry model version/hash mismatch')
    if item['system_spec_sha256'] != fingerprint(model['experiment']['system_spec']):
        raise ValueError('registry SystemSpec mismatch')
    equation_ids = {e['equation_id'] for e in json.loads((root/'configs/PLL_EQUATION_REGISTRY_V1.json').read_text(encoding='utf-8'))['equations']}
    equation_ids |= {e['equation_id'] for e in item['research_relations']}
    metrics = item['mappings']; ids = [row['system_metric_id'] for row in metrics]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate metric mapping')
    enabled = {s['metric'] for s in model['experiment']['system_spec']['metrics']}
    if {r['system_metric_id'] for r in metrics if r['enabled_in_frozen_SystemSpec']} != enabled:
        raise ValueError('registry silently changed active SystemSpec constraints')
    for row in metrics:
        if not REQUIRED <= row.keys() or row['inverse_capability'] not in CAPABILITIES:
            raise ValueError('incomplete mapping/capability')
        if not set(row['equation_ids']) <= equation_ids:
            raise ValueError('unknown equation ID')
        if not set(row['related_block_variables']) <= model['variables'].keys():
            raise ValueError('unknown block variable')
    item['runtime_binding_checks']=binding_checks
    return item


def query(registry, metric_id):
    row = next((r for r in registry['mappings'] if r['system_metric_id'] == metric_id), None)
    if row is None:
        raise ValueError('unknown metric: '+metric_id)
    return deepcopy(row)


def route(registry, metric_id):
    row = query(registry, metric_id)
    kind = row['inverse_capability']
    return {'system_metric_id': metric_id, 'inverse_capability': kind,
            'enabled_in_frozen_SystemSpec': row['enabled_in_frozen_SystemSpec'],
            'suggested_tools': deepcopy(row['available_solver_tool']),
            'action': {'ANALYTICAL_INVERSE': 'solve conditional algebra, then check full SI domain and M1',
                       'NUMERICAL_INVERSE': 'propagate necessary constraints, use existing bounded M1 solver, then independent M2',
                       'PHYSICS_SCREENING': 'apply necessary conditions only; do not promise feasibility or measured accuracy',
                       'BEHAVIORAL_ONLY': 'screen tuning/domain, then request unchanged full M2 at declared initial conditions',
                       'UNSUPPORTED': 'report missing definition/mechanism; do not allocate or certify'}[kind],
            'executes_solver': False, 'may_change_SystemSpec': False,
            'model_versions':deepcopy(registry['model_versions']),
            'source_binding_checks':deepcopy(registry['runtime_binding_checks']),
            'may_issue_behavioral_PASS': False, 'model_limitations': row['model_limitations']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', required=True, type=Path)
    parser.add_argument('--metric', required=True)
    parser.add_argument('--route', action='store_true')
    args = parser.parse_args()
    registry = load_registry(args.registry)
    print(json.dumps(route(registry, args.metric) if args.route else query(registry, args.metric),
                     ensure_ascii=False, indent=2))
