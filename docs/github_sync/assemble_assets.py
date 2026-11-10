import argparse, hashlib, json
from pathlib import Path

p = argparse.ArgumentParser(description='Verify release parts and reassemble original archives into a new directory')
p.add_argument('--downloaded', required=True)
p.add_argument('--target', required=True)
a = p.parse_args(); source = Path(a.downloaded).resolve(); target = Path(a.target).resolve()
if target.exists(): raise SystemExit('Target must not already exist')
manifest = json.loads((source / 'TRANSFER_MANIFEST.json').read_text(encoding='utf-8'))
target.mkdir(parents=True)
for row in manifest['files']:
    destination = (target / row['name']).resolve()
    if destination.parent != target: raise ValueError('Unsafe asset name')
    total = hashlib.sha256(); size = 0
    with destination.open('xb') as out:
        for part in row['parts']:
            path = (source / part['name']).resolve()
            if path.parent != source: raise ValueError('Unsafe part name')
            digest = hashlib.sha256(); n = 0
            with path.open('rb') as f:
                for data in iter(lambda: f.read(4 * 1024 ** 2), b''):
                    digest.update(data); total.update(data); out.write(data); n += len(data); size += len(data)
            if n != part['bytes'] or digest.hexdigest() != part['sha256']: raise ValueError('Part integrity mismatch: ' + part['name'])
    if size != row['bytes'] or total.hexdigest() != row['sha256']: raise ValueError('Original asset integrity mismatch: ' + row['name'])
    print('Verified', row['name'], size)
