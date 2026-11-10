"""Attach completed evidence to the new model; preserve the validation input snapshot."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.block_space.validation import write_new


def main():
    path=ROOT/'configs/BLOCK_SPACE_MODEL_V1.json'
    old=json.loads(path.read_text(encoding='utf-8'))
    if old['validation_evidence']['status']!='PENDING_DOMAIN_SCAN':
        raise ValueError('already finalized; do not overwrite evidence')
    run=ROOT/'outputs/block_space_v1_20261104_01'
    summary=json.loads((run/'summary.json').read_text(encoding='utf-8'))
    snapshot=json.loads((run/'model_snapshot.json').read_text(encoding='utf-8'))
    assert snapshot==old and summary['numerical_acceptance']=='PASS'
    new=deepcopy(old)
    new['validation_evidence']={
        'status':'M1_DOMAIN_SCAN_COMPLETE_SPARSE_EVENT_CHECKS',
        'report':'docs/stage1_5/DOMAIN_VALIDATION_REPORT.md',
        'per_case_evidence_required':True,'coverage_claim':'representative_samples_not_entire_domain',
        'validated_experiment_sha256':fingerprint(old['experiment']),
        'validation_input_model_sha256':fingerprint(snapshot),
        'summary':'outputs/block_space_v1_20261104_01/summary.json',
        'summary_file_sha256':hashlib.sha256((run/'summary.json').read_bytes()).hexdigest(),
        'numerical_cases':summary['valid_M1_count'],'event_checked_cases':summary['event_completed_count'],
        'event_frequency_control_agreement_cases':len(summary['event_conditional_agreement_ids']),
        'BW_PM_UGF_behavioral_validation':'NOT_ESTABLISHED',
        'reference_blockspec':'outputs/block_space_v1_20261104_01/REFERENCE_BLOCKSPEC.json',
        'known_weak_region':'near-rail tuning; see C130 160us and 640us diagnostics; no domain-wide capture guarantee',
    }
    for name in ('output_frequency_Hz','BW_Hz','PM_deg','UGF_Hz'):
        new['metric_support'][name]['evidence']='outputs/block_space_v1_20261104_01/FORWARD_MODEL_VALIDATION.csv'
    new['metric_support']['output_frequency_Hz']['behavioral_validation']='SPARSE_CONDITIONAL_EVENT_FREQUENCY_CONTROL_CHECKS_ONLY'
    assert old['experiment']==new['experiment'] and old['variables']==new['variables'] and old['versions']==new['versions']
    # This changes only the new Stage 1.5 model's evidence metadata; the input used in the run is retained.
    with path.open('w',encoding='utf-8') as stream:
        json.dump(new,stream,indent=2,ensure_ascii=False,allow_nan=False)
        stream.write('\n')
    write_new(ROOT/'docs/stage1_5/MODEL_FINALIZATION.json',{
        'input_snapshot':'outputs/block_space_v1_20261104_01/model_snapshot.json',
        'input_model_sha256':fingerprint(old),'final_model_sha256':fingerprint(new),
        'semantic_experiment_sha256':fingerprint(new['experiment']),
        'changes':'evidence metadata only; variables, domains, SystemSpec, formulas and model versions identical'})
    print('Finalized evidence metadata; frozen Stage 1 inputs and all validation outputs unchanged.')


if __name__=='__main__':
    main()
