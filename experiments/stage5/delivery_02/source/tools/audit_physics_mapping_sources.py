"""Read-only source audit for Stage 1; all generated files refuse overwrite."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATLAB_FILES = {
    'graph/factor_registry.m': 'factor IDs and equations; adapt five factors only',
    'graph/variable_registry.m': 'unit and variable semantics; audit reference',
    'model/pll_params.m': 'ideal defaults; declared functional domain, not silicon capability',
    'model/pll_linear_kernel.m': 'continuous locked small-signal transfer equations; adapted',
    'model/solve_tuning_point.m': 'monotonic VCO lock point; linear subset adapted',
    'characterization/characterize_loop.m': 'crossing definitions; log-grid search adapted with bisection',
    'model/validate_pll_params.m': 'positive monotonic VCO domain; audit reference',
    'model/vco_model.m': 'zero-voltage frequency intercept and local derivative',
    'model/pfd_cp_event_step.m': 'directional currents, signed injected leakage and reset semantics',
    'model/pll_behavioral_model.m': 'reference minus divided phase; no transient code reused',
    'model/loop_filter_model.m': 'C1 shunt, series Rz-C2 branch KCL',
    'factors/pll_default_specs.m': 'historical illustrative targets, not new SystemSpec',
    'experiments/exp_icp_sweep.m': 'historical declared sweep, not supported circuit range',
    'experiments/exp_lf_sweep.m': 'historical declared sweep, not supported circuit range',
    'experiments/exp_kvco_sweep.m': 'historical declared sweep, not supported circuit range',
    'verification/python_crosscheck.py': 'historical independent Python equations, not executed here',
    'results/python_crosscheck_results.json': 'historical Python anchor, NOT MATLAB Runtime evidence',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def audit(matlab_root, out):
    matlab_root = Path(matlab_root).resolve(strict=True)
    sources = []
    for relative, semantic in MATLAB_FILES.items():
        p = matlab_root / relative
        sources.append({'path': str(p), 'sha256': sha(p), 'mode': 'read_only_formula_reference',
                        'domain': 'ideal behavioral CPPLL; no implementation claim', 'semantic': semantic})
    for relative in ['pll_allocation/contracts.py', 'pll_allocation/behavioral.py',
                     'pll_allocation/_legacy/physics/cp.py', 'pll_allocation/_legacy/physics/lf.py',
                     'pll_allocation/_legacy/evaluation/python_behavioral.py']:
        p = ROOT / relative
        sources.append({'path': str(p), 'sha256': sha(p), 'mode': 'read_only_semantic_comparison',
                        'domain': 'frozen v1 contract and sampled charge/RC behavioral model',
                        'semantic': 'no imports or edits in Stage 1; see VARIABLE_SEMANTICS.md'})
    # Preserve every pre-existing file in protected local trees and entire MATLAB project.
    protected = []
    paths = [p for tree in ['pll_allocation', 'tests', 'examples', 'configs', 'data', 'outputs']
             for p in (ROOT/tree).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    paths += [ROOT/'PROJECT_CHARTER.md', ROOT/'AGENTS.md', ROOT/'pyproject.toml']
    paths += [p for p in matlab_root.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for p in sorted(set(paths)):
        protected.append({'path': str(p), 'sha256': sha(p)})
    Path(out).mkdir(parents=True, exist_ok=False)
    write_new(Path(out)/'source_manifest.json', {'matlab_root': str(matlab_root), 'sources': sources,
              'scope': 'source review and formula adaptation only; MATLAB Runtime not executed'})
    write_new(Path(out)/'protected_before.json', protected)
    print(f'Audited {len(sources)} sources; fingerprinted {len(protected)} protected files: {out}')


def verify(before, out):
    rows = json.loads(Path(before).read_text(encoding='utf-8'))
    changed = [row['path'] for row in rows if not Path(row['path']).is_file() or sha(Path(row['path'])) != row['sha256']]
    write_new(Path(out), {'checked_files': len(rows), 'changed_or_missing': changed,
                         'status': 'UNCHANGED' if not changed else 'CHANGED'})
    if changed:
        raise SystemExit('protected files changed: ' + repr(changed))
    print(f'UNCHANGED: {len(rows)} protected files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab-root')
    parser.add_argument('--out', required=True)
    parser.add_argument('--verify-before')
    args = parser.parse_args()
    if args.verify_before:
        verify(args.verify_before, args.out)
    else:
        audit(args.matlab_root, args.out)
