# Stage5 delivery index

Stage5 experiment execution and reporting complete; technical Leader acceptance pending. No Stage5.1/6 work started. Formal source remains master cd70cf4 plus the exact Stage5 working-tree hashes, with no automatic commit or push.

|Required deliverable|Authoritative path|
|---|---|
|Experiment plan|docs/stage5/STAGE5_EXPERIMENT_PLAN.md; experiments/stage5/experiment_plan_frozen.json|
|Scenario contract|docs/stage5/SPEC_SCENARIO_CONTRACT.md|
|Frozen scenarios|experiments/stage5/scenarios/S0.json through S4.json|
|Per-candidate CSV|experiments/stage5/scenario_results.csv, identical to summary_02/scenario_results.csv|
|Candidate/tool/M2/feedback trace|experiments/stage5/candidate_trace.jsonl, identical to summary_02/candidate_trace.jsonl|
|Per-metric requirements/measurement/validity/error/evidence|experiments/stage5/summary_02/metric_evaluations/|
|Strategy and costs|docs/stage5/STRATEGY_COMPARISON_REPORT.md; VALIDATION_AND_COSTS.md; COST_ACCOUNTING.json|
|Research questions and seven answers|docs/stage5/END_TO_END_FEASIBILITY_REPORT.md|
|Tests|tests/test_scenarios_stage5.py; experiments/stage5/interface_tests_01 and final_tests_01,351 passes each|
|Actual-result audit|experiments/stage5/result_audit_02/audit.json,297 checks passed|
|Independent report audit|experiments/stage5/final_report_audit_01/,26 checks passed; three suggested wording clarifications subsequently applied|
|Reuse audit|docs/stage5/MODULE_REUSE_SHA256.json,14 original formal modules/configs unchanged|
|Protection|experiments/stage5/final_protection_01/protection.json,5765 existing tracked files checked|
|Commands/provenance/errors|docs/stage5/RUN_AND_REPRODUCE.md; DEVELOPMENT_AND_PROVENANCE.md; original receipts|
|Final review export|experiments/stage5/delivery_02/stage5_source_review.zip|
|Source SHA manifest and archive identity|experiments/stage5/delivery_02/SOURCE_SHA256.json and package_receipt.json|
|Final external receipt|docs/stage5/FINAL_RECEIPT.json; generated after archive to avoid hash self-reference|

Source export delivery_01 was validated in isolation without DLL/raw/track_b: load original inputs, Registry bindings, ownership and S4 no-simulation preflight passed. It predates only final wording clarifications; delivery_02 is the final archive with updated prose and audit receipts. The export check does not claim full native rebuild, wheel installation or cross-platform acceptance. Final archive CRC and each source SHA are verified independently.

All study failures remain: S2 LLM malformed/truncated response, first local cost aggregation exception after valid S0 measurements, PhaseA inactive local-helper edits detected by verifier, and summary_01 repair seed report error. summary_02 is authoritative. Local S0 was referenced without rerun after bookkeeping failure; simulation costs count it once. Stage5 scope comprises31 study completeM2 calls and3840 study native runs; pre-edit/post-interface Baseline regressions and tests are separate cost categories.
