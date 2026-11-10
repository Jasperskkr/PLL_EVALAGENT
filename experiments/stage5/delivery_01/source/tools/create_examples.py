"""Build versioned examples from read-only snapshots; not needed at runtime."""
from copy import deepcopy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def create():
    anchor=json.loads((ROOT/'data/legacy/models.json').read_text(encoding='utf-8-sig'))['VCO']
    source='PLL_SPEC_ALLOC_BASELINE/configs/system_80m_phase.yaml (byte snapshot: data/legacy/system_80m_phase.yaml)'
    def axis(unit,values): return {'unit':unit,'choices':values}
    currents=[8e-5,9e-5,1e-4,1.1e-4,1.2e-4]
    p={'schema_version':'pll-allocation-1.0','task_id':'regular80_nonzero',
       'topology':{'id':'integer_n_cppll','blocks':['PFD','CP','LF','VCO','Divider'],
                   'connections':[['PFD','CP'],['CP','LF'],['LF','VCO'],['VCO','Divider'],['Divider','PFD']]},
       'operating_context':{'fref_Hz':1e7,'N':8,'fout_target_Hz':8e7,'VDD_V':1.8,'temperature_C':27.0,
          'charge_definition':'net_balance_charge_including_local_proxy_demand','phase_convention':'feedback_minus_reference'},
       'initialization':{'Vctrl_V':1.1774,'Vc2_V':1.1774,'feedback_error_cycles':0.0},
       'measurement':{'duration_s':4e-5,'tail_cycles':50,'lock_phase_deg':5.0,'lock_frequency_ppm':100.0,'lock_hold_cycles':20},
       'system_spec':[
          {'metric':'mean_phase_abs_deg','operator':'<=','value':0.2,'unit':'deg','measurement':'final_50_complete_reference_cycles','tolerance':0.0,'source':source},
          {'metric':'tail_max_abs_frequency_error_ppm','operator':'<=','value':100.0,'unit':'ppm','measurement':'final_50_complete_reference_cycles','tolerance':0.0,'source':source},
          {'metric':'lock_status','operator':'==','value':'LOCKED','unit':'1','measurement':'frozen_lock_protocol_v1','tolerance':0.0,'source':source}],
       'block_space':{'parameter_role':'DECLARED_TARGET','source':'legacy suite phase_0p2deg_nonzero_q0; explicit finite declared targets',
          'validity':{'model_id':'signed_charge_exact_ideal_rc_linear_vco_v1','empirical_accuracy':'NOT_ESTABLISHED_FOR_NEW_TARGETS',
                      'load_model':'local_proxy_dc_in_q0_incremental_conductance_omitted'},
          'couplings':[{'type':'equal','left':'CP.I_up_A','right':'CP.I_down_A'}],
          'blocks':{'PFD':{'reset_s':axis('s',[2e-9])},
           'CP':{'I_up_A':axis('A',currents),'I_down_A':axis('A',currents),'q0_C':axis('C',[6e-15,8e-15,1e-14])},
           'LF':{'Rz_Ohm':axis('Ohm',[3820.,5000.]),'C1_F':axis('F',[1e-10]),'C2_F':axis('F',[1e-9]),'Cload_F':axis('F',[5e-14]),'Rload_Ohm':axis('Ohm',[1e9])},
           'VCO':{'V0_V':axis('V',[anchor['V0_V']]),'f0_Hz':axis('Hz',[anchor['f0_Hz']]),'Kvco_Hz_per_V':axis('Hz/V',[anchor['Kvco_Hz_per_V']]),
                  'voltage_min_V':axis('V',[1.13]),'voltage_max_V':axis('V',[1.21])},
           'Divider':{'N':axis('1',[8])}}}}
    examples={'regular80':p}
    tight=deepcopy(p); tight['task_id']='tight80_0p19deg'; tight['system_spec'][0].update(value=0.19,source='legacy suite: phase_0p19deg_nonzero_q0; unchanged threshold')
    examples['tight80']=tight
    failed=deepcopy(p); failed['task_id']='finite_domain80_0p1deg'; failed['system_spec'][0].update(value=0.1,source='legacy suite: impossible_0p1deg_nonzero_q0; no global infeasibility claim')
    examples['finite_domain80']=failed
    frozen=deepcopy(p); frozen['task_id']='frozen80_original'; frozen['block_space']['blocks']['CP']['q0_C']['choices']=[i*2e-15 for i in range(-5,6)]
    frozen['block_space']['source']='original 80MHz frozen declaration including q0=0 ideal target assumption'
    examples['frozen80']=frozen
    triplet=deepcopy(p); triplet['task_id']='joint84'; triplet['operating_context'].update(fref_Hz=10.5e6,fout_target_Hz=84e6)
    for s in triplet['system_spec']: s['source']='legacy triplet_84m_comparison.yaml; unchanged SystemSpec and 40us measurement'
    blocks=triplet['block_space']['blocks']; blocks['CP']['q0_C']['choices']=[2e-15,4e-15,6e-15,8e-15,1e-14]
    blocks['VCO']['f0_Hz']['choices']=[anchor['f0_Hz']+d for d in (0.,2e6,4e6)]
    blocks['VCO']['Kvco_Hz_per_V']['choices']=[anchor['Kvco_Hz_per_V']*f for f in (.8,1.,1.2)]
    triplet['block_space']['source']='legacy 84MHz CP/LF/VCO 450-point declared grid; no module evidence dependency'
    examples['joint84']=triplet
    unsupported=deepcopy(p); unsupported['task_id']='unsupported_jitter80'
    unsupported['system_spec'].append({'metric':'integrated_jitter_s','operator':'<=','value':1e-12,'unit':'s','measurement':'integrated_phase_noise_10k_10M','tolerance':0.,'source':'new negative acceptance test; backend has no noise model'})
    examples['unsupported_jitter80']=unsupported
    folder=ROOT/'examples'; folder.mkdir(exist_ok=True)
    for name,example in examples.items():
        with (folder/(name+'.json')).open('x',encoding='utf-8') as f: json.dump(example,f,ensure_ascii=False,indent=2)
    print('created',len(examples),'examples')

if __name__=='__main__': create()
