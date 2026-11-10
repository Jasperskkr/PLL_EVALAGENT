# Stage 5 predeclared experiment plan

2026-11-05; resumed by user after master consolidation. HEAD cd70cf4. Original request: TASK_REQUEST.md. Authoritative machine plan: experiments/stage5/experiment_plan_frozen.json; scenarios: experiments/stage5/scenarios/S0–S4.json. These files are frozen before implementation and new scenario M2 runs.

|Scenario|BW (kHz)|PM minimum (deg)|
|---|---:|---:|
|S0|150–300|50|
|S1|180–230|60|
|S2|240–280|55|
|S3|290–300|50|
|S4|150–300|73|

All use unchanged 10 MHz × 8, ideal fixed topology, six-axis declared space, original equations, native physics and Protocol1.1. Frozen spec retains original draft metadata and 1 µHz frequency tolerance. The pre-pause real Baseline and postmerge exact regression satisfy P0; a fresh post-interface frozen Baseline is required for compatibility.

Analytical submits existing solver's first official candidate. Random uses existing pure uniform sampler with seeds **11,23,47**, uniform discrete capacitor choices and linear uniform continuous variables in original model order. One draw per seed, no target screening, rejection search or hidden analytical call. Invalid domain proposals remain recorded, without spending M2 outside domain. Same seed across scenarios permits paired judgments, not independent samples.

Real LLM uses existing Messages interface, default configured model/environment, maximum4 decisions ×45s and1500 output tokens per request, no automatic retry. Missing/failed service is REAL_LLM_NOT_EXECUTED for allocation, with real failed request count/time retained; no mock substituted. Existing prompt limits independent numerical design, so solver acceptance must be called tool-assisted and its limitation reported.

Phase A: all five scenes × (analytical + three random seeds + real LLM) finish first-shot before Phase B. One complete M2 per arm at most. S4 runs independent existing propagation first for every arm; structured M1-assumption infeasibility skips policy, LLM and M2.

Phase B: only a reliable certified hard FAIL justifies existing deterministic repair. Save bound real feedback, candidate changes and lineage, then run up to two additional complete M2 verifications per arm. Total maximum3 per arm. No new LLM repair; UNKNOWN-only feedback stops. No-change repair is recorded without redundant M2.

Every candidate uses identical domain/M1/M2/metric-level evaluation. Complete TB retains cold capture at0.15V/160µs separately from four warm small-signal BW sweeps/refinements. Independent M2 bandwidth intervals judge current scene. Measured subset is explicitly **{BW_Hz}**; strict periodic PM and1µHz frequency accuracy remain UNKNOWN. Any certified hard FAIL dominates UNKNOWN. No complete PASS from current capabilities.

After both phases, unchanged Stage4 six-variant frequency suites and Stage4.1 steps are applied to **analytical S0 and S3 only**, maximum800 native calls in total. Other candidates explicitly report no new local PM/UGF measurement; historical domain evidence remains referenced separately. This selection is frozen before outcomes. No thresholds/scenarios are changed to improve results.

All outputs refuse existing destinations. Record whole process wall time, solver/cheap/M1/M2/LLM calls, native runs, failures, tokens and unavailable monetary pricing separately. Report exploratory finite evidence, including failure/UNKNOWN and validity rejection; do not claim population/statistical superiority. Stop after Stage5, pending technical Leader review.
