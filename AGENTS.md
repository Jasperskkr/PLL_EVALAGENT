# PLLAgent research source

Read README.md, docs/ARCHITECTURE.md, docs/REVIEW_GUIDE.md and PROJECT_CHARTER.md.

- Official execution entry: python -m pll_allocation pipeline. Keep one Policy/Runner boundary.
- Scope: fixed-topology behavioral joint allocation, not transistor sizing or circuit capability certification.
- Reuse the existing inverse, M1/M2, numerical tools, measurement protocols and verdict semantics.
- Policy proposes actions; Runner owns validation, bounds, budgets, real execution and final verdicts.
- Persist full candidates before evaluation. Charge real calls including failures; label replay and TEST injection.
- Unsupported, unmeasured and numerically unresolved metrics remain UNKNOWN. M1 PASS cannot replace M2 PASS.
- New runs use fresh experiments/<run_id>; never overwrite history or publish outputs, GUI, binaries or secrets.
- Use functional module/config names in new code. Preserve compatibility schemas and hash-bound numerical sources.
- Inspect docs/COMPATIBILITY.md before changing old imports, contracts or frozen source bytes.
- Run relevant tests; report skipped archive-dependent tests and actual runtime/platform limits.
- Research claims require real evidence. LLM availability or a successful mock test is not proof of allocation benefit.
- Record scope changes in docs/RELEASE_NOTES.md; retain the original user charter unchanged.
