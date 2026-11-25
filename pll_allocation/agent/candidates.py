"""Append-only current-problem evidence archive; no model or solver authority."""
from copy import deepcopy
from ..contract_names import current_label
import math

from ..exploration.contracts import check_candidate, judge, require
from ..physics_mapping.model import MappingResult, Status, fingerprint


def material_change(before, after, *, absolute=1e-6, relative=1e-6):
    threshold = max(absolute, relative*max(abs(before or 0.), abs(after or 0.)))
    delta = after-before if before is not None and after is not None else None
    return {'delta': delta, 'threshold': threshold,
            'material': after is not None and (before is None or delta > threshold)}


def rank(row):
    """Feasibility, maximin supported bound margin, then exact parameter identity."""
    return (0 if row['judgment']['m1_feasibility'] == 'FEASIBLE' else 1,
            -row['judgment']['minimum_normalized_margin'], row['parameter_sha256'])


class CandidateArchive:
    def __init__(self, explorer, path):
        self.explorer, self.path = explorer, path
        self.entries, self.seen, self.rejected = [], set(), []
        path.touch(exist_ok=False)
        self.sync()

    def sync(self):
        """All original evidence remains on disk even when revalidation excludes it."""
        import json
        for source, rows in [('M1_CALIBRATION', self.explorer.calibration_samples),
                             ('M1_SEARCH', self.explorer.rows)]:
            for row in rows:
                sid = row['evidence_id']
                if sid in self.seen:
                    continue
                self.seen.add(sid)
                raw = row.get('formal_M1_result')
                if not raw:
                    continue  # Exact cache references are persisted by the executor, not new model evidence.
                try:
                    require(row['M1_status'] == 'OK', 'non-OK formal evidence')
                    require(row['problem_sha256'] == self.explorer.problem['problem_sha256'], 'problem binding mismatch')
                    require(row['model_fingerprint'] == self.explorer.context['model']['model_sha256'], 'model binding mismatch')
                    require(row['parameter_sha256'] == fingerprint(row['parameters']), 'parameter binding mismatch')
                    result = MappingResult(**(raw | {'status': Status(raw['status'])}))
                    judgment = judge(self.explorer.problem, row['parameters'], result)
                    screening = check_candidate(self.explorer.problem, row['parameters'])
                    require(result.status == Status.OK and screening['status'] == 'NECESSARY_CONDITIONS_SATISFIED',
                            'formal result or current-domain screening invalid')
                    margin = judgment['minimum_normalized_margin']
                    require(margin is not None and math.isfinite(margin), 'finite supported bound margin required')
                except (AssertionError, ValueError, TypeError, KeyError) as error:
                    self.rejected.append({'evidence_id': sid, 'reason': 'Inapplicable/non-OK formal evidence: '+type(error).__name__})
                    continue
                item = {k: deepcopy(row[k]) for k in ('evidence_id', 'origin', 'parameters', 'parameter_sha256',
                         'problem_sha256', 'model_fingerprint')}
                scope = 'FINAL_RECOMMENDATION_RECHECK' if row['origin'] == 'RECOMMENDATION:FINAL_RECHECK' else source
                item.update(source=scope, M1_status='OK', formal_M1_result=deepcopy(raw),
                            metrics=deepcopy(result.metrics), judgment=judgment, screening=screening)
                if getattr(self.explorer, 'conditional_physics', None) is not None:
                    item.update(self.explorer.conditional_physics.describe(row['parameters']))
                    if 'conditional_noise_status' in item:
                        item['joint_conditional_feasibility'] = ('CONDITIONAL_FEASIBLE' if
                            judgment['m1_feasibility'] == 'FEASIBLE' and self.explorer.conditional_physics.qualified(item)
                            else 'NOT_ESTABLISHED')
                self.entries.append(item)
                with self.path.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(item, ensure_ascii=False, allow_nan=False)+'\n')

    def best(self, source=None, *, feasible_only=False):
        rows = [r for r in self.entries if (source is None or current_label(r['source']) == current_label(source))
                and (not feasible_only or r['judgment']['m1_feasibility'] == 'FEASIBLE')]
        return min(rows, key=rank, default=None)

    def summary(self, *, absolute=1e-6, relative=1e-6):
        self.sync()
        old, new, known = self.best('M1_CALIBRATION'), self.best('M1_SEARCH'), self.best()
        def compact(row):
            return deepcopy(row) if row else None
        improvement = material_change(old['judgment']['minimum_normalized_margin'] if old else None,
                                      known['judgment']['minimum_normalized_margin'] if known else None,
                                      absolute=absolute, relative=relative)
        improvement['feasibility_transition'] = bool(known and known['judgment']['m1_feasibility'] == 'FEASIBLE'
            and (not old or old['judgment']['m1_feasibility'] != 'FEASIBLE'))
        return {'best_known': compact(known), 'best_calibration': compact(old), 'best_new': compact(new),
                'improvement_over_calibration': improvement,
                'ranking_rule': 'FEASIBLE first; maximum minimum normalized supported-bound margin; exact parameter SHA256 tie-break; stable first evidence on equal parameters',
                'valid_evidence_count': len(self.entries), 'rejected_evidence': deepcopy(self.rejected)}
