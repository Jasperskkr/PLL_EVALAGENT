"""Explicit lightweight source/evidence review export; excludes waveforms and credentials."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import read,write_new


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--summary',required=True,type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False);source=a.out/'source';source.mkdir()
    paths=set()
    suffixes={'.py','.cpp','.cmd','.json','.jsonl','.csv','.md','.xml','.toml','.yaml','.yml','.m','.txt','.log'}
    for folder in ('pll_allocation','configs','tests','tools','data','examples','docs/stage5'):
        for q in (ROOT/folder).rglob('*'):
            if q.is_file() and q.suffix.lower() in suffixes and not any(part in ('__pycache__','.pytest_cache','build','source','dirty_source_backup','pre_audit','source_snapshot','raw','tmp') or part.startswith('build_') for part in q.relative_to(ROOT).parts):
                paths.add(q)
    for name in ('AGENTS.md','PROJECT_CHARTER.md','P0_EXISTING_SYSTEM_AUDIT.md','P0_MODULE_REUSE_MATRIX.md','P0_TARGET_ARCHITECTURE.md','P0_MIGRATION_PLAN.md','pyproject.toml','.gitattributes','MAINLINE_ARCHITECTURE.md','docs/DECISIONS.md','docs/PROJECT_STATUS.md'):
        paths.add(ROOT/name)
    for name in ('docs/stage3a1/migration_manifest.json','docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json',
                 'docs/stage4_2/M2_VALIDATION_CANDIDATES.json','docs/stage4_2/SYSTEM_SPEC_MAPPING_MATRIX.md'):
        paths.add(ROOT/name)
    # Preserve historical small finite-registry fixtures used by the full suite.
    for q in (ROOT/'experiments/stage4_2/readiness_05').rglob('*'):
        if q.is_file() and q.suffix in ('.json','.csv','.py') and 'source_snapshot' not in q.parts:paths.add(q)
    for name in ('run_stage5.py','collect_stage5.py','audit_stage5.py','package_stage5.py','write_reports.py','experiment_plan_frozen.json'):
        paths.add(ROOT/'experiments/stage5'/name)
    paths.update((ROOT/'experiments/stage5/scenarios').glob('*.json'))
    for q in a.summary.rglob('*'):
        if q.is_file():paths.add(q.resolve())
    for folder in ('firstshot_01','repair_01'):
        for q in (ROOT/'experiments/stage5'/folder).rglob('*'):
            if (q.is_file() and q.suffix in ('.json','.jsonl','.log')
                    and not any(part in ('raw','tmp') for part in q.relative_to(ROOT/'experiments/stage5'/folder).parts)
                    and q.name!='source_manifest.json'):
                paths.add(q)
    for row in read(a.summary/'summary.json')['local_evidence']:
        case=Path(row['evidence'])
        for name in ('AllocationProposal.json','frequency_result.json','frequency_gate.json','steps/result.json'):
            paths.add(case/name)
    for folder in ('baseline_receipt_01','interface_tests_01','interface_baseline_receipt_01','firstshot_receipt_01','repair_receipt_01','local_receipt_01','local_receipt_02','final_tests_01','result_audit_01','result_audit_02','collection_receipt_01','collection_receipt_02'):
        for q in (ROOT/'experiments/stage5'/folder).glob('*'):
            if q.is_file() and q.suffix in ('.json','.md','.log','.xml'):paths.add(q)
    secrets=[os.environ[k].encode('utf-8') for k in ('ANTHROPIC_AUTH_TOKEN','ANTHROPIC_API_KEY','OPENAI_API_KEY') if len(os.environ.get(k,''))>8]
    manifest=[]
    for q in sorted(paths):
        content=q.read_bytes()
        if any(secret in content for secret in secrets):raise RuntimeError('credential bytes found; export aborted')
        target=source/q.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        manifest.append({'path':q.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)})
    write_new(a.out/'SOURCE_SHA256.json',manifest)
    write_new(source/'SOURCE_SHA256.json',manifest)
    (source/'STAGE5_REVIEW_README.md').write_text('''# Stage5 review snapshot

Source checkout export; no DLLs, raw NPZ waveforms, secrets, virtualenvs or caches. HEAD cd70cf4 plus exact Stage5 source hashes; changes are not yet a Git commit. Canonical frozen assets unchanged. Use original configs, not copied old release manifests as new version claims.

On Windows with MSVC2022 x64 and Python NumPy/SciPy/pytest dependencies:

```powershell
.\\pll_allocation\\verification\\build_kernel.cmd
.\\pll_allocation\\verification\\build_return_ratio.cmd
.\\pll_allocation\\verification\\build_closed_loop.cmd
python -B -m pytest -q tests -p no:cacheprovider
python -B -m pll_allocation pipeline --strategy analytical --scenario experiments/stage5/scenarios/S1.json --out experiments/new_stage5_reproduction
```

New outputs must not exist. Saved study files are evidence/replay, not new LLM execution. Existing configured real LLM transport reads environment values at runtime; no credential is included. Full-size raw waveforms stay in the original workspace, and native/wall costs refer to actual source runs. No wheel or cross-platform validation is implied.
''',encoding='utf-8')
    archive=a.out/'stage5_source_review.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for q in sorted(source.rglob('*')):
            if q.is_file():z.write(q,q.relative_to(source).as_posix())
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip()
        if bad:raise RuntimeError('archive CRC failed '+bad)
        for row in manifest:
            if hashlib.sha256(z.read(row['path'])).hexdigest()!=row['sha256']:raise RuntimeError('archive byte hash mismatch')
    write_new(a.out/'package_receipt.json',{'files':len(manifest),'source_bytes':sum(r['bytes'] for r in manifest),
        'archive_bytes':archive.stat().st_size,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'credential_byte_scan':'PASS_FOR_CONFIGURED_ENVIRONMENT_SECRETS','raw_binaries_excluded':True,
        'archive_crc_and_all_file_hashes':'PASS','source_export':str(source.resolve()),'wheel_installation':'NOT_EXECUTED'})
    print(json.dumps(read(a.out/'package_receipt.json'),indent=2))


if __name__=='__main__':main()
