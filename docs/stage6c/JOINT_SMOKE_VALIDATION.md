# Independent joint integration and smoke validation

Final integration gate: **PASS** for the tested source-bound CLI smoke. Full six-arm research remains a separate experiment and has not been started by this verifier.

## Regression and preserved failures

- joint_tests_01: collection failed before tests/native work due to an unterminated dictionary key in the new search hook. Author fixed it.
- joint_tests_02: 469 passed, 4 failed because changing frozen allocate.py broke original exact-source and registry gates. Four independent malformed jitter probes also found invalid acceptance: negative CI, NaN point estimate, point estimate outside its CI, and an UNKNOWN nested noise bundle.
- Author restored allocate.py exactly and placed the optional margin hook in a controlled generation adapter based on the original solver function. Cache binds the complete extension; invalid jitter is UNKNOWN; source/seed/build consistency is independently checked; all 16 mapping stencil budget charges are reserved before execution. Each constraint now references candidate-local evidence.
- joint_tests_03: 477 passed, one failed because a package-exported allocate function was imported as a module. The author corrected the explicit module import. A concurrent trace-field correction is explicitly recorded as a source change, so this run was not accepted as frozen.
- joint_tests_04: all **478 tests passed in 37.12 s**. All existing source entries remained unchanged; a new unloaded packaging tool was added, and the blanket wrapper marked that addition. The original receipt remains alongside source_scope_review.json explaining the exact scope. No further full regression was run solely for that unrelated addition.
- All four malformed jitter probes now return UNKNOWN. A separate B proposal-only invocation exercised the generated SLSQP hook successfully: 45 cheap calls, 31 controller M1 calls, 20 candidate generations, plus one independently reported full-noise mapping, zero native calls. This is development cost, not a formal method sample.

## Actual formal CLI smoke

```powershell
$env:PLL_STAGE6C_BUILD_DIR = "<workspace>/pll_allocation/verification/build_stage6c_v3"
python -B -m pll_allocation pipeline --multispec configs/stage6c/joint_frozen_01/J0_ideal.json --method A --out F:/LJP/PLL_Stage6C_results/joint_smoke_01
```

The F: destination was checked absent, resolved under the intended fresh results directory, and had 58 GB free. No historical evaluation cache was supplied. Process exit 0 in 45.211288 s; source manifest recorded no change during execution.

The result is RESEARCH_JOINT_FEASIBLE: measured BW 226403.934472 Hz; nominal continuous M1 PM 72.247210 degrees; tuning point 0.6 V; fixed-window capture 33 us with [32,34] us numerical envelope; independent jitter 63.707228 ps with [62.879330,64.675533] ps seed/dt interval; nominal M1 Routh and finite perturbation recovery pass their explicit conditional definitions. Original formal M2 overall remains UNKNOWN; strict periodic PM and microhertz frequency remain unknown; FULL_SYSTEMSPEC_CERTIFIED is false.

Cost: one candidate slot, one fresh full M2, zero cache hits, 120 completed native runs, zero native failures, 290090329 integration points, 18.778888 native seconds. Test, failed development, source-validation, proposal-only, and smoke costs remain separate from the upcoming six-arm method comparison. No LLM calls.

## Independent audit

joint_smoke_execution_01/independent_audit.json verifies all 27 hash-linked trace events, the final trace hash, candidate save event 15 preceding M2 event 16, seven independently re-derived constraint rows exactly, all row evidence paths, 120 raw native summaries and matching integration points/native elapsed cost, candidate/profile/build identities, and the real seed aggregation through check_result. F: cache evidence uses the correct absolute child origin. This audit adds zero native calls and makes no new statistical sample.

Complete command/source/environment/raw/measurement/trace/cost/failure evidence remains under experiments/stage6c/joint_tests_01 through _04, joint_smoke_execution_01, and F:/LJP/PLL_Stage6C_results/joint_smoke_01. No old source/config/test was modified by the verifier.
