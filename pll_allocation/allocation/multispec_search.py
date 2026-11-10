"""Deterministic proposals over existing M1/solvers; runner owns M2 and verdicts."""
from copy import deepcopy
import math
from .allocate import analytical,optimize,sensitivity
from .core import assess_m1,bounds,values,margin_details
from .physics import inverse_at_shape,propagate
from ..block_space.contracts import make_candidate,check_parameters
from ..physics_mapping.model import fingerprint
from .multispec_constraints import objective_key


class SearchController:
    def __init__(self,model,problem,method,meter,emit):
        self.model,self.problem,self.method,self.meter,self.emit=model,problem,method,meter,emit
        self.spec=problem['research_system_spec'];self.pool=[];self.seen=set();self.records=[]
        self.incumbent=None;self.anchor=None;self.pair_step=None;self.no_improvement=0
        self.log_step=problem['search']['log_step'];self.vstep=problem['search']['voltage_step_V']
        self.stop_reason=None;self.sens=None;self.poll_number=0

    def checked(self,candidate,reason):
        self.meter.charge('candidate_generations')
        domain=check_parameters(self.model,candidate)
        if domain['declared_domain']!='IN_DECLARED_DOMAIN' or domain['model_validity']!='VALID':
            self.emit('CANDIDATE_REJECTED',reason=reason,domain=domain,parameters=candidate)
            return None
        a=assess_m1(self.model,self.spec,candidate,self.meter)
        self.emit('M1_CANDIDATE_CHECK',reason=reason,candidate=candidate,assessment=a)
        if a['judgment']['verdict']!='M1_SPEC_PASS':return None
        return {'candidate':candidate,'assessment':a,'reason':reason,'parameter_sha256':fingerprint(candidate)}

    def initialize(self):
        start,meta=analytical(self.model,self.spec,self.meter)
        self.emit('ANALYTICAL_ALLOCATION',metadata=meta,candidate=start)
        if start is None:self.stop_reason='NO_INITIAL_CANDIDATE';return None
        if self.method=='A':return self.checked(start,'A_UNCHANGED_ANALYTICAL')
        self.sens=sensitivity(self.model,self.spec,self.meter,start)
        self.emit('M1_SENSITIVITY',result=self.sens,role='actual SLSQP guards and feedback variable activation')
        improved,opt=optimize(self.model,self.spec,self.meter,self.sens)
        self.emit('SLSQP_JOINT_IMPROVEMENT',before=start,after=improved,metadata=opt)
        self.build_pool(start)
        return self.checked(improved or start,'B_C_EXISTING_SLSQP_WITH_ANALYTICAL_CENTER_SENSITIVITY')

    def build_pool(self,initial):
        bw=next(r for r in self.spec['metrics'] if r['metric']=='BW_Hz');target=(bw['min']+bw['max'])/2
        domain=propagate(self.model,self.spec)
        for pair in domain['capacitor_pairs']:
            if pair['x_interval'] is None:continue
            p=inverse_at_shape(self.model,pair['C1'],pair['C2'],target,math.sqrt(1+pair['C2']/pair['C1']),self.meter)
            if p is None:continue
            try:c=make_candidate(self.model,p)
            except ValueError as e:self.emit('REGION_REJECTED',capacitors=pair,reason=str(e));continue
            record=self.checked(c,'DIVERSE_CAPACITOR_PEAK_SHAPE')
            if record:self.pool.append(record)
        # Different gain split / operating points also retained without asserting capture quality.
        p=values(initial);product=p['Icp']*p['Kvco']
        for fraction in (.25,.75):
            lo=max(bounds(self.model,'Kvco')[0],product/bounds(self.model,'Icp')[1])
            hi=min(bounds(self.model,'Kvco')[1],product/bounds(self.model,'Icp')[0]);kv=lo+fraction*(hi-lo)
            q={**p,'Kvco':kv,'Icp':product/kv,'f0':min(bounds(self.model,'f0')[1],max(bounds(self.model,'f0')[0],80e6-kv*.6))}
            record=self.checked(make_candidate(self.model,q),'DIVERSE_GAIN_SPLIT')
            if record:self.pool.append(record)
        self.emit('DIVERSE_POOL_RETAINED',regions=self.pool,not_measured=True)

    def observe(self,record,evaluation):
        self.seen.add(record['parameter_sha256']);record={**record,'evaluation':deepcopy(evaluation)}
        self.records.append(record)
        previous=self.incumbent
        if previous is None or objective_key(evaluation,self.problem['objective'])<objective_key(previous['evaluation'],self.problem['objective']):
            self.incumbent=record;self.no_improvement=0
            self.emit('INCUMBENT_UPDATED',previous_candidate_sha256=previous['parameter_sha256'] if previous else None,
                parameter_sha256=record['parameter_sha256'],objective=list(objective_key(evaluation,self.problem['objective'])))
        else:
            self.no_improvement+=1
            self.emit('POLL_NOT_IMPROVED',parameter_sha256=record['parameter_sha256'],no_improvement=self.no_improvement)
        failed=[r['metric_name'] for r in evaluation['constraints'] if r['verification_status']=='FAIL']
        self.emit('BEHAVIORAL_FEEDBACK',evaluation=evaluation,failed_metrics=failed,
            rule='feasibility first; paired polls are directional evidence, never precise capture gradients')
        if self.anchor and record['reason'].startswith('PAIRED_BEHAVIORAL_POLL'):
            a=next(r for r in self.anchor['evaluation']['constraints'] if r['metric_name']=='lock_time_s')['numerical_envelope']
            b=next(r for r in evaluation['constraints'] if r['metric_name']=='lock_time_s')['numerical_envelope']
            trend=('UNRESOLVED' if not a or not b else 'RESOLUTION_OVERLAP_NO_EXACT_GRADIENT' if max(a[0],b[0])<=min(a[1],b[1])
                   else 'DIRECTIONAL_IMPROVEMENT' if b[1]<a[0] else 'DIRECTIONAL_DEGRADATION')
            self.emit('CAPTURE_POLL_TREND',classification=trend,anchor_interval=a,trial_interval=b,
                      scope='finite window, quantized and potentially nonsmooth; no differentiability assumption')
        if self.method!='C':self.stop_reason='METHOD_HAS_NO_BEHAVIORAL_SEARCH';return
        if evaluation['unresolved_constraints']:
            self.stop_reason='UNRESOLVED_MEASUREMENT_DIAGNOSIS_REQUIRED';return
        if self.no_improvement>=self.problem['search']['max_no_improvement']:
            self.log_step*=.5;self.vstep*=.5;self.no_improvement=0
            self.emit('TRUST_RADIUS_CONTRACTED',log_step=self.log_step,voltage_step_V=self.vstep,
                reason='two non-improving polls, finite block resolution/non-smooth response possible')

    def _coordinate_candidate(self,anchor,label,delta):
        p=values(anchor['candidate']);q=dict(p);product=p['Icp']*p['Kvco']
        if label=='Vreq':
            v=(80e6-p['f0'])/p['Kvco']+delta;q['f0']=80e6-p['Kvco']*v
        elif label=='Kvco':
            v=(80e6-p['f0'])/p['Kvco'];q['Kvco']=p['Kvco']*math.exp(delta)
            q['Icp']=product/q['Kvco'];q['f0']=80e6-q['Kvco']*v
        elif label=='gain':q['Icp']=p['Icp']*math.exp(delta)
        elif label=='Rz':q['Rz']=p['Rz']*math.exp(delta)
        else:raise ValueError('unsupported physical coordinate')
        try:return make_candidate(self.model,q)
        except ValueError as error:
            self.emit('COORDINATE_OUT_OF_DOMAIN',coordinate=label,delta=delta,reason=str(error),original_values=q);return None

    def _bw_feedback_poll(self):
        anchor=self.incumbent;rows={r['metric_name']:r for r in anchor['evaluation']['constraints']}
        observed=rows['BW_Hz']['measured_or_predicted_value'];base=anchor['assessment']['prediction']['metrics']['BW_Hz']
        candidates=[]
        for label in ('gain','Rz'):
            column='Icp' if label=='gain' else label
            derivative=self.sens['columns'].get(column,{})
            if derivative.get('status')!='OK' or abs(derivative['log_elasticity']['BW_Hz'])<1e-8:
                self.emit('SENSITIVITY_DEGENERATE',coordinate=label,action='freeze unreliable direction');continue
            for sign in (-1,1):
                step=self.log_step;r=None
                while step>=self.problem['search']['minimum_log_step']-1e-12:
                    c=self._coordinate_candidate(anchor,label,sign*step)
                    if c is not None and fingerprint(c) not in self.seen:
                        r=self.checked(c,'M2_BW_RESIDUAL_SENSITIVITY_PATTERN:'+label+':'+str(sign))
                    if r:break
                    self.emit('FEEDBACK_STEP_BACKTRACKED',coordinate=label,sign=sign,
                        rejected_log_step=step,next_log_step=step*.5,reason='full M1 constraint/domain rejection or repeated point')
                    step*=.5
                if not r:continue
                pred=r['assessment']['prediction']['metrics'];corrected=pred['BW_Hz']*observed/base
                rule=rows['BW_Hz'];margin=min(corrected-rule['lower_bound'],rule['upper_bound']-corrected)/rule['normalization_scale']
                pm=rows['PM_deg'];pmmargin=(pred['PM_deg']-pm['lower_bound'])/pm['normalization_scale']
                r['feedback_projection']={'BW_Hz':corrected,'scope':'local multiplicative discrepancy heuristic; original M1 unchanged; requires new full M2',
                    'sensitivity_column':derivative,'predicted_worst_frequency_margin':min(margin,pmmargin)}
                candidates.append(r)
        self.emit('FEEDBACK_PATTERN_SCREEN',candidates=candidates)
        if candidates:return max(candidates,key=lambda r:r['feedback_projection']['predicted_worst_frequency_margin'])
        return None

    def next(self):
        if self.stop_reason:return None
        if not self.incumbent:return self.initialize()
        if self.method!='C':return None
        if self.log_step<self.problem['search']['minimum_log_step'] or self.vstep<self.problem['search']['minimum_voltage_step_V']:
            self.stop_reason='TRUST_RADIUS_BELOW_RESOLUTION';return None
        failed=[r['metric_name'] for r in self.incumbent['evaluation']['constraints'] if r['verification_status']=='FAIL']
        if 'BW_Hz' in failed:
            r=self._bw_feedback_poll()
            if r:return r
        # Pair anchors fixed before +/- evaluations, so observations are not called exact derivatives.
        while self.poll_number<4:
            stage=self.poll_number//2;sign=-1 if self.poll_number%2==0 else 1
            if self.poll_number%2==0:
                self.anchor=deepcopy(self.incumbent);self.pair_step=self.vstep if stage==0 else self.log_step
            self.poll_number+=1;coordinate='Vreq' if stage==0 else 'Kvco'
            if coordinate=='Kvco':
                a=self.sens['columns'].get('Icp',{});b=self.sens['columns'].get('Kvco',{})
                if a.get('status')!='OK' or b.get('status')!='OK':
                    self.emit('SENSITIVITY_DEGENERATE',coordinate=coordinate,action='skip unverified equivalent-gain poll');continue
            delta=sign*self.pair_step
            self.emit('VARIABLE_ACTIVATED',coordinate=coordinate,delta=delta,anchor_sha256=self.anchor['parameter_sha256'],
                feedback_capture=self.incumbent['evaluation']['constraints'][-1],
                reason='M1 f0 dynamic zero-column / Icp-Kvco equivalent columns; behavior remains independently measured')
            c=self._coordinate_candidate(self.anchor,coordinate,delta)
            if c is None or fingerprint(c) in self.seen:continue
            r=self.checked(c,'PAIRED_BEHAVIORAL_POLL:'+coordinate+':'+str(sign))
            if r:return r
        # Switch to an already independently M1-screened physical region; deterministic order.
        current=values(self.incumbent['candidate'])
        ordered=sorted(enumerate(self.pool),key=lambda item:(
            (values(item[1]['candidate'])['C1'],values(item[1]['candidate'])['C2'])==(current['C1'],current['C2']),item[0]))
        for _,r in ordered:
            if r['parameter_sha256'] not in self.seen:
                self.emit('PHYSICAL_REGION_SWITCH',from_sha256=self.incumbent['parameter_sha256'],to_region=r,
                    reason='local operating-point polls exhausted; preserve full BW/PM/tuning checks')
                return self.checked(r['candidate'],'REGION_SWITCH_FULL_RECHECK')
        self.stop_reason='NO_UNSEEN_M1_FEASIBLE_POLL';return None
