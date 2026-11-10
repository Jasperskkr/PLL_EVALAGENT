# Stage 6A execution and safety plan

Authorized request: TASK_REQUEST.md, 2026-11-09 Asia/Shanghai. No automatic merge, commit, LLM request, model change, or threshold relaxation.

## Baseline and preservation

Original master is cd70cf445d2ac6789550b7df2da6736221262045. Stage 3A.1 / 4 / 4.2 / 4.1 are ancestors. Stage 5 is **not committed**: its exact working-tree implementation and evidence are part of the research baseline. Four tracked modifications, two existing archive deletions, and all untracked nonignored files were copied to the isolated managed worktree. The original remains untouched. safety_01/baseline_files.json pins 14,709 existing files (478,501,915 bytes); every copy and the original were SHA256 checked. Original status is saved verbatim. Ignored historical waveforms/builds remain at their original location; native code will be rebuilt here. No user edits were stashed, committed, discarded, or moved.

Research branch: codex/stage6a-multispec-feasibility. All Stage 6A additions stay under docs/stage6a, experiments/stage6a, and tests/test_stage6a_joint.py. Only append Stage 6A decisions/status in this isolated checkout. The inherited dirty baseline is distinguished from new edits by the manifest. Formal ownership and the sole run entry `python -m pll_allocation pipeline` remain unchanged.

## Ordered gates

1. Read-only Git/source audit and verified isolated snapshot (completed; safety_01).
2. Capability audit of Registry, existing M1/solvers and full M2/capture protocol; write Spec Capability Matrix before new measurements.
3. Deterministic M1 scan: enumerate all nine capacitor pairs, shape coordinates and original bounds, retain feasible and boundary witnesses. Use existing conditional-domain atlas and inverse functions; no parallel model. Time full M1 and cheap algebra separately. Compare local sensitivities and gain/tuning equivalence.
4. Freeze research scenarios, candidate-selection rules, complete candidates, capture requirements, budget and source identities **before** any Stage 6A candidate M2. E0 uses BW/PM/tuning; choose E1 from actual pre-scan competition. If competition is weak, report that result. E2 uses unchanged Protocol 1.1, initial control .15 V, initial phases/states from the existing kernel, duration 160 us, both .4/.2 ns steps. Research lock deadline will be declared from historical evidence, never selected using new M2 outcomes.
5. Verifier rebuilds native kernels and runs full existing regression plus 4–8 representative candidate validations using the formal CLI. Full validation includes cold capture and all four BW sweeps. All candidates and metadata are persisted before TB. No LLM calls. The study will reuse existing algorithms and explicit existing-proposal reverification; custom research thresholds are assessed separately without changing the frozen SystemSpec.
6. E2, if reliable: compare equivalent M1 dynamics but different operating points/gain splits; attempt the existing deterministic repair on an observed research failure and recheck every included constraint. Preserve a failed/no-change repair. Never call an M1-PM-failing repaired candidate jointly feasible. Stage 5 S3/random-11 is a mandatory historical regression.
7. Independent binding/judgment/cost checks, final original-worktree protection check, reports A–E and reproducible commands. Retain all failures and raw data. No merge to master.

## Measurement and decision rules

M1_PREDICTED_FEASIBLE requires complete legal candidate, valid ideal M1, BW/PM and strict interior tuning. M2_MEASURED_PASS refers only to the named independently supported subset. RESEARCH_JOINT_FEASIBLE combines measured BW (and capture/deadline when enabled) with **predicted** M1 PM and tuning; it is mixed-evidence research feasibility. FULL_SYSTEMSPEC_CERTIFIED remains UNKNOWN unless every original required independent metric is supported and passes. Missing/unsupported/nonconverged evidence cannot become PASS.

Capture deadline judgments use the hull of both measured lock times enlarged by the existing 1 us block resolution; deadline overlap is UNKNOWN. Require same terminal capture status and the original numerical convergence limits. A repeated independent capture pair for one matched candidate checks deterministic repeatability; these two extra native calls are diagnostic cost, not new candidate/full-M2 samples. BW uses the unchanged numerical envelope. Report native time, component wall time and full Pipeline wall time separately.

Initial budget: at most eight new complete candidate M2 calls, plus one repeat capture pair (two native calls; the initial pair is already in full M2). Do not silently grow this budget. Baseline equality is checked using E0 analytical against historical Stage 5, avoiding an extra identical full validation. Tests are accounted separately.
