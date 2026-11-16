"""Orthogonal run summaries derived only from actual decisions/observations."""
from collections import Counter


def optimization_executed(record):
    """An accepted request or a seed Probe is not an executed SLSQP start."""
    return any(s['solver'] == 'scipy.optimize.SLSQP' and s['status'] != 'SKIPPED_BUDGET'
               for o in record['observations'] for s in o['solver_runs'])


def quality_state(candidate, target, recheck=None):
    """A quality threshold is additional to supported-M1 feasibility."""
    feasible = bool(candidate and candidate.get('judgment',candidate).get('m1_feasibility') == 'FEASIBLE')
    judgment = candidate.get('judgment',candidate) if candidate else {}
    margin = judgment.get('minimum_normalized_margin', judgment.get('worst_normalized_margin'))
    met = feasible and margin is not None and margin >= target
    status = ('NO_FEASIBLE_CANDIDATE' if not feasible else 'UNVERIFIED_RECHECK_FAILED' if
              recheck is not None and not recheck.get('passed') else 'REACHED' if met else 'NOT_REACHED')
    return {'status':status, 'quality_target':target, 'minimum_normalized_margin':margin,
            'target_met_on_saved_M1':bool(met),
            'recommendation_recheck_passed':recheck.get('passed') if recheck is not None else None}


def run_state(termination_reason, history, archive, recommendation_check):
    solver = Counter(s['status'] for record in history for o in record['observations'] for s in o['solver_runs'])
    feedback_searches = sum(optimization_executed(r) for r in history[1:])
    feedback_proposals = sum(r['decision']['action'] == 'OPTIMIZE' for r in history[1:])
    feedback_stops = sum(r['decision']['action'] == 'STOP' for r in history[1:])
    feedback = ('FEEDBACK_OPTIMIZED_THEN_STOPPED' if feedback_searches and feedback_stops else
                'FEEDBACK_REOPTIMIZED' if feedback_searches else 'FEEDBACK_READ_AND_STOPPED' if feedback_stops else
                'FEEDBACK_ACTION_ACCEPTED_NO_OPTIMIZATION_EXECUTED' if feedback_proposals else
                'NO_ACCEPTED_FEEDBACK_DECISION')
    best = archive.best(feasible_only=True)
    slsqp = [s for r in history for o in r['observations'] for s in o['solver_runs']
             if s['solver'] == 'scipy.optimize.SLSQP']
    return {'termination_reason': termination_reason,
            'm1_allocation_status': ('KNOWN_M1_FEASIBLE_RECHECKED' if best and recommendation_check.get('passed') else
                'KNOWN_M1_FEASIBLE_RECHECK_FAILED_OR_UNAVAILABLE' if best else 'NO_KNOWN_M1_FEASIBLE_CANDIDATE'),
            'solver_execution_status': {'status': 'NOT_RUN' if not solver else 'OBSERVED', 'counts': dict(solver),
                'started':sum(s['status'] != 'SKIPPED_BUDGET' for s in slsqp),
                'converged':sum(s['status'] == 'CONVERGED' for s in slsqp),
                'not_converged':sum(s['status'] == 'NOT_CONVERGED' for s in slsqp),
                'budget_exhausted':sum(s['status'] == 'BUDGET_EXHAUSTED' for s in slsqp),
                'exceptions':sum(s['status'] == 'SOLVER_EXCEPTION' for s in slsqp),
                'skipped_budget':sum(s['status'] == 'SKIPPED_BUDGET' for s in slsqp)},
            'feedback_loop_status': feedback, 'feedback_reoptimization_count': feedback_searches,
            'feedback_stop_count': feedback_stops, 'feedback_optimization_proposal_count': feedback_proposals,
            'optimization_execution_count': sum(optimization_executed(r) for r in history)}
