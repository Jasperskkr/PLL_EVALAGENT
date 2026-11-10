# Unified PLL run: S1__llm_agent

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

Cost: {"analytic_calls": 6, "M1_calls": 2, "candidate_generations": 3, "M2_calls": 1, "LLM_calls": 3, "native_completed_runs": 106, "native_failed_attempts": 0, "integration_points": 95724491, "native_elapsed_s": 2.8516716999583878, "native_failure_elapsed_s": 0, "M1_posthoc_calls": 1, "M1_total_calls": 3, "total_elapsed_s": 36.56693329999689, "monetary_cost": null}
Failure: null
