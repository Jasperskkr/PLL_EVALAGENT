"""Verify protected inputs and create fresh audit delivery records; never run TB."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.verification.build_identity import check_build


def sha(path):
    item = Path(path)
    return hashlib.sha256(item.read_bytes()).hexdigest() if item.is_file() else None


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    for target in ('PROTECTION.json', 'DELIVERY_MANIFEST.json'):
        if (OUT / target).exists():
            raise FileExistsError(f'refusing overwrite: {OUT / target}')
    before = read(OUT / 'snapshot_01/protected_before.json')
    sources = read(OUT / 'snapshot_01/source_manifest.json')
    snapshot = read(OUT / 'snapshot_01/audit_snapshot.json')
    tracked_changes = [entry['path'] for entry in before
                       if sha(ROOT / entry['path']) != entry['sha256']]
    source_changes = [entry['absolute_path'] for entry in sources
                      if sha(entry['absolute_path']) != entry['sha256']]
    upstream = [{**entry, 'final_sha256': sha(entry['path']),
                 'final_match': sha(entry['path']) == entry['registered_sha256']}
                for entry in snapshot['upstream_matlab_source_checks']]
    provenance = read(ROOT / 'data/behavioral_space_v1/reference/provenance.json')
    reference = {path: sha(path) == provenance['sha256'] for path in
                 snapshot['historical_python_event_reference_checks']}
    xml = ET.parse(OUT / 'tests_01.xml').getroot()
    suites = [xml] if xml.tag == 'testsuite' else list(xml.iter('testsuite'))
    tests = {key: sum(int(suite.get(key, '0')) for suite in suites)
             for key in ('tests', 'failures', 'errors', 'skipped')}
    identity = check_build()
    passed = (not tracked_changes and not source_changes
              and all(entry['final_match'] for entry in upstream)
              and all(reference.values())
              and tests == {'tests': 85, 'failures': 0, 'errors': 0, 'skipped': 0})
    result = {
        'status': 'PASS' if passed else 'FAIL',
        'date': '2026-11-06 Asia/Shanghai',
        'tracked_entry_count': len(before),
        'initially_missing_count': sum(entry['sha256'] is None for entry in before),
        'tracked_content_or_missing_state_changes': tracked_changes,
        'key_source_count': len(sources), 'key_source_changes': source_changes,
        'upstream_matlab_sources': upstream,
        'historical_python_event_reference_checks': reference,
        'native_binary_identity': identity, 'tests': tests,
        'new_full_M2_runs': 0, 'new_native_runs': 0,
        'new_LLM_calls': 0, 'MATLAB_runtime_calls': 0,
        'new_outputs_scope': str(OUT),
        'limitation': 'source/evidence audit and targeted unit regression; no new full behavioral certification',
    }
    write_new(OUT / 'PROTECTION.json', result)
    files = [{'path': str(path.relative_to(ROOT)), 'sha256': sha(path)}
             for path in sorted(OUT.rglob('*')) if path.is_file()
             and path.name != 'DELIVERY_MANIFEST.json']
    write_new(OUT / 'DELIVERY_MANIFEST.json', {
        'self_excluded': True, 'file_count': len(files), 'files': files})
    print(json.dumps({key: result[key] for key in (
        'status', 'tracked_entry_count', 'initially_missing_count',
        'tracked_content_or_missing_state_changes', 'key_source_count',
        'key_source_changes', 'tests', 'new_full_M2_runs', 'new_native_runs')},
        ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
