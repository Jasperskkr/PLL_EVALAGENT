# Unified PLL run: postmerge_baseline

Status: M2_PARTIAL_PASS
Strategy: analytical; origin: NEW_ALLOCATION
Full behavioral PASS: False

M1 prediction and independently measured M2 are separate. Partial BW acceptance retains overall UNKNOWN.

## FIRST_SHOT: M1_PASS / M2_PARTIAL_PASS

|Required metric|M2 status|
|---|---|
|output_frequency_Hz|UNKNOWN|
|BW_Hz|PASS|
|PM_deg|UNKNOWN|

Cost: {"analytic_calls": 11, "M1_calls": 1, "candidate_generations": 6, "M2_calls": 1, "LLM_calls": 0, "native_completed_runs": 106, "native_failed_attempts": 0, "integration_points": 95090315, "native_elapsed_s": 2.9994541998021305, "native_failure_elapsed_s": 0, "M1_posthoc_calls": 1, "M1_total_calls": 2, "total_elapsed_s": 9.53721979999682, "monetary_cost": null}
Failure: null
