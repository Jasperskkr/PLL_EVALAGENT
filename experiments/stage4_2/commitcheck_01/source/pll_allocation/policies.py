"""Complete-candidate proposal policies. No policy controls verification or verdicts."""
from __future__ import annotations
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time
from .contracts import candidate_grid, values_of, digest, canonical
from .behavioral import PHYSICS, screen, write_json

class RulePolicy:
    policy_id='physics_analytic_initial_v1'
    def propose(self,p,history,remaining):
        tried={x['candidate_sha256'] for x in history}
        bound=next(s['value'] for s in p['system_spec'] if s['metric']=='mean_phase_abs_deg')
        def rank(c):
            s=screen(p,c); v=values_of(c)
            return (max(0,s['metrics']['mean_phase_abs_deg']-bound),v['CP.I_up_A'],abs(v['CP.q0_C']),
                    abs(s['equilibrium_vctrl_V']-p['initialization']['Vctrl_V']),v['LF.Rz_Ohm'],digest(c))
        choices=sorted(candidate_grid(p),key=rank)
        candidate=next((c for c in choices if digest(c) not in tried),None)
        return None if candidate is None else {'candidate':candidate,'rationale':'Rank declared joint targets by analytic equilibrium phase, current, charge and tuning distance; full dynamic TB still required.'}

class GridPolicy:
    policy_id='finite_joint_grid_v1'
    def propose(self,p,history,remaining):
        tried={x['candidate_sha256'] for x in history}
        candidate=next((c for c in candidate_grid(p) if digest(c) not in tried),None)
        return None if candidate is None else {'candidate':candidate,'rationale':'Next complete joint point in declared finite grid; no TB answers used for ordering.'}

class RandomPolicy(GridPolicy):
    policy_id='seeded_random_joint_search_v1'
    def __init__(self,seed=0): self.seed=seed
    def propose(self,p,history,remaining):
        candidates=list(candidate_grid(p)); random.Random(self.seed).shuffle(candidates)
        tried={x['candidate_sha256'] for x in history}
        candidate=next((c for c in candidates if digest(c) not in tried),None)
        return None if candidate is None else {'candidate':candidate,'rationale':f'Seeded random finite-domain search; seed={self.seed}.'}

class FeedbackSearchPolicy(GridPolicy):
    policy_id='analytic_feedback_local_search_v1'
    def propose(self,p,history,remaining):
        if not history:
            proposal=super().propose(p,history,remaining)
            if proposal: proposal['rationale']='Initial finite-domain point, before any behavioral feedback.'
            return proposal
        tried={a['candidate_sha256'] for a in history}
        anchor=history[-1]; old=values_of(anchor['candidate'])
        violated={s['metric'] for s in anchor['diagnosis']['violations']}
        bound=next(s['value'] for s in p['system_spec'] if s['metric']=='mean_phase_abs_deg')
        def rank(c):
            v=values_of(c)
            phase_error=max(0,screen(p,c)['metrics']['mean_phase_abs_deg']-bound)/bound if 'mean_phase_abs_deg' in violated else 0
            changed=sum(old[k]!=v[k] for k in v)
            relative=sum(abs(v[k]-old[k])/max(abs(old[k]),1e-30) for k in v)
            return phase_error,changed,relative,digest(c)
        options=[c for c in candidate_grid(p) if digest(c) not in tried]
        if not options: return None
        return {'candidate':min(options,key=rank),
                'rationale':'Measured failed constraints '+','.join(sorted(violated))+'. Rank legal full candidates by remaining analytic phase violation and proximity to the measured point; require a new full transient TB for dynamics.'}

class ReplayPolicy:
    policy_id='saved_proposal_replay_v1'
    def __init__(self,source):
        self.source=Path(source)
        raw=json.loads(self.source.read_text(encoding='utf-8'))
        canonical(raw)
        self.proposals=raw if isinstance(raw,list) else [raw]
    def propose(self,p,history,remaining):
        if len(history)>=len(self.proposals): return None
        raw=deepcopy(self.proposals[len(history)])
        return {'candidate':raw.get('candidate',raw),'rationale':'Explicit offline replay; not a new LLM call.',
                'replay_source':str(self.source.resolve())}

class ServiceUnavailable(RuntimeError):
    pass

class LLMPolicy:
    """Native Messages HTTP adapter; configured provider, no mock/fallback proposals."""
    policy_id='physics_informed_llm_v1'
    def __init__(self,config,call_root):
        self.config=deepcopy(config); self.call_root=Path(call_root); self.calls=[]
        self.model=os.environ.get(config.get('model_env','ANTHROPIC_MODEL'),'') or config.get('model','')
        self.base=os.environ.get(config.get('base_url_env','ANTHROPIC_BASE_URL'),'')
        self.key=os.environ.get(config.get('api_key_env','ANTHROPIC_AUTH_TOKEN'),'')
    def propose(self,p,history,remaining):
        if not self.model or not self.base or not self.key:
            raise ServiceUnavailable('MISSING_CONFIGURED_LLM_ENVIRONMENT')
        call=self.call_root/f'call_{len(self.calls)+1:03d}'
        call.mkdir(parents=True,exist_ok=False)
        instructions=(
          'You allocate complete behavioral JointBlockSpecs for a fixed integer-N CP-PLL. '
          'You make the design choices and repair decisions. Return JSON only with keys action (PROPOSE or STOP), '
          'candidate (complete joint-block-spec-1.0), rationale. Do not claim PASS or modify SystemSpec. '
          'Candidate schema: {schema_version:"joint-block-spec-1.0", parameter_role:"DECLARED_TARGET", '
          'common_conditions: EXACT copy of operating_context, blocks: all PFD/CP/LF/VCO/Divider, '
          'each parameter: {value: finite number selected from its choices, unit: exact given unit}}. '
          'Use all required parameters and units from block_space. Never omit fixed parameters. '
          'First proposal must use only supplied problem and physical priors. On feedback, inspect measured violations, '
          'successful metrics and margins; choose coordinated local repair or full reallocation; return complete candidate. '
          'CP q0 already contains local proxy DC demand. Kvco is Hz/V, not rad/s/V. '
          'Transient lock cannot be guaranteed by equilibrium equations. Do not assume transistor realizability. '
          'No hardcoded adjustment rule is required: you choose which legal parameters to change. '
          'Stop if no justified proposal remains or the available budget cannot support verification.')
        payload={'problem':p,'physics':PHYSICS,'previous_attempts':history,'remaining_budget':remaining,
                 'candidate_schema':{'blocks':p['block_space']['blocks'],'parameter_role':'DECLARED_TARGET'},
                 'policy_version':self.policy_id}
        request={'model':self.model,'max_tokens':self.config.get('max_tokens',8000),
                 'system':instructions,'messages':[{'role':'user','content':canonical(payload)}]}
        write_json(call/'input.json',request)
        started=time.perf_counter()
        meta={'provider':self.config.get('provider','configured_messages_provider'),'model':self.model,
              'policy_version':self.policy_id,'real_network_call':True,'http_status':None,'usage':None}
        self.calls.append(meta)
        write_json(call/'transport_config.json',self.config)
        command=[sys.executable,'-B',str(Path(__file__).with_name('llm_transport.py')),
                 '--request',str((call/'input.json').resolve()),'--config',str((call/'transport_config.json').resolve()),
                 '--response',str((call/'response.json').resolve()),'--status',str((call/'transport_status.json').resolve())]
        try:
            process=subprocess.run(command,capture_output=True,timeout=self.config.get('timeout_s',60),shell=False,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            transport=json.loads((call/'transport_status.json').read_text(encoding='utf-8'))
            meta.update(transport)
            if process.returncode:
                raise ServiceUnavailable('LLM_TRANSPORT_'+transport.get('error_type','UNKNOWN'))
            raw=json.loads((call/'response.json').read_text(encoding='utf-8'))
            meta['usage']=raw.get('usage'); meta['response_model']=raw.get('model')
            content=''.join(x.get('text','') for x in raw.get('content',[]) if x.get('type')=='text').strip()
            if content.startswith('```'):
                content=content.split('\n',1)[1].rsplit('```',1)[0].strip()
            proposal=json.loads(content)
            canonical(proposal)
            write_json(call/'proposal.json',proposal)
            meta['status']='RESPONDED'
            if proposal.get('action')=='STOP': return None
            if proposal.get('action')!='PROPOSE' or not isinstance(proposal.get('candidate'),dict):
                raise ValueError('invalid proposal envelope')
            proposal['llm_call_index']=len(self.calls)
            return proposal
        except subprocess.TimeoutExpired:
            if (call/'transport_status.json').is_file():
                meta.update(json.loads((call/'transport_status.json').read_text(encoding='utf-8')))
            meta.update(status='SERVICE_UNAVAILABLE',error_type='TOTAL_PROCESS_TIMEOUT')
            raise ServiceUnavailable('LLM_TOTAL_PROCESS_TIMEOUT') from None
        except OSError as e:
            meta.update(status='SERVICE_UNAVAILABLE',error_type=type(e).__name__)
            raise ServiceUnavailable('LLM_TRANSPORT_'+type(e).__name__) from None
        except (ValueError,KeyError,TypeError) as e:
            meta.update(status='INVALID_RESPONSE',error_type=type(e).__name__)
            raise ServiceUnavailable('LLM_INVALID_STRUCTURED_RESPONSE') from None
        finally:
            meta['elapsed_s']=time.perf_counter()-started
            write_json(call/'metadata.json',meta)
