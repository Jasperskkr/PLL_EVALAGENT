"""Thin adapter over the byte-identical, previously regressed behavioral core."""
from __future__ import annotations
from copy import deepcopy
import math
from pathlib import Path
import subprocess
import time
from .contracts import METRICS, digest, values_of, canonical
from ._legacy.evaluation.python_behavioral import PythonBehavioralEvaluator
from ._legacy.physics.cp import equilibrium_timing

PHYSICS = {
 'charge': 'q(d)=q0 + Iup*d if d>=0, else q0 + Idown*d; q0 already includes local proxy DC demand',
 'phase': 'd_eq=-q0/I(direction); phase_eq_deg=-360*fref*d_eq; phase=feedback-reference',
 'vco': 'f(V)=f0+Kvco_Hz_per_V*(V-V0); angular gain=2*pi*Kvco_Hz_per_V',
 'filter': 'Z(s)=(1+s*Rz*C2)/(s*(C1+Cload+C2)+s^2*Rz*(C1+Cload)*C2)',
 'coupling': 'CP current, LF impedance and VCO gain jointly determine loop dynamics; static phase alone cannot establish transient lock',
 'unsupported': ['phase_noise','jitter','reference_spur','sampled_loop_bandwidth','sampled_phase_margin'],
}

def legacy_inputs(p, candidate):
    v=values_of(candidate)
    t={k.split('.',1)[1]:value for k,value in v.items() if k.startswith(('CP.','LF.'))}
    c=deepcopy(p['operating_context']); c['pfd_reset_s']=v['PFD.reset_s']
    req={'operating_context':c,'initialization':p['initialization'], 'measurement':p['measurement'], 'system_spec':p['system_spec']}
    vco={k:v['VCO.'+k] for k in ('V0_V','f0_Hz','Kvco_Hz_per_V')}
    vco['declared_voltage_range_V']=[v['VCO.voltage_min_V'],v['VCO.voltage_max_V']]
    return req,t,vco

def screen(p,candidate):
    req,t,vco=legacy_inputs(p,candidate)
    phase=-360*req['operating_context']['fref_Hz']*equilibrium_timing(t)
    veq=vco['V0_V']+(req['operating_context']['fout_target_Hz']-vco['f0_Hz'])/vco['Kvco_Hz_per_V']
    return {'kind':'ANALYTIC_EQUILIBRIUM_PREDICTION','metrics':{'mean_phase_abs_deg':abs(phase)},
            'equilibrium_phase_deg':phase,'equilibrium_vctrl_V':veq,
            'dynamic_acceptance':'REQUIRES_FULL_BEHAVIORAL_TB','behavioral_evaluations':0}

def write_json(path,value):
    Path(path).write_text(canonical(value)+'\n',encoding='utf-8')

class PythonBehavioralBackend:
    backend_id='legacy_exact_rc_behavioral_tb_v1'
    def capabilities(self):
        return {'schema_version':'behavioral-capabilities-1.0','backend_id':self.backend_id,
                'metrics':{k:{'unit':v[0],'measurement':v[2]} for k,v in METRICS.items()},
                'scope':'reference_cycle_charge_impulse_exact_RC_linear_VCO',
                'frequency_domain_verification':False,'physical_qualification':False,
                'external_calls_per_evaluation':{'MATLAB':0,'ngspice':0}}

    def run(self,p,candidate,workdir):
        start=time.perf_counter()
        req,target,vco=legacy_inputs(p,candidate)
        raw=PythonBehavioralEvaluator(req,vco).evaluate(target)
        rows=raw.pop('cycles')
        metrics=raw['metrics']
        if rows:
            tail=rows[-p['measurement']['tail_cycles']:]
            metrics.update(output_frequency_Hz=sum(r['frequency_cycle_Hz'] for r in tail)/len(tail),
                           vctrl_min_V=min(r['vctrl_min_V'] for r in rows),vctrl_max_V=max(r['vctrl_max_V'] for r in rows))
        result={'schema_version':'behavioral-evaluation-1.0','backend_id':self.backend_id,
                'problem_sha256':digest(p),'candidate_sha256':digest(candidate),'kind':'FULL_BEHAVIORAL_TB_MEASUREMENT',
                'metrics':metrics,'units':{k:v[0] for k,v in METRICS.items()},
                'measurement':p['measurement'],'metric_measurements':{k:v[2] for k,v in METRICS.items()},
                'domain_status':raw['numeric_domain_status'],'completed':len(rows)==round(p['measurement']['duration_s']*p['operating_context']['fref_Hz']),
                'reference_cycles':len(rows),'raw_model_report':raw,
                'artifacts':{'cycles':'cycles.json'},'cost':{'behavioral_evaluations':1,'reference_cycles':len(rows),
                'external_calls':{'MATLAB':0,'ngspice':0},'elapsed_s':time.perf_counter()-start}}
        write_json(Path(workdir)/'cycles.json',rows)
        write_json(Path(workdir)/'measurement.json',result)
        return result

class CommandBehavioralBackend:
    """Configured JSON/argv bridge. No shell strings, guessed MATLAB API, or PASS stub."""
    def __init__(self,command,capabilities,timeout_s=60):
        if not isinstance(command,list) or not command or not all(isinstance(x,str) for x in command):
            raise ValueError('command must be a nonempty argv list')
        if not math.isfinite(timeout_s) or timeout_s <= 0: raise ValueError('positive timeout required')
        self.command,self._capabilities,self.timeout_s=command,capabilities,timeout_s
        self.backend_id=capabilities['backend_id']
    def capabilities(self): return deepcopy(self._capabilities)
    def run(self,p,candidate,workdir):
        path=Path(workdir).resolve()
        write_json(path/'request.json',{'schema_version':'behavioral-request-1.0','problem':p,'candidate':candidate,
                   'problem_sha256':digest(p),'candidate_sha256':digest(candidate)})
        try:
            process=subprocess.run(self.command,cwd=path,capture_output=True,timeout=self.timeout_s,shell=False,
                                   creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0)
        except subprocess.TimeoutExpired as error:
            (path/'stdout.log').write_bytes(error.stdout or b'')
            (path/'stderr.log').write_bytes(error.stderr or b'')
            raise
        (path/'stdout.log').write_bytes(process.stdout); (path/'stderr.log').write_bytes(process.stderr)
        if process.returncode: raise RuntimeError('behavioral command exited '+str(process.returncode))
        import json
        return json.loads((path/'response.json').read_text(encoding='utf-8'))

class MetricVerifier:
    def judge(self,p,candidate,evaluation):
        issues=[]; checks=[]
        bound=(evaluation.get('schema_version')=='behavioral-evaluation-1.0' and
               evaluation.get('problem_sha256')==digest(p) and evaluation.get('candidate_sha256')==digest(candidate) and
               evaluation.get('measurement')==p['measurement'] and evaluation.get('completed') is True and
               evaluation.get('kind')=='FULL_BEHAVIORAL_TB_MEASUREMENT' and
               evaluation.get('reference_cycles')==round(p['measurement']['duration_s']*p['operating_context']['fref_Hz']))
        if not bound: issues.append('INCOMPLETE_OR_UNBOUND_TB_RESULT')
        if evaluation.get('domain_status')!='IN_DECLARED_NUMERIC_DOMAIN': issues.append('MODEL_OUT_OF_DOMAIN_OR_UNKNOWN')
        for s in p['system_spec']:
            name=s['metric']; actual=evaluation.get('metrics',{}).get(name)
            status='UNKNOWN'; margin=None; normalized=None
            if evaluation.get('units',{}).get(name)!=s['unit'] or evaluation.get('metric_measurements',{}).get(name)!=s['measurement']:
                status='UNSUPPORTED'
            elif actual is not None and bound:
                target=s['value']; tol=s['tolerance']
                if name=='lock_status':
                    if actual in {'LOCKED','NOT_LOCKED'}: status='PASS' if actual==target else 'FAIL'
                elif type(actual) in (int,float) and math.isfinite(actual):
                    margin=target+tol-actual if s['operator']=='<=' else actual-target+tol if s['operator']=='>=' else tol-abs(actual-target)
                    normalized=margin/max(abs(target),tol,1e-30)
                    status='PASS' if margin>=0 else 'FAIL'
            checks.append({'metric':name,'status':status,'actual':actual,'target':s['value'],'unit':s['unit'],
                           'operator':s['operator'],'tolerance':s['tolerance'],'margin':margin,'normalized_margin':normalized})
        unknown=issues or any(c['status'] in {'UNKNOWN','UNSUPPORTED'} for c in checks)
        verdict='UNKNOWN' if unknown else 'FAIL' if any(c['status']=='FAIL' for c in checks) else 'PASS'
        margins=[c['normalized_margin'] for c in checks if c['normalized_margin'] is not None]
        return {'verdict':verdict,'scope':'DECLARED_BEHAVIORAL_MODEL_ONLY','checks':checks,'issues':issues,
                'minimum_normalized_margin':min(margins) if margins else None,
                'constraint_violation':sum(max(0,-c['normalized_margin']) if c['normalized_margin'] is not None else 1 if c['status']=='FAIL' else 0 for c in checks),
                'independent_physical_qualification':'UNKNOWN'}
