"""Write immutable research configs/plan before formal experiments. No M2 execution."""
from copy import deepcopy
import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.allocation.core import write_new
from pll_allocation.allocation.multispec_constraints import validate_problem
from pll_allocation.physics_mapping.model import fingerprint


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='experiments/stage6b/frozen_01');args=parser.parse_args()
    config,model,spec,protocol=load_inputs()
    out=Path(args.out).resolve();out.mkdir(exist_ok=False)
    for name,lower,upper,pm,objective in [('B1',150000,300000,50,'capture_then_margin'),
                                         ('B2',290000,300000,70,'margin_then_capture')]:
        research=deepcopy(spec)
        research['metrics'][1].update(min=lower,max=upper)
        research['metrics'][2]['min']=pm
        constraints=[]
        for metric,op,lo,hi,source,proto,scale,strict in [
            ('BW_Hz','interval',lower,upper,'M2',protocol['protocol_id'],(upper-lower)/2,False),
            ('PM_deg','lower',pm,None,'M1',spec['metrics'][2]['protocol'],pm,False),
            ('Vctrl_required_V','interval',0,1.2,'M1','linear_vco_static_tuning_solution',.6,True),
            ('lock_time_s','upper',None,40e-6,'M2',protocol['protocol_id']+':fixed_capture_0.15V_160us',40e-6,False)]:
            constraints.append(dict(metric_name=metric,comparator=op,lower_bound=lo,upper_bound=hi,
                measurement_source=source,measurement_protocol=proto,normalization_scale=scale,strict=strict,
                model_validity='ORIGINAL_IDEAL_DECLARED_DOMAIN'))
        problem=dict(schema_version='pll-multispec-problem-1.0',problem_id=name,version='stage6b-1.0',
            scope='RESEARCH_ONLY_NO_FULL_CERTIFICATION',base_bindings=config['bindings'],research_system_spec=research,
            constraints=constraints,objective=objective,budgets={'M1_calls':96,'cheap_calls':10000,'M2_candidate_slots':6},
            search={'version':'physical_pattern_1.0','log_step':.08,'voltage_step_V':.08,
                'minimum_log_step':.01,'minimum_voltage_step_V':.01,'max_no_improvement':2,
                'poll_order':['Vreq_minus','Vreq_plus','Kvco_minus','Kvco_plus','region_switch']})
        problem['problem_sha256']=fingerprint(problem)
        validate_problem(problem,config,model,spec,protocol)
        write_new(out/(name+'.json'),problem)
    paths=[ROOT/'pll_allocation/pipeline.py',*sorted((ROOT/'pll_allocation/allocation').glob('*.py')),
           *sorted((ROOT/'tests').glob('*stage6b*')),*sorted((ROOT/'tools').glob('*stage6b*')),
           out/'B1.json',out/'B2.json']
    write_new(out/'plan.json',{'created_at':datetime.now().astimezone().isoformat(),
        'order':[[s,m] for s in ('B1','B2') for m in ('A','B','C')],
        'methods':{'A':'unchanged analytical; one M2',
            'B':'analytical-center sensitivity -> unchanged SLSQP; one M2',
            'C':'same B first shot -> paired Vreq/Kvco polls -> unused capacitor region'},
        'budget':'equal caps:96 M1 including child pre/posthoc,10000 cheap,6 slots including cache hits/failures',
        'cache':'new Stage6B source/protocol/parameter-bound shared cache; no historical Stage6A reuse',
        'rules':'no outcome tuning; no LLM; no BO; no measurement changes; A/B naturally stop after first candidate',
        'capture_interval':'fine +/- abs(coarse-fine) +/-1us block resolution; conservative hull superset',
        'normalization':'BW half-interval; PM lower limit; tuning0.6V; capture40us',
        'optional_B3':'read-only interface analysis, no alternate-initial-state formal run',
        'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]})

if __name__=='__main__':main()
