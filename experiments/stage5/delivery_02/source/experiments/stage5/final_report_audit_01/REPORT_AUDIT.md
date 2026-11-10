# Final reporting consistency audit

All 26 factual checks passed. No blocking numerical or certification discrepancies found. Audit added0M2/0LLM and ran no tests or simulations.

Confirmed: cap-pair necessary exclusions S0/S2/S3=3/9,S1=6/9,S4=9/9; all31 measured candidates captured within the specified window; all31 strict PM/frequency judgments UNKNOWN;12 repaired BW passes include one M1PM failure. Actual cost/token totals and scoped test exclusions agree with receipts. All successful real LLM submissions equal the corresponding deterministic solver output. Existing high-precision/tool-choice prompt restrictions are explicitly disclosed and must remain, so these experiments cannot establish universal absence of LLM value.

Nonblocking wording clarifications:

- docs/stage5/END_TO_END_FEASIBILITY_REPORT.md — opening conclusion: 本轮四个可行场景: Prefer 四个M1预测可行且M2 BW子集通过的场景, because strict PM/frequency remain UNKNOWN. Later paragraphs already explain this boundary; no numerical error.

- docs/stage5/END_TO_END_FEASIBILITY_REPORT.md — RQ1: S4五arm共避免5次无意义完整TB: Prefer S4五个arm在预检后均未进入M2（实际调用0）; 5 avoided calls is counterfactual budget interpretation, whereas observed fact is five skipped arms and zero M2.

- docs/stage5/DEVELOPMENT_AND_PROVENANCE.md — Current helper is frozen before PhaseB/local: Use helper re-frozen before PhaseB and separately after local cost-schema fix for S3 continuation; current wording can imply one helper hash across both local attempts, although next paragraph correctly discloses the change.

Exact checked report hashes and machine assertions are in audit.json.
