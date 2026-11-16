"""Active configuration relocation and non-overwriting maintenance contracts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT=Path(__file__).resolve().parents[1]


def test_all_active_json_configs_are_installed_in_their_own_directory():
    project=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))
    groups=project['tool']['setuptools']['data-files']
    actual={}
    for destination,names in groups.items():
        for name in names:
            assert (ROOT/name).is_file()
            actual[name]=destination
    expected={p.relative_to(ROOT).as_posix():'share/pll-allocation/'+p.parent.relative_to(ROOT).as_posix()
              for p in (ROOT/'configs').rglob('*.json')}
    assert actual==expected


def test_relocated_configs_and_profiles_match_recorded_identity():
    receipt=json.loads((ROOT/'configs/provenance/config_paths.json').read_text(encoding='utf-8'))
    naming=json.loads((ROOT/'configs/provenance/naming_migration.json').read_text(encoding='utf-8'))
    updates={row['path']: row for row in naming['source_updates']}
    for row in receipt['config_moves']:
        assert not (ROOT/row['old']).exists()
        digest=hashlib.sha256((ROOT/row['new']).read_bytes()).hexdigest()
        if digest!=row['after_sha256']:
            update=updates[row['new']]
            assert update['before_sha256']==row['after_sha256'] and update['after_sha256']==digest
        if row['new']!='configs/pipeline.json':assert row['after_sha256']==row['before_sha256']
    for row in receipt['duplicate_config_removals']:
        assert not (ROOT/row['path']).exists()
        assert (ROOT/row['replacement']).is_file()
    profiles=json.loads((ROOT/'configs/provenance/verification_profiles.json').read_text(encoding='utf-8'))
    for row in profiles['files']:
        assert hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()==row['sha256']


def test_profile_generation_is_explicit_and_never_overwrites(tmp_path):
    target=tmp_path/'profiles'
    command=[sys.executable,str(ROOT/'tools/create_verification_profiles.py'),'--out',str(target)]
    first=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    assert first.returncode==0,first.stderr
    before={p.name:p.read_bytes() for p in target.iterdir()}
    assert len(before)==18 and 'manifest.json' in before
    second=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    assert second.returncode!=0
    assert {p.name:p.read_bytes() for p in target.iterdir()}==before
