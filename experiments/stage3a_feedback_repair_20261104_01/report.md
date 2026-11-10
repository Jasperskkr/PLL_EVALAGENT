# Unified PLL run: stage3a_feedback_repair_20261104_01

Status: M2_PARTIAL_PASS
Strategy: random; origin: NEW_ALLOCATION
Full behavioral PASS: False

M1 prediction and independently measured M2 are separate. Partial BW acceptance retains overall UNKNOWN.

## FIRST_SHOT: M1_FAIL / M2_FAIL

|Required metric|M2 status|
|---|---|
|output_frequency_Hz|UNKNOWN|
|BW_Hz|FAIL|
|PM_deg|UNKNOWN|
## FEEDBACK_REPAIR: M1_PASS / M2_PARTIAL_PASS

|Required metric|M2 status|
|---|---|
|output_frequency_Hz|UNKNOWN|
|BW_Hz|PASS|
|PM_deg|UNKNOWN|

Cost: {"analytic_calls": 160, "M1_calls": 11, "candidate_generations": 16, "M2_calls": 2, "LLM_calls": 0, "native_completed_runs": 220, "native_failed_attempts": 0, "integration_points": 189333926, "native_elapsed_s": 6.260832399857463, "native_failure_elapsed_s": 0, "M1_posthoc_calls": 2, "M1_total_calls": 13, "total_elapsed_s": 22.151192499994067, "monetary_cost": null}
Failure: null
