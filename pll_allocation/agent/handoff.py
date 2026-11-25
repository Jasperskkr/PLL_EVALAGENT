"""Versioned M1 nominal handoff only; no M2 invocation or candidate ranking."""
from copy import deepcopy
import os
from pathlib import Path

from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import check_candidate, judge, require
from ..physics_mapping.model import MappingResult, Status, fingerprint
from ..exploration.engine import model_identity

from ..contract_names import HANDOFF_SCHEMA, LEGACY_HANDOFF_SCHEMA, handoff_ready

SCHEMA = HANDOFF_SCHEMA
SUPPORTED_SCHEMAS = (SCHEMA, LEGACY_HANDOFF_SCHEMA)


def validate_handoff(handoff, *, require_current_model=True):
    """Strict gate for a saved nominal input; recomputes no physics or ranking.

    require_current_model=False checks recorded evidence for archival reading only;
    execution always requires the installed model. No evidence is rewritten.
    Uses the existing parameter screening and formal-result judge. Hash binding
    detects accidental edits, not maliciously forged or unauthenticated data.
    """
    require(isinstance(handoff, dict) and handoff.get('schema_version') in SUPPORTED_SCHEMAS, 'unsupported handoff schema')
    require(handoff.get('handoff_sha256') == fingerprint({k:v for k,v in handoff.items() if k!='handoff_sha256'}),
            'handoff fingerprint mismatch')
    require(handoff_ready(handoff) is True, 'handoff gate blocked: no rechecked feasible nominal')
    require(handoff.get('gate_status') == 'READY' and handoff.get('gate_reasons') == [],
            'handoff gate status/reasons disagree with ready flag')
    require(handoff['M2_status'] == 'NOT_EVALUATED' and handoff['FULL_SYSTEMSPEC_CERTIFIED'] is False,
            'handoff cannot certify M2 or complete SystemSpec')
    problem,context = handoff['problem'],handoff['source_context_binding']
    require(fingerprint({k:v for k,v in problem.items() if k!='problem_sha256'}) == problem['problem_sha256'] ==
            handoff['problem_sha256'], 'handoff problem binding mismatch')
    require(handoff['system_spec'] == problem['specs'], 'resolved SystemSpec mismatch')
    require(handoff['context_sha256'] == context['context_sha256'] and
            handoff['model_fingerprint'] == context['model_fingerprint'], 'context/model binding mismatch')
    if require_current_model:
        require(handoff['model_fingerprint'] == model_identity()['model_sha256'], 'handoff model differs from installed M1')
    row,check = handoff['recommended_nominal'],handoff['recommendation_recheck']
    require(row is not None and check.get('passed') is True and check.get('row') is not None,
            'handoff requires independent formal M1 recheck')
    fresh = check['row']
    require(fresh['formal_M1_called'] is True and fresh['independent_final_recheck'] is True and
            fresh['M1_status'] == row['M1_status'] == 'OK', 'nominal formal M1 evidence unavailable')
    require(check['source_evidence_id'] == row['evidence_id'] and check['evidence_id'] == fresh['evidence_id'],
            'recheck evidence linkage mismatch')
    require(fresh['parameter_sha256'] == row['parameter_sha256'] == fingerprint(row['parameters']) and
            fresh['parameters'] == row['parameters'], 'nominal/recheck parameter mismatch')
    require(set(handoff['block_spec_SI']) == set(FREE_IDS) and handoff['block_spec_SI'] ==
            {k:row['parameters']['values'][k] for k in FREE_IDS}, 'six-axis SI BlockSpec mismatch')
    for evidence in (row,fresh):
        require(evidence['problem_sha256'] == handoff['problem_sha256'] and
                evidence['model_fingerprint'] == handoff['model_fingerprint'], 'nominal model/problem mismatch')
        raw = evidence['formal_M1_result']
        result = MappingResult(**(raw | {'status':Status(raw['status'])}))
        require(result.status == Status.OK and result.metrics == evidence['metrics'] and
                result.parameter_sha256 == row['parameter_sha256'] and result.model_id == model_identity()['model_id'],
                'invalid formal M1 metrics/parameter/model binding')
        judgment = judge(problem,evidence['parameters'],result)
        require(judgment == evidence['judgment'] and judgment['m1_feasibility'] == 'FEASIBLE',
                'current supported M1 constraints not satisfied')
    require(fresh['metrics'] == row['metrics'] and fresh['judgment'] == row['judgment'],
            'nominal final recheck differs')
    require(check_candidate(problem,row['parameters'])['status'] == 'NECESSARY_CONDITIONS_SATISFIED',
            'nominal violates current original design domain')
    return deepcopy(row['parameters'])


def build_handoff(explorer, archive, recommended, recheck, states, cost, *, handoff_dir=None):
    item = {'schema_version':SCHEMA, 'ready_for_verification':False, 'gate_status':'BLOCKED',
        'gate_reasons':[], 'problem_sha256':explorer.problem['problem_sha256'],
        'context_sha256':explorer.context['context_sha256'],
        'model_fingerprint':explorer.context['model']['model_sha256'],
        'problem':deepcopy(explorer.problem), 'system_spec':deepcopy(explorer.problem['specs']),
        'source_context_binding':{'context_sha256':explorer.context['context_sha256'],
            'model_fingerprint':explorer.context['model']['model_sha256'],
            'path':str(explorer.context_path), 'evidence_artifacts':deepcopy(explorer.context['evidence_artifacts'])},
        'block_spec_SI':{k:deepcopy(recommended['parameters']['values'][k]) for k in FREE_IDS} if recommended else None,
        'recommended_nominal':deepcopy(recommended), 'recommendation_recheck':deepcopy(recheck),
        'other_candidate_references':[{'evidence_id':r['evidence_id'],'parameter_sha256':r['parameter_sha256'],
            'source':r['source'],'M1_status':r['M1_status'],'judgment':deepcopy(r['judgment']),
            'artifact':'candidate_archive.jsonl'} for r in archive.entries if r['judgment']['m1_feasibility']=='FEASIBLE'
            and (not recommended or r['parameter_sha256'] != recommended['parameter_sha256'])],
        'run_state':deepcopy(states), 'termination_reason':states['termination_reason'], 'cost':deepcopy(cost),
        'authoritative_nominal_field':'recommended_nominal',
        'legacy_fields_not_for_verification':['new_allocation','best_observed_current_spec','status'],
        'M2_status':'NOT_EVALUATED', 'FULL_SYSTEMSPEC_CERTIFIED':False,
        'scope':'M1-rechecked nominal input for existing M2; no verification feedback execution or whole-domain certification'}
    if not recommended:
        item['gate_reasons']=['NO_KNOWN_M1_FEASIBLE_CANDIDATE']
    elif not recheck.get('passed'):
        item['gate_reasons']=['FINAL_FORMAL_M1_RECHECK_NOT_PASSED']
    else:
        item.update(ready_for_verification=True,gate_status='READY')
    if handoff_dir is not None:
        try:
            relative = os.path.relpath(explorer.context_path, Path(handoff_dir).resolve())
        except ValueError:
            # Windows cannot express relative paths between different drives.
            # Existing externally supplied contexts retain their absolute binding.
            pass
        else:
            item['source_context_binding']['relative_path'] = Path(relative).as_posix()
    if recommended and 'physics_selection' in recommended:
        item['selection_evidence'] = deepcopy(recommended['physics_selection'])
    item['handoff_sha256']=fingerprint(item)
    if item['ready_for_verification']:
        try:validate_handoff(item)
        except (ValueError,KeyError,TypeError) as error:
            item.update(ready_for_verification=False,gate_status='BLOCKED',gate_reasons=[str(error)])
            item['handoff_sha256']=fingerprint({k:v for k,v in item.items() if k!='handoff_sha256'})
    return item
