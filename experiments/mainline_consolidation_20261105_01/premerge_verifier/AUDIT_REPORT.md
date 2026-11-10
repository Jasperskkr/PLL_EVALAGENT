# Pre-target-branch merge independent verification

HEAD: `cd70cf445d2ac6789550b7df2da6736221262045`; branch: `codex/stage4-1-engineering-validation`. Stage5 remains paused.

Formal implementation ownership:

- `physics_mapping.model.M1Evaluator/evaluate`: forward M1 model.
- `allocation.allocate/physics`: analytical inverse, SLSQP, sensitivity and random allocation; `allocation.agent`: real Messages transport and tool decisions.
- `verification.verify`: independent M2 capture/frequency-response measurement and metric judgment; return-ratio and phase-step research extensions remain under verification.
- `pipeline.run_pipeline`: formal runner, binding, persistence, budget and feedback. The unique formal CLI is `python -m pll_allocation pipeline`. `run/suite` and `track_a` are explicitly documented compatibility entrypoints.

All six legacy `track_a` modules are exact module aliases to formal `allocation`; formal-import process succeeds while both legacy `track_a` and `track_b` imports are blocked. Existing AST dependency audit passed, including six byte-identical allocation implementations and no forbidden dependencies.

Existing ownership/import subset: 7 passed. Full existing source suite: 328 passed in 23.88 s; subprocess wall time 25.181 s, exit 0. Exact commands, stdout/stderr and JUnit are retained. Full regression may include its existing M2 test fixtures; this is not a new Stage5 comparison or post-merge baseline.

Protected source/config hashes checked: 81; changed: 0. HEAD unchanged. No core source, frozen input, branch, commit or historical artifact was edited by this verifier.

Post-merge analytical baseline has not run; awaiting target merge and followup authorization.
