"""Run the scientific-figure rendered audits and preserve every tool result."""
from pathlib import Path
import argparse
import json
import subprocess
import sys


def main(folder, scripts):
    folder, scripts = Path(folder), Path(scripts)
    out = folder/'qa'; out.mkdir(exist_ok=False); records = []
    tasks = [('source', [sys.executable, str(scripts/'validate_figure.py'), str(Path(__file__).with_name('plot_stage41.py')), '--json'])]
    for p in sorted(folder.glob('*.pdf')):
        tasks.append((p.stem+'_text', [sys.executable, str(scripts/'audit_pdf_text.py'), str(p), '--min-pt', '5', '--json']))
        tasks.append((p.stem+'_collision', [sys.executable, str(scripts/'audit_figure_collisions.py'), str(p),
                     '--json-out', str(out/(p.stem+'.collision.json')), '--overlay-pdf', str(out/(p.stem+'.collision.pdf'))]))
    for name, command in tasks:
        r = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
        (out/(name+'.txt')).write_text(r.stdout+'\n'+r.stderr, encoding='utf-8')
        records.append({'task': name, 'command': command, 'exit_code': r.returncode})
    (out/'execution.json').write_text(json.dumps(records, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(records, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--folder', required=True); parser.add_argument('--scripts', required=True)
    args = parser.parse_args(); main(args.folder, args.scripts)
