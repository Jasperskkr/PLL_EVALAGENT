# Post-merge independent source regression

Branch `master`, HEAD `cd70cf445d2ac6789550b7df2da6736221262045`, unchanged before and after. Stage5 remains paused. This run checks the consolidated mainline only.

Fresh formal command: `python -B -m pll_allocation pipeline --strategy analytical --out experiments/mainline_consolidation_20261105_01/postmerge_baseline`. Exact interpreter, command, Python/platform/compiler, initial Git status and source hashes are in `before.json`; stdout/stderr and execution costs are retained.

|Metric|Actual result|
|---|---|
|M1 BW|225000.0000001216 Hz|
|M1 UGF|167166.52042501146 Hz|
|M1 PM|72.24720983805331 deg|
|M2 BW|226403.93447205875 Hz, MEASURED_CONVERGED|
|M2 BW envelope|226283.00933770544 to 226503.68228813985 Hz|
|M2 capture|CAPTURED_WITHIN_WINDOW, initial0.15V, duration160us|
|M2 terminal frequency|79999999.99990459 Hz|
|M2 frequency envelope|79999999.98990458 to 80000000.0099046 Hz, empirical floor only|
|Strict frequency precision|UNKNOWN, required_precision_validated=false|
|Strict periodic PM|UNKNOWN, value=null|
|Overall|M2_PARTIAL_PASS; full_behavioral_pass=false|

Candidate, full M1 assessment, and complete semantic M2 result match both the preceding frozen baseline and official analytical regression fixtures exactly. All six comparisons have zero differences. Candidate identity and execution-wall cost metadata are excluded; physical capture durations and measurement settings remain compared. Full comparison is in `comparison.json`.

Baseline cost: M2=1,106 completed native runs,0 failed native attempts,95090315 integration points; native2.9994541998s,pipeline9.5372198000s,subprocess10.4554538000s. Formal M1=1,posthocM1=1,cheap=11,candidate generations=6,real LLM=0.

Post-merge full existing suite: **328 passed in24.04s**, process wall25.2825645s,exit0. Command/logs/JUnit in sibling `postmerge_tests`. These are source-checkout results; no wheel installation validation was performed.

Source/config/test hashes checked: 96; changed=0. No source, model, protocol, test, branch or historical artifact was edited by this verifier.

Full evidence: `before.json`, `comparison.json`, `execution.json`, `final_receipt.json`; test evidence: `../postmerge_tests/tests.xml`, `stdout.log`, `stderr.log`, `execution.json`.
