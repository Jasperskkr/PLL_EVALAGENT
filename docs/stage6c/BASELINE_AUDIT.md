# Stage 6C baseline audit

2026-11-10. Supersedes the truncated Stage 7 request with the complete user-supplied Stage 6C specification. Stage7 worktree/branch name remains an audit identifier; implementation and experiments use stage6c paths. No automatic master merge.

Base HEAD/master cd70cf445d2ac6789550b7df2da6736221262045 does not contain the uncommitted Stage5/6A/6B implementation. Recovered verified ZIP02 manifest (12491 files) and overlaid byte-exact current Stage6B source/config/tests/tools. ZIP03 is missing at its former path; its historical receipt is not new archive verification. See ../stage7/IMPLEMENTATION_DESIGN.md and ../../experiments/stage7/safety_02 for source paths, SHA256, model semantics and receipt. Old checkouts and frozen evidence are read-only.

Reuse: original strict ideal M1, registry, original domain/contracts, Analytical/SLSQP and deterministic pattern-search policy, original fixed-grid/within-step-edge-interpolation Euler kernel, original measurements/protocol 1.1, source/binary build identity and formal pipeline. Nonzero original K2/mismatch remains UNSUPPORTED. No PDK/SPICE dependency. Independent verifier performs baseline builds/tests and all native simulations.

Add versioned external profiles, M1 noise mapping, generated optional kernel extension, independent noise statistics, and opt-in pipeline/constraint adapters. No second maintained PLL state equation or formal pipeline. Preserve frozen sources except explicit opt-in dispatch/constraint extension. All new mechanisms disabled calls original simulate directly.

Risks: sampling/aliasing, reset pulse resolution, stochastic convergence, approximate reference reconstruction, conditional versus strict periodic stability, effective versus gated CP PSD. Profiles are research environments, not characterized circuits. No invented Icp/Kvco-noise scaling. Acceptance gates are sequential A → B → C → D/E/F; unresolved gates retain failures and stop formal claims.
