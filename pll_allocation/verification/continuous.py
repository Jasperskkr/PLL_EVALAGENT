"""Validated continuous-Handoff adapter to the existing native M2 TB.

The frozen proposal gate and all physical/measurement equations stay unchanged.
The subprocess boundary provides a hard deadline even inside ctypes native code.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from ..agent.handoff import validate_handoff
from ..exploration.contracts import require
from ..physics_mapping.model import fingerprint, parse_parameters
from .build_identity import check_build, identities
from .experiments import read, write, response_sweep
from .metric_protocols import integer_n_protocol
from .run_suite import capture_pair, comparison_after_measurement
from .simulator import MODEL_VERSION, validate_frequency_plan
from .verify import interval_judgment


def measurement_suite(p,out,doc,*,before_posthoc_m1):
    """Adapt the handoff to the frozen public TB functions, not its old gate.

    Schedule/thresholds match verify.verify. Its source remains byte-frozen for
    historical Registry bindings. No simulator or measurement is reimplemented.
    """
    capture=capture_pair(out/'capture',p,.15,160e-6,protocol_document=doc)
    values=validate_frequency_plan(p)
    target=values['N']*values['f_ref']
    vreq=(target-values['f0'])/values['Kvco'];responses={};comparison=None
    if values['Vctrl_min']<vreq<values['Vctrl_max']:
        for key,amp,dt,cycles in [('base',.01,.4e-9,12),('amplitude_half',.005,.4e-9,12),
            ('step_half',.01,.2e-9,12),('window_double',.01,.4e-9,24)]:
            responses[key]=response_sweep(out/key,p,amplitude=amp,dt=dt,cycles=cycles,protocol_document=doc)
        before_posthoc_m1()
        comparison=comparison_after_measurement(p,responses,protocol_document=doc)
    return capture,responses,comparison


def model_identity():
    check_build()
    root = Path(__file__).parent
    return {'model_version': MODEL_VERSION, 'native': identities(), 'adapter_version': 'pll-continuous-m2-1.2',
        'source_sha256': {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in
            ('continuous.py', 'metric_protocols.py', 'verify.py', 'simulator.py', 'measure.py', 'experiments.py', 'run_suite.py')}}


def verification_request(handoff, *, run_id, observation_id, timeout_s):
    parameters = validate_handoff(handoff)
    p = validate_frequency_plan(parameters)
    require(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 3600,
            'bounded M2 deadline required')
    doc = integer_n_protocol(p)
    item = {'schema_version': 'pll-m2-verification-request-1.0', 'run_id': run_id,
        'observation_id': observation_id, 'candidate_id': handoff['recommended_nominal']['evidence_id'],
        'candidate_sha256': fingerprint(parameters), 'problem_id': handoff['problem']['problem_id'],
        'problem_sha256': handoff['problem_sha256'], 'parameters': parameters,
        'topology': handoff['problem']['topology'], 'fixed_parameters': handoff['problem']['fixed_parameters'],
        'specs': deepcopy(handoff['system_spec']), 'handoff': deepcopy(handoff),
        'M1_evidence_id': handoff['recommendation_recheck']['evidence_id'],
        'M1_metrics': deepcopy(handoff['recommended_nominal']['metrics']),
        'M2_model': model_identity(), 'protocol': doc, 'protocol_id': doc['protocol_id'],
        'protocol_sha256': fingerprint(doc), 'timeout_s': timeout_s,
        'budget': {'M2_verifications': 1, 'posthoc_M1_reserve': 1},
        'spec_protocol_mapping': {'BW_Hz': 'unchanged warm-start divided-phase -3dB convergence envelope',
            'lock_time_s': 'explicit verification feedback mapping from PENDING_M2 to protocol.capture: initial=.15V,160us window; conditional',
            'PM_deg': 'NO_M2_CERTIFICATION; original M1 evidence separate', 'jitter_s': 'UNSUPPORTED'}}
    item['request_sha256'] = fingerprint(item)
    return item


def validate_request(item):
    require(item['request_sha256'] == fingerprint({k:v for k,v in item.items() if k != 'request_sha256'}),
            'M2 request fingerprint mismatch')
    expected = verification_request(item['handoff'], run_id=item['run_id'],
        observation_id=item['observation_id'], timeout_s=item['timeout_s'])
    require(item == expected, 'M2 request/model/protocol/candidate binding mismatch')
    return item['parameters']


def judge_measurements(request, capture, comparison):
    """Point-level independent M2 judgments; never fill PM/Jitter from M1."""
    bwok = bool(comparison and comparison['numerical_converged'])
    bw = comparison['M2_BW_measurement'].get('BW_Hz') if bwok else None
    bwi = comparison['BW_numerical_envelope_Hz'] if bwok else None
    captured = bool(capture and capture['numerical_converged'] and
                    capture['reliable_capture_status'] == 'CAPTURED_WITHIN_WINDOW')
    lock = capture['fine']['lock_time_s'] if captured else None
    # Retain the protocol's 1us reporting resolution and observed two-step discrepancy.
    uncertainty = max(1e-6, capture['step_comparison']['lock_time_difference_s'] or 0) if captured else None
    locki = [max(0, lock-uncertainty), lock+uncertainty] if lock is not None else None
    metrics = {'BW_Hz': {'value':bw, 'unit':'Hz', 'interval':bwi, 'valid':bwok},
        'lock_time_s': {'value':lock, 'unit':'s', 'interval':locki, 'valid':locki is not None,
                        'scope':'conditional on initial=.15V and 160us capture window'},
        'PM_deg': {'value':None, 'unit':'deg', 'interval':None, 'valid':False},
        'jitter_s': {'value':None, 'unit':'s', 'interval':None, 'valid':False}}
    constraints = []
    for spec in request['specs']:
        m = metrics.get(spec['metric'], {'value':None, 'interval':None, 'valid':False})
        status = interval_judgment(m['interval'], spec) if spec['enabled'] and m['valid'] else (
            'UNKNOWN' if spec['enabled'] else 'DISABLED')
        bounds = ({**({'min':m['interval'][0]-spec['min']+spec['tolerance']} if 'min' in spec else {}),
                   **({'max':spec['max']+spec['tolerance']-m['interval'][1]} if 'max' in spec else {})}
                  if m['valid'] and spec['enabled'] else {})
        constraints.append({'metric':spec['metric'], 'spec':deepcopy(spec), 'value':m['value'],
            'numerical_interval':m['interval'], 'status':status, 'bound_margins':bounds,
            'margin':min(bounds.values(), default=None),
            'reason':'converged native measurement envelope' if m['valid'] else 'unsupported, unmeasured or unconverged M2 metric'})
    enabled = [c for c in constraints if c['spec']['enabled']]
    supported = [c for c in enabled if c['metric'] in ('BW_Hz', 'lock_time_s')]
    def aggregate(rows):
        return ('FAIL' if any(c['status']=='FAIL' for c in rows) else 'PASS' if rows and
            all(c['status']=='PASS' for c in rows) else 'UNKNOWN')
    return {'metrics':metrics, 'constraints':constraints, 'overall_status':aggregate(enabled),
        'supported_metrics_status':aggregate(supported), 'M1_metrics':request['M1_metrics'],
        'FULL_SYSTEMSPEC_CERTIFIED':False, 'verified_joint_block_spec':False,
        'capture':capture, 'frequency_response_comparison':comparison,
        'capability_boundary':'M2 PM/Jitter unknown; measured points only; no PDK/SPICE certification'}


def cost_from_disk(out):
    out = Path(out)
    summaries = [read(p)['summary'] for p in out.rglob('summary.json')]
    return {'completed_native_runs':len(summaries), 'attempted_native_runs':len(list(out.rglob('request.json'))),
        'integration_points':sum(s['integration_points'] for s in summaries),
        'native_elapsed_s':sum(s['elapsed_s'] for s in summaries),
        'failed_native_attempts':len(list(out.rglob('failure.json'))),
        'posthoc_M1_calls':int((out/'posthoc_m1_started.json').exists())}


def partial_measurements(out):
    """Retain completed independent metrics if another measurement fails."""
    out=Path(out)
    capture=read(out/'capture/comparison.json') if (out/'capture/comparison.json').exists() else None
    comparison=read(out/'measurement_comparison.json') if (out/'measurement_comparison.json').exists() else None
    return capture,comparison


def worker(request, out):
    validate_request(request)
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    write(out/'verification_request.json', request)
    started = time.perf_counter()
    try:
        capture, responses, comparison = measurement_suite(request['parameters'], out, request['protocol'],
            before_posthoc_m1=lambda: write(out/'posthoc_m1_started.json', {'formal_call_started':True}))
        write(out/'measurement_comparison.json',comparison)
        result = judge_measurements(request, capture, comparison)
        result['execution_status'] = 'COMPLETED'
    except Exception as error:
        result = judge_measurements(request, *partial_measurements(out))
        result.update(execution_status='EXCEPTION', error=type(error).__name__+': '+str(error))
    result.update(schema_version='pll-m2-observation-1.0', run_id=request['run_id'],
        observation_id=request['observation_id'], candidate_id=request['candidate_id'],
        candidate_sha256=request['candidate_sha256'], request_sha256=request['request_sha256'],
        problem_sha256=request['problem_sha256'], protocol_sha256=request['protocol_sha256'],
        M2_model_fingerprint=fingerprint(request['M2_model']), evidence_id='M2:'+request['observation_id'],
        raw_evidence_path=str(out.resolve()), cost=cost_from_disk(out), wall_time_s=time.perf_counter()-started)
    write(out/'result.json',result)
    return result


def execute_request(request, out):
    """Each request is isolated; partial native evidence survives timeout/failure."""
    validate_request(request)
    out = Path(out).resolve(); require(not out.exists(), 'M2 output already exists')
    request_path = out.with_name(out.name+'_request.json'); write(request_path, request)
    start = time.perf_counter()
    code = None; failure = None
    try:
        p = subprocess.run([sys.executable, '-B', '-m', 'pll_allocation.verification.continuous',
            '--request',str(request_path),'--out',str(out)], capture_output=True, shell=False,
            timeout=request['timeout_s'], creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        code = p.returncode
        out.mkdir(parents=True,exist_ok=True)
        (out/'worker_stdout.txt').write_bytes(p.stdout); (out/'worker_stderr.txt').write_bytes(p.stderr)
    except subprocess.TimeoutExpired:
        failure = 'TIMEOUT'
    if (out/'result.json').exists():
        result = read(out/'result.json')
    else:
        out.mkdir(parents=True,exist_ok=True)
        result = judge_measurements(request,*partial_measurements(out))
        result.update(schema_version='pll-m2-observation-1.0', execution_status=failure or 'WORKER_FAILED',
            run_id=request['run_id'], observation_id=request['observation_id'], candidate_id=request['candidate_id'],
            candidate_sha256=request['candidate_sha256'], problem_sha256=request['problem_sha256'],
            request_sha256=request['request_sha256'], protocol_sha256=request['protocol_sha256'],
            M2_model_fingerprint=fingerprint(request['M2_model']), evidence_id='M2:'+request['observation_id'],
            raw_evidence_path=str(out), cost=cost_from_disk(out), wall_time_s=time.perf_counter()-start)
        write(out/'result.json',result)
    result.update(worker_returncode=code, parent_wall_time_s=time.perf_counter()-start)
    write(out/'execution_result.json',result)
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--request',required=True); parser.add_argument('--out',required=True)
    args=parser.parse_args(); worker(read(args.request),args.out)


if __name__ == '__main__':
    main()
