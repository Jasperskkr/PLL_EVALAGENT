# M2 nonideal validation — independent verifier

Final mechanism gate: **PASS within the declared behavioral model and tested windows**. This does not certify global stability, all initial conditions, strict periodic phase margin, or the original microhertz frequency requirement. No LLM calls were made. Source/config/test changes were made by the author, never the verifier.

## Preserved failures and correction

- `phaseB_01`: fresh MSVC build passed; 12 tests failed and 3 passed. Ten tests reached native computation before Python metadata failed on Windows path separators; two short test windows violated the existing onset bound. Native work incurred before metadata failure is preserved and must not be counted as zero-cost success. The author normalized identity paths and corrected test onset values.
- `phaseB_02`: fresh v2 build and all 15 short mechanism tests passed. `nonideal_01` then exposed a long-window zero-delay reset defect: K2-only output response froze, and mismatch-only charged to a rail. Their BW verdicts remain UNKNOWN. Five profiles completed 498 native calls with no native exceptions; this failed development experiment is preserved in full.
- Review identified normalized reset time rounding below the current event fraction, causing an already due reset to be skipped. The author accepts a due reset at max(current_fraction, reset_fraction), and rejects an expired event older than the declared numerical tolerance. The fix changes scheduling only; PSD/measurement thresholds were not relaxed.
- A proposed v2 diagnostic was rejected before native execution by the source/binary identity guard after the author changed the source. `reset_diagnostic_01/receipt.json` records native_calls=0; the verifier did not bypass the guard.
- `phaseB_03`: fresh `build_stage6c_v3` and all 17 tests passed, including both long-window regressions. Old builds, failed tests, and experiment directories remain intact.

## Independent physics and event checks

`phaseB_03/independent_event_checks.py` independently reconstructs UP/DOWN durations and reset counts using a global priority event queue built from observed reference/divider edges. It does not reuse the kernel fixed-grid subinterval loop. Across nine single/sign/combined mechanisms all reset counts agree exactly; maximum UP/DOWN duration difference is 3.693e-19 s.

Independent vector reconstructions also check each Euler capacitor KCL update, pulse charge including mismatch/compliance/leakage, anchored quadratic VCO frequency, and actual phase increment. Maximum capacitor-update difference is 4.441e-16 V; maximum phase-increment residual is 2.172e-12 rad. Oracle cost: 9 native calls, 675009 integration points, 0.071305 native seconds. These are short deterministic checks, separate from the five full experiments.

## Final complete deterministic measurements

The unchanged response_sweep/fit/quality/refinement and capture protocol are injected with the optional extension backend. Each profile runs coarse/fine capture, base/half-amplitude/half-step/double-window frequency sweeps, and coarse/fine finite-duration phase perturbation recovery. Original fit and convergence gates remain unchanged.

| Profile | Capture fine µs | BW Hz | BW numerical convergence | Finite-window recovery | Native calls |
|---|---:|---:|---|---|---:|
| ideal-1.0 | 33.000 | 226403.934472 | True | PASS_CONDITIONAL_FINITE_WINDOW | 108 |
| K2_plus-1.0 | 33.000 | 247324.899040 | True | PASS_CONDITIONAL_FINITE_WINDOW | 108 |
| mismatch_plus-1.0 | 32.000 | 225848.609143 | True | PASS_CONDITIONAL_FINITE_WINDOW | 108 |
| reset-1.0 | 33.000 | 226403.934472 | True | PASS_CONDITIONAL_FINITE_WINDOW | 108 |
| combined-1.0 | 32.000 | 234431.559082 | True | PASS_CONDITIONAL_FINITE_WINDOW | 108 |

All five final profiles are CAPTURED_WITHIN_WINDOW with paired-step convergence, all BW measurements are MEASURED_BRACKETED with original amplitude/step/window quality convergence, and all tested perturbations recover within the finite observation. Zero/reset BW is exactly the original baseline value; other profiles retain physical changes. Strict periodic PM remains UNKNOWN and FULL_SYSTEMSPEC_CERTIFIED remains false.

Final experiment cost: 540 native completed, 0 native failures, 20.278966 native seconds, 482347381 integration points. Process wall time is 51.683483 s, including measurement and persistence. Test suite work and failed development work are separate costs, not extra independent samples.

## Actual commands and evidence

```powershell
$env:PLL_STAGE6C_BUILD_DIR = "<workspace>/pll_allocation/verification/build_stage6c_v3"
cmd /c pll_allocation\verification\build_stage6c.cmd "<workspace>/pll_allocation/verification/build_stage6c_v3"
python -B -m pytest -q tests/verification/test_stage6c_nonideal.py -p no:cacheprovider --basetemp=experiments/stage6c/phaseB_03/tmp --junitxml=experiments/stage6c/phaseB_03/tests.xml
python -B experiments/stage6c/phaseB_03/independent_event_checks.py
python -B tools/run_stage6c_nonideal.py --out experiments/stage6c/nonideal_02
```

Commands above document actual runs; fresh reruns require new output/build directories. Exact absolute argv, environment, source manifests, JUnit, native requests, trajectories, measurement quality, cost events and results are under `phaseB_01`, `phaseB_02`, `phaseB_03`, `nonideal_execution_01`, `nonideal_execution_02`, `nonideal_01`, `nonideal_02`. Final build/test and final full experiments recorded no source changes during execution.
