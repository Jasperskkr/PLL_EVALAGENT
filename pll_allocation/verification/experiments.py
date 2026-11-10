"""Reproducible measurement experiments; M1 is absent from this module."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from .resources import CONFIGS
import time
import numpy as np
from .simulator import simulate
from .measure import (bandwidth_from_response,capture_metrics,compare_transfers,
                     pm_identification_prototype,response_metrics)

HERE=Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path,value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write('\n')


def protocol():
    return read(CONFIGS/'verification/protocol_v1_1.json')


def candidate(overrides=None):
    import sys
    from pll_allocation.block_space import make_candidate,load_model
    return make_candidate(load_model(CONFIGS/'BLOCK_SPACE_MODEL_V1.json'),overrides)


def save_run(folder,parameters,settings,kind,*,protocol_document=None,simulate_fn=None):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=False)
    doc=protocol_document if protocol_document is not None else protocol()
    protocol_hash=hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest() if protocol_document is not None else hashlib.sha256((CONFIGS/'verification/protocol_v1_1.json').read_bytes()).hexdigest()
    write(folder/'request.json',{'parameters':parameters,'settings':settings,'kind':kind,
        'protocol_sha256':protocol_hash,'protocol_document':doc,
        'protocol_hash_encoding':'sorted_compact_json_utf8' if protocol_document is not None else 'raw_protocol_json_file_bytes'})
    start=time.perf_counter()
    try:
        run=(simulate_fn or simulate)(parameters,**settings)
        np.savez_compressed(folder/'trajectory.npz',trace=run['trace'],ref_edges=run['ref_edges'],div_edges=run['div_edges'])
        write(folder/'summary.json',{'summary':run['summary'],'actual_settings':run['settings']})
        if kind=='capture':
            measured=capture_metrics(run,doc)
        else:
            cfg=doc['frequency_response']; freq=settings['modulation_Hz']
            discard=max(cfg['minimum_discard_s'],cfg['discard_cycles']/freq)
            begin=settings['onset_s']+discard
            measured=response_metrics(run,doc,measurement_start_s=begin,measurement_end_s=settings['duration_s'])
        write(folder/'measurement.json',measured)
        with (folder/'complete.json').open('x',encoding='utf-8') as f:
            json.dump({'status':'COMPLETED','elapsed_including_measurement_s':time.perf_counter()-start},f)
        return measured
    except Exception as error:
        write(folder/'failure.json',{'status':'UNKNOWN','reason':type(error).__name__+': '+str(error),
                                    'elapsed_s':time.perf_counter()-start})
        raise


def response_point(folder,p,freq,*,amplitude=.01,dt=.4e-9,cycles=12,protocol_document=None,simulate_fn=None):
    cfg=(protocol_document or protocol())['frequency_response']
    # Initialization from static frequency law only, not M1 loop predictions.
    v=p['values']; vreq=(v['N']['value']*v['f_ref']['value']-v['f0']['value'])/v['Kvco']['value']
    settings={'duration_s':cfg['onset_s']+max(cfg['minimum_discard_s'],cfg['discard_cycles']/freq)+cycles/freq,
        'dt_s':dt,'initial_control_V':vreq,'phase_amplitude_rad':amplitude,'modulation_Hz':freq,
        'onset_s':cfg['onset_s'],'record_interval_s':cfg['record_interval_s']}
    return save_run(folder,p,settings,'response',protocol_document=protocol_document,simulate_fn=simulate_fn)


def response_sweep(folder,p,*,amplitude=.01,dt=.4e-9,cycles=12,protocol_document=None,simulate_fn=None):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=False)
    cfg=(protocol_document or protocol())['frequency_response']
    plan={'parameters':p,'amplitude_rad':amplitude,'dt_s':dt,'cycles':cycles,
        'grid_Hz':cfg['grid_Hz'],'refinement':'geometric midpoint of measured BW bracket; no M1 query',
        'frequency_bracket_relative_width_limit':cfg['frequency_bracket_relative_width_limit'],
        'posthoc_low_frequency_anchor':'if first measured gain >1.03, add 5kHz then 2kHz; no model query'}
    write(folder/'plan.json',plan)
    points=[]
    for i,freq in enumerate(cfg['grid_Hz']):
        points.append(response_point(folder/f'f{i:02d}',p,freq,amplitude=amplitude,dt=dt,cycles=cycles,protocol_document=protocol_document,simulate_fn=simulate_fn))
    for j,freq in enumerate((5000,2000)):
        first=min((x for x in points if x['status']=='MEASURED'),key=lambda x:x['frequency_Hz'],default=None)
        if first is not None and abs(first['magnitude']-1)>.03:
            points.append(response_point(folder/f'anchor{j}',p,freq,amplitude=amplitude,dt=dt,cycles=cycles,protocol_document=protocol_document,simulate_fn=simulate_fn))
    bw=bandwidth_from_response(points)
    for i in range(16):
        if bw['status']!='MEASURED_BRACKETED' or bw['bracket_relative_width']<=cfg['frequency_bracket_relative_width_limit']:
            break
        a,b=bw['bracket_Hz']; freq=math.sqrt(a*b)
        points.append(response_point(folder/f'refine{i:02d}',p,freq,amplitude=amplitude,dt=dt,cycles=cycles,protocol_document=protocol_document,simulate_fn=simulate_fn))
        bw=bandwidth_from_response(points)
    result={'bandwidth':bw,'points':points,'PM':pm_identification_prototype(points),
            'M1_used_for_measurement':False,'settings':plan}
    write(folder/'result.json',result)
    return result


def compare_sweeps(reference,other):
    a,b=reference['bandwidth'],other['bandwidth']
    base={p['frequency_Hz']:p for p in reference['points']}
    diffs=[compare_transfers(base[p['frequency_Hz']],p) for p in other['points'] if p['frequency_Hz'] in base]
    differences=[x for x in diffs if x['status']=='COMPARED']
    return {'BW_relative_difference':abs(b['BW_Hz']/a['BW_Hz']-1) if 'BW_Hz' in a and 'BW_Hz' in b else None,
        'max_complex_transfer_relative_difference':max((x['relative_complex_difference'] for x in differences),default=None),
        'max_transfer_phase_difference_deg':max((x['phase_difference_deg'] for x in differences),default=None),
        'compared_frequencies':len(differences)}


