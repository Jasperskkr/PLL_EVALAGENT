"""Public responsibility names and explicit read compatibility for old contracts.

Only unsigned configuration values are normalized. Signed evidence is validated
in its recorded form and is never recursively renamed or rehashed on read.
"""
from copy import deepcopy

HANDOFF_SCHEMA = 'pll-m1-verification-handoff-2.0'
LEGACY_HANDOFF_SCHEMA = 'pll-stage9-nominal-handoff-1.0'
FEEDBACK_SCHEMA = 'pll-verification-feedback-2.0'
LEGACY_FEEDBACK_SCHEMA = 'pll-stage9-feedback-1.0'
RESULT_SCHEMA = 'pll-verification-result-2.0'

LABEL_ALIASES = {
    'STAGE7_CALIBRATION': 'M1_CALIBRATION',
    'STAGE8B_SEARCH': 'M1_SEARCH',
    'DETERMINISTIC_PHYSICS_STAGE7': 'DETERMINISTIC_PHYSICS_EXPLORATION',
    'LLM_GUIDED_STAGE7_5': 'LLM_GUIDED_SUBREGION_EXPLORATION',
    'STAGE7_5_EXPLORATION': 'SUBREGION_M1_EXPLORATION',
}


def current_label(value):
    return LABEL_ALIASES.get(value, value)


def handoff_ready(item):
    """Read the readiness field belonging to the declared contract version."""
    version = item.get('schema_version')
    if version == HANDOFF_SCHEMA:
        if 'ready_for_stage9' in item or 'legacy_fields_not_for_stage9' in item:
            raise ValueError('legacy handoff fields require the legacy schema')
        return item.get('ready_for_verification')
    if version == LEGACY_HANDOFF_SCHEMA:
        if 'ready_for_verification' in item:
            raise ValueError('mixed handoff contract versions')
        return item.get('ready_for_stage9')
    raise ValueError('unsupported handoff schema')


def problem_matches_handoff(current, handoff):
    """Compare the current input against its declared historical resolution.

    Only the old generated unsupported-metric label may differ. The recorded
    problem, candidate IDs, evidence and fingerprints are never modified.
    """
    if current == handoff['problem']:
        return True
    if handoff['schema_version'] != LEGACY_HANDOFF_SCHEMA:
        return False
    from .physics_mapping.model import fingerprint
    legacy = deepcopy(current)
    legacy.pop('problem_sha256')
    for spec in legacy['specs']:
        if spec['protocol'] == 'NOT_EVALUATED_BY_M1':
            spec['protocol'] = 'NOT_EVALUATED_IN_STAGE7'
    legacy['problem_sha256'] = fingerprint(legacy)
    return legacy == handoff['problem']
