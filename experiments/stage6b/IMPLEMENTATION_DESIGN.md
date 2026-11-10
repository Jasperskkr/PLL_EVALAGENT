# Stage 6B Implementation Design — before development experiments

Date: 2026-11-09 Asia/Shanghai. Original task is copied to docs/stage6b/TASK_REQUEST.md after snapshot verification. No real LLM API, BO/TuRBO, new PLL model, measurement protocol change, or master merge.

## Reuse and isolation

Research branch codex/stage6b-sensitivity-allocation starts at master cd70cf4 plus an exact copy of current Stage5/6A uncommitted source/evidence. The source Stage6A checkout remains read-only. All nonignored files and all Stage6A delivered raw evidence are copied and SHA256 verified. Missing tracked archives remain missing. No user changes are committed/stashed/discarded. Original hashes/status and precise dependencies are recorded in safety_01. Three native DLLs are rebuilt in the new checkout.

Reuse original BlockSpace contracts, physics_mapping Registry/evaluate, allocation analytical/sensitivity/optimize/repair, verification.verify and protocol1.1. Preserve their source bytes. Add allocation/multispec_constraints.py for evidence-aware constraint evaluation and allocation/multispec_search.py for pure deterministic proposal logic. Extend the existing pipeline.py with an explicit --multispec problem --method A|B|C route. It owns candidate selection, persistence, all-constraint rechecks, caching, budgets and full-M2 dispatch by reusing its existing run_pipeline function; no second entry or verifier.

## Constraint and objective

Problem JSON binds frozen assets and declares BW/PM/tuning/conditional capture, measurement sources/protocols, budgets and secondary objective. B1:150–300kHz/PM50/interior tuning/40us, then minimize conservative capture-time envelope. B2:290–300kHz/PM70/interior tuning/40us, then maximize minimum normalized research margin and capture as a tie-breaker. All methods share the same problem and maximal6 complete M2 candidate slots, including cache accesses; M1/cheap budgets equal. A/B stop after one candidate by definition, do not receive extra search to exhaust budget.

Unified rows include metric name, comparator/bounds, source, protocol, validity, predicted/measured value or interval, normalized violation, margin and PASS/FAIL/UNKNOWN/UNSUPPORTED. BW uses unchanged M2 envelope; PM uses M1 only; tuning strict interior; capture uses original paired convergence, terminal capture and hull of coarse/fine times enlarged by1us. No weighted cancellation: feasibility/unresolved evidence precedes all secondary objectives. Full original SystemSpec certification remains unavailable; known formal FAIL is retained.

## Candidate generation and actual sensitivity use

A uses unchanged analytical first candidate. B and C compute analytical-center sensitivities and pass them into the existing SLSQP solver, whose guards use the actual log derivatives. Keep a separate diverse pool from all eligible capacitor pairs using original inverse_at_shape, strict gain/current/R/tuning checks and full M1. Pool contains gain splits and operating points, rather than only a maximum-PM winner. All pool evaluations count toward M1 budget; invalid trials are retained.

C begins with B. Each M2 result affects the next proposal. Pattern coordinates are log gain product, log R, log Kvco (with Icp reconstructed), Vreq (with f0 reconstructed); actual C1/C2 choices are enumerated. Sensitivity columns identify equivalent gain directions, derivative degeneracy and constraint side effects. Use deterministic symmetric operating-point polls for capture and gain/R polls for measured BW violations; choose a M1-feasible predicted-error-correcting poll by estimated constraint residual. This is a small pattern/trust-radius method, not the old fixed BW scaling repair. Resolution/overlapping envelopes never become exact gradients. Poll outcomes affect incumbent, direction order, trust-radius contraction and discrete-region switch. All complete candidates are independently checked by original full M1 and all research constraints after every change.

## Evaluation and trace

The runner owns all final decisions. Persist first candidate before TB; each complete M2 contains original cold capture plus four BW sweeps/refinements. Shared cache keys bind candidate, model, kernel, protocol and measurement settings; cache hits cost zero new M2 but consume a candidate slot and reference immutable evidence. Cross-method identical first candidates may reuse new-stage evidence; never label cache as new simulation. No Stage6A outcomes enter formal search cache or candidate rules. Existing Stage6A boundary failure is regression/debug evidence only, not a chosen formal first candidate.

Append hash-chained JSONL trace during execution for problem/source load, M1 calls, pool and sensitivity, candidate proposals/rejections, cache hit/miss, M2 begin/end, feedback, incumbent changes, budget/stop and final verdict. Link original native request/summary/measurement and pipeline trace by relative paths and SHA256. Provide a consolidated end-to-end trace index for audit, tests, study, failures and packaging; preserve event provenance when aggregating recorded historical events.

## Freeze, tests and delivery

Before formal B1/B2: write versioned problem configs, method order A/B/C, deterministic polling order/steps,6 slots, M1/cheap caps, objectives, source hashes, no-adjustment rule. Tests cover joint decisions, PM fail/BW pass counterexample, unknown/fail capture, domain/rail rejection, discrete switch, measured BW feedback, derivative degeneracy, non-smooth/resolution outcomes, budget/cache and Stage5/6A regression. Verifier runs all historical tests and new tests and complete formal M2s; author does not run simulations. Any development failure remains in a fresh directory.

Deliver architecture/algorithm/results/comparison/Agent-boundaries reports, exact input/config/source/versions, raw results and complete trace. Create one ZIP containing a runnable source tree, all Stage6B result data (including raw), needed historical regression fixtures and README reproduction/inspection commands, SHA256 manifest and archive receipt. Verify ZIP CRC/hash and isolated extraction tests; no credentials/build caches in package, source rebuild instructions included. Original outputs remain untouched. Stop at Stage6B review.
