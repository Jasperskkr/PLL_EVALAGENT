"""Freeze reviewed stochastic tracking protocol; never replace v1 UNKNOWN evidence."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


if __name__=='__main__':
    old=ROOT/'configs/stage6c/frozen_01';new=ROOT/'configs/stage6c/protocol11_01';new.mkdir(parents=True,exist_ok=False)
    q=json.loads((old/'noise_protocol.json').read_text())
    q.update(protocol_id='pll-noise-verification-1.1',noise_settle_s=100e-6,
        stochastic_tracking='unchanged_coldcapture_gate; no_slip_clamp_rails; original_phase_and_control_bounds; halfobservation_mean_frequency_bound',
        legacy_1us_capture_frequency='DIAGNOSTIC_ONLY_NOT_RANDOM_LOCK_IDENTIFICATION',
        revision_reason='independent source variance and ten saved trajectories show v1 misclassifies stationary frequency noise as loss of lock',
        baseline_protocol='configs/stage6c/frozen_01/noise_protocol.json')
    with (new/'noise_protocol.json').open('x',encoding='utf-8') as f:json.dump(q,f,indent=2);f.write('\n')
    refs=[{'path':(new/'noise_protocol.json').relative_to(ROOT).as_posix(),'sha256':hashlib.sha256((new/'noise_protocol.json').read_bytes()).hexdigest()}]
    for p in sorted(old.glob('*.json')):
        if p.name not in ('noise_protocol.json','manifest.json'):refs.append({'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    with (new/'manifest.json').open('x',encoding='utf-8') as f:json.dump(refs,f,indent=2)
