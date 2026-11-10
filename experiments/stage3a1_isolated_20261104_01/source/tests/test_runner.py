from copy import deepcopy
import json
from pathlib import Path
import sys
from pll_allocation.behavioral import PythonBehavioralBackend, CommandBehavioralBackend, write_json
from pll_allocation.contracts import digest, canonical, candidate_grid
from pll_allocation.policies import GridPolicy, RulePolicy, ReplayPolicy, LLMPolicy, FeedbackSearchPolicy
from pll_allocation.runner import run
from test_contracts import ROOT,problem
import pytest

class SavingProbe(PythonBehavioralBackend):
    def run(self,p,c,workdir):
        assert (workdir.parents[1]/'initial_joint_block_spec.json').is_file()
        assert json.loads((workdir/'proposal.json').read_text(encoding='utf-8'))['candidate']==c
        return super().run(p,c,workdir)

def test_first_proposal_saved_before_tb(tmp_path):
    result=run(problem(),RulePolicy(),tmp_path/'run',budget=2,backend=SavingProbe())
    assert result['metrics']['first_pass_feasible']
    assert result['metrics']['behavioral_evaluations']==1
    assert result['independent_physical_qualification']=='UNKNOWN'

def test_real_fail_then_reallocation_and_trace(tmp_path):
    out=tmp_path/'grid'; result=run(problem(),GridPolicy(),out,budget=30)
    trace=[json.loads(x) for x in (out/'allocation_trace.jsonl').read_text(encoding='utf-8').splitlines()]
    assert trace[0]['attempt']['judgement']['verdict']=='FAIL'
    assert result['status']=='VERIFIED_BEHAVIORAL_PASS'
    assert result['metrics']['evaluations_to_first_feasible']>1
    assert not result['metrics']['first_pass_feasible']
    assert trace[0]['attempt']['candidate']!=trace[-1]['attempt']['candidate']
    previous='0'*64
    for event in trace:
        assert event['previous_sha256']==previous
        checksum=event.pop('event_sha256'); assert digest(event)==checksum; previous=checksum

def test_budget_and_finite_domain_failure_are_honest(tmp_path):
    r=run(problem('finite_domain80'),GridPolicy(),tmp_path/'run',budget=30)
    assert r['status']=='BUDGET_EXHAUSTED'
    assert r['metrics']['behavioral_evaluations']==30
    assert not r['final_candidate_verified']
    assert r['metrics']['evaluations_to_first_feasible'] is None

def test_invalid_proposal_no_tb_cost(tmp_path):
    p=problem(); candidate=next(candidate_grid(p)); candidate['blocks'].pop('CP')
    file=tmp_path/'invalid.json'; write_json(file,candidate)
    r=run(p,ReplayPolicy(file),tmp_path/'run',budget=2)
    assert r['metrics']['behavioral_evaluations']==0
    assert r['metrics']['proposal_attempts']==1

def test_exception_counts_and_unknown(tmp_path):
    class Broken(PythonBehavioralBackend):
        def run(self,*args): raise TimeoutError('failed simulator')
    r=run(problem(),GridPolicy(),tmp_path/'run',budget=2,backend=Broken())
    assert r['metrics']['behavioral_evaluations']==2
    assert not r['final_candidate_verified']
    rows=json.loads((tmp_path/'run/behavioral_tb_results.json').read_text(encoding='utf-8'))
    assert all(row['verdict']['verdict']=='UNKNOWN' for row in rows)

def test_reproducible_and_no_overwrite(tmp_path):
    p=problem(); one=tmp_path/'one'; two=tmp_path/'two'
    first=run(p,GridPolicy(),one,budget=3); second=run(p,GridPolicy(),two,budget=3)
    assert first['decision_sha256']==second['decision_sha256']
    for name in ('input_system_spec.json','initial_joint_block_spec.json','final_joint_block_spec.json'):
        assert (one/name).read_bytes()==(two/name).read_bytes()
    old=(one/'run_manifest.json').read_bytes()
    with pytest.raises(FileExistsError): run(p,RulePolicy(),one)
    assert (one/'run_manifest.json').read_bytes()==old

def test_missing_llm_environment_never_falls_back(tmp_path,monkeypatch):
    for name in ('MISSING_LLM_KEY','MISSING_LLM_MODEL','MISSING_LLM_URL'): monkeypatch.delenv(name,raising=False)
    policy=LLMPolicy({'model_env':'MISSING_LLM_MODEL','base_url_env':'MISSING_LLM_URL','api_key_env':'MISSING_LLM_KEY'},tmp_path/'run/llm_calls')
    r=run(problem(),policy,tmp_path/'run',budget=2)
    assert r['status']=='POLICY_UNAVAILABLE'
    assert r['metrics']['llm_calls']==0 and r['metrics']['behavioral_evaluations']==0
    assert not (tmp_path/'run/initial_joint_block_spec.json').exists()

def test_command_bridge_uses_real_inner_tb(tmp_path):
    worker=tmp_path/'worker.py'
    worker.write_text('''import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from pll_allocation.behavioral import PythonBehavioralBackend,write_json
r=json.loads(Path('request.json').read_text(encoding='utf-8'))
out=PythonBehavioralBackend().run(r['problem'],r['candidate'],Path.cwd())
write_json('response.json',out)
''',encoding='utf-8')
    caps=PythonBehavioralBackend().capabilities()
    backend=CommandBehavioralBackend([sys.executable,'-B',str(worker),str(ROOT)],caps)
    r=run(problem(),RulePolicy(),tmp_path/'run',budget=1,backend=backend)
    assert r['final_candidate_verified']
    assert (tmp_path/'run/attempts/001/stdout.log').exists()

def test_policy_cannot_mutate_frozen_problem(tmp_path):
    class Mutating(RulePolicy):
        def propose(self,p,h,r):
            result=super().propose(p,h,r); p['system_spec'][0]['value']=999
            return result
    p=problem(); fingerprint=digest(p)
    r=run(p,Mutating(),tmp_path/'run',budget=1)
    assert digest(p)==fingerprint==r['input_sha256']

def test_feedback_repair_uses_real_failure(tmp_path):
    result=run(problem(),FeedbackSearchPolicy(),tmp_path/'run',budget=3)
    assert result['status']=='VERIFIED_BEHAVIORAL_PASS'
    assert result['metrics']['evaluations_to_first_feasible']==2
    rows=[json.loads(row)['attempt'] for row in (tmp_path/'run/allocation_trace.jsonl').read_text(encoding='utf-8').splitlines()]
    assert rows[0]['judgement']['verdict']=='FAIL'
    assert 'mean_phase_abs_deg' in rows[1]['rationale']

def test_key_order_does_not_change_grid_or_decisions(tmp_path):
    p=problem(); reordered=json.loads(canonical(p))
    assert list(candidate_grid(p))==list(candidate_grid(reordered))

def test_unsupported_stops_without_wasting_budget(tmp_path):
    result=run(problem('unsupported_jitter80'),RulePolicy(),tmp_path/'run',budget=30)
    assert result['status']=='UNSUPPORTED_SYSTEM_SPEC'
    assert result['metrics']['behavioral_evaluations']==1

def test_llm_total_timeout_is_honest(tmp_path,monkeypatch):
    import subprocess
    import pll_allocation.policies as module
    for name,value in [('UNIT_MODEL','unit_transport_test'),('UNIT_URL','http://unused.invalid'),('UNIT_KEY','test-only')]:
        monkeypatch.setenv(name,value)
    def timed_out(*args,**kwargs): raise subprocess.TimeoutExpired('isolated-transport',0.01)
    monkeypatch.setattr(module.subprocess,'run',timed_out)
    policy=LLMPolicy({'model_env':'UNIT_MODEL','base_url_env':'UNIT_URL','api_key_env':'UNIT_KEY','timeout_s':0.01},tmp_path/'run/llm_calls')
    result=run(problem(),policy,tmp_path/'run',budget=2)
    assert result['status']=='POLICY_UNAVAILABLE'
    assert result['reason']=='LLM_TOTAL_PROCESS_TIMEOUT'
    assert not result['final_candidate_verified']
    assert result['metrics']['behavioral_evaluations']==0
    assert 'test-only' not in (tmp_path/'run/llm_calls/call_001/input.json').read_text(encoding='utf-8')
