# Stage 6C delivery acceptance

## Source and historical protection

`experiments/stage6c/protection_final_01/receipt.json`: 170 original Stage6B source entries, 165 unchanged; exactly five explicitly optional changes: pipeline.py, pipeline_contracts.py, allocation/multispec_constraints.py, allocation/multispec_search.py, verification/experiments.py. The original ideal model/registry/contracts/allocate/kernel/simulator/measure/verify/protocol remain byte-exact. New modules are listed with SHA in current_manifest.json; stage6c_change_list.json and stage6c_source_only.patch compare directly with the read-only original Stage6B directory. git_tracked_diff.patch is also included, but contains inherited changes because HEAD predates Stage5/6A/6B. Do not attribute its entire diff to this stage.

`original_workspace_protection.json`: all170 original source hashes still match, original Stage6B HEAD and Git status unchanged. This scope is source/status protection, not a new full rehash of all historical raw files. No reset/clean/stash/commit/master merge was performed.

## E0 actual regression

Current unique CLI, extension off, six original B1/B2 A/B/C arms, fresh shared cache: **PASS**. Original frozen plan was not edited or bypassed to claim source identity; a separately declared regression plan binds current sources to the unmodified old problems.

All parameter candidates/order, M1/M2 scientific values, numerical envelopes, judgments and cost counts exactly match historical Stage6B. 130 selected numeric checks are reported by this specific comparator; this is distinct from the older archive's156 checks. Actual regression cost:13 slots/10 new complete M2/3 cache/1060 native,26.944964398 native elapsed seconds. Source unchanged during all six runs. This is reproducibility cost, not new optimization samples. See legacy_regression_execution_01/{receipt,comparison}.json; full new raw tree is included in the bundle as extra/legacy/.

Stage6A: independently verified all8 historical candidates using current M1/contract, original57 artifact hashes anchored by DELIVERY_SHA256 and FINAL_RECEIPT, plus18 current fixture files byte-exact. Seven historical research feasible/one BW FAIL remain; strict PM remains UNKNOWN. Cost8 new M1, **zero new M2/native**. No claim to have freshly simulated Stage6A's full8 points. Self-contained selected evidence and provenance were copied into stage6a_evidence_audit_01; original full historical raw remains at its read-only origin.

## Execution, traces and archive

The six-arm formal study, noise/nonideal experiments, final478test gate and source-scope audit are documented in FINAL_RESEARCH_REPORT.md. Real native calls/seeds/failures remain in their saved event journals. Packaging excludes DLL/obj/lib/pyc, .git, pytest tmp and historical ZIP recursion; it includes source, profiles, tests, tools, reports, all Stage6C saved experiment raw, selected historical fixtures, the full formal study, CLI smoke and fresh legacy regression trees.

`artifact_trace.jsonl` is an evidence-derived hash chain with embedded actual event records, file SHA and in-archive paths. Its outer order uses artifact retrieval metadata; original payload timestamps/costs are retained. It does not pretend to be a complete transcript of unrecorded interactive calls. Original failures/UNKNOWN and the independent protocol revision remain visible.

Archive acceptance is performed on an immutable candidate followed by a final package. Exact accepted artifact/hash, full-entry CRC/SHA, evidence/trace links and independent clean-build/run results will be recorded in appended acceptance evidence. A ZIP cannot contain its own final SHA or its own subsequent acceptance receipt; those remain adjacent signed-by-hash receipts, not fabricated internal attestations.

Current status at this document revision: source protection, formal study, E0 and Stage6A historical audit complete; archive export/independent fresh extraction **pending**. This wording must not be read as a claimed successful rebuild. Final appended section will supersede this pending status once actually observed.
