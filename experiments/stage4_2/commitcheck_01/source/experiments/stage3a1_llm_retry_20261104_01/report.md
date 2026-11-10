# Unified PLL run: stage3a1_llm_retry_20261104_01

Status: M2_PARTIAL_PASS
Strategy: llm_agent; origin: NEW_ALLOCATION
Full behavioral PASS: False

M1 prediction and independently measured M2 are separate. Partial BW acceptance retains overall UNKNOWN.

## FIRST_SHOT: M1_PASS / M2_PARTIAL_PASS

|Required metric|M2 status|
|---|---|
|output_frequency_Hz|UNKNOWN|
|BW_Hz|PASS|
|PM_deg|UNKNOWN|

Cost: {"analytic_calls": 11, "M1_calls": 2, "candidate_generations": 6, "M2_calls": 1, "LLM_calls": 3, "native_completed_runs": 106, "native_failed_attempts": 0, "integration_points": 95090315, "native_elapsed_s": 3.123564600246027, "native_failure_elapsed_s": 0, "M1_posthoc_calls": 1, "M1_total_calls": 3, "total_elapsed_s": 41.243807399994694, "monetary_cost": null}
Failure: null
