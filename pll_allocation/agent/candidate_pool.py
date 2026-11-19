"""Diversity and quality selection over the existing formal candidate archive."""
from copy import deepcopy
import math

from ..exploration.contracts import number, require
from ..region_explorer.assessment import normalized_point
from .candidates import rank

MODES = ('DETERMINISTIC', 'LLM_PHYSICS_GUIDED', 'AUTO_HYBRID')


def validate_pool_config(raw):
    fields = {'mode', 'target_count', 'minimum_margin', 'minimum_distance',
              'deterministic_rounds', 'llm_call_limit', 'allow_paid_llm'}
    require(isinstance(raw, dict) and fields <= set(raw) <= fields | {'excluded_hashes'}, 'complete candidate pool configuration required')
    c = deepcopy(raw)
    require(isinstance(c.get('excluded_hashes', []), list) and len(c.get('excluded_hashes', [])) <= 32 and
            all(isinstance(k, str) and len(k) == 64 for k in c.get('excluded_hashes', [])), 'invalid prior tested candidate identities')
    require(c['mode'] in MODES, 'unsupported allocation mode')
    require(type(c['target_count']) is int and 1 <= c['target_count'] <= 100, 'target_count must be 1..100')
    require(type(c['deterministic_rounds']) is int and 1 <= c['deterministic_rounds'] <= 10, 'deterministic_rounds must be 1..10')
    require(type(c['llm_call_limit']) is int and 0 <= c['llm_call_limit'] <= 20, 'llm_call_limit must be 0..20')
    require(type(c['allow_paid_llm']) is bool, 'explicit boolean LLM authorization required')
    require(number(c['minimum_margin'], 'minimum_margin') >= 0, 'nonnegative quality margin required')
    require(0 <= number(c['minimum_distance'], 'minimum_distance') <= math.sqrt(6), 'invalid normalized distance')
    return c


def distance(problem, a, b):
    x, y = (normalized_point(problem, row['parameters']) for row in (a, b))
    return math.sqrt(sum((x[k]-y[k])**2 for k in x))


def distinct_candidates(rows, problem, config, *, quality_only=False):
    """Stable greedy packing in the problem's six normalized (log/linear) axes.

    Keep the best margin in each neighborhood. All rejected evidence remains
    in CandidateArchive; this function grants no new verification authority.
    """
    selected, seen = [], set()
    for row in sorted(rows, key=rank):
        if row['judgment']['m1_feasibility'] != 'FEASIBLE':
            continue
        if quality_only and row['judgment']['minimum_normalized_margin'] < config['minimum_margin']:
            continue
        key = row['parameter_sha256']
        if key in seen:
            continue
        seen.add(key)
        if all(distance(problem, row, old) >= config['minimum_distance'] for old in selected):
            selected.append(row)
    return selected


def joint_candidates(rows, problem, config, passing_hashes):
    """Pack only quality-qualified M1 points with supported-M2 PASS evidence.

    The caller owns native/TEST provenance. Packing the passing subset avoids
    an unverified or failed neighbor hiding a valid delivery candidate.
    """
    passing_hashes = set(passing_hashes)
    return distinct_candidates([r for r in rows if r['parameter_sha256'] in passing_hashes],
                               problem, config, quality_only=True)


def select_m2(rows, problem, config, tested=(), passing=()):
    """Quality gate first, then distance from already tested points, then margin."""
    tested = list(tested)
    keys = {r['parameter_sha256'] for r in tested}
    # Filter before packing: an already tested neighbor must not hide a new
    # alternative, while near-duplicates of delivered points add no value.
    remaining = [r for r in rows if r['parameter_sha256'] not in keys and
                 all(distance(problem, r, old) >= config['minimum_distance'] for old in passing)]
    eligible = distinct_candidates(remaining, problem, config, quality_only=True)
    if not tested:
        return min(eligible, key=rank, default=None)
    return min(eligible, key=lambda r: (-min(distance(problem, r, old) for old in tested), rank(r)), default=None)
