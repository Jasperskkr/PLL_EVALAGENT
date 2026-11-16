# Core allocation pipeline (2026-11-16)

This guide describes the maintained source path. The GitHub core sync includes code,
contracts, configuration templates and regression tests; GUI files and new experiment
outputs are intentionally excluded. Older experiment files already in Git history are
not rewritten by this source publication.

## Environment and official entry

Run commands from the repository root on Windows x64 with Python 3.12 and MSVC 2022
Community C++17. Install the existing numerical and test extras:

```powershell
python -m pip install -e ".[integration,test]"
python -m pll_allocation pipeline --help
```

The official entry remains `python -m pll_allocation pipeline`. Optional study modes
are adapters behind this entry, not alternative production pipelines. Paths below
are relative to the repository root. Each output directory and its sibling
`<name>_calibration` must be new; no command may overwrite prior evidence.

## Deterministic inverse allocation and M1

```powershell
python -m pll_allocation pipeline --initial-allocation-problem configs/stage7/continuous_global_v2.json --initial-allocation-config configs/initial_allocation/deterministic.json --out experiments/core_deterministic_01
```

`ResearchProblemV2` contains enabled SystemSpec constraints, six continuous SI
Min/Max axes, fixed topology parameters and exploration settings. The example is
an ideal Integer-N CPPLL, 10 MHz reference, N=8, 80 MHz output, 0..1.2 V rails.
It is a behavioral allocation problem, not a transistor sizing certificate.

`agent/initial_allocation.py` coordinates calibration, physical-region construction,
formal M1 evaluation, bounded local optimization, candidate archival and a final
independent recheck. Both deterministic and LLM policies use this same controller.
`exploration/physics_region_builder.py` calls the existing
`allocation/physics.py:inverse_at_shape` over the original user domain, checks the
joint gain/tuning intersection, and constructs local boxes around legal seeds.
Constructed seeds and boxes are unverified until the formal M1 executor evaluates
them. `region_explorer/` owns the existing Sobol/SLSQP actions, evaluation accounting,
finite differences, domain checks and observations. No new physical solver is
introduced by the Agent layer.

M1 predicts ideal continuous BW, nominal continuous PM and the tuning point. It
does not predict reliable capture time or certify a whole six-dimensional region.
The example intentionally also declares pending M2 lock time and unsupported jitter;
M1 feasibility must not be reported as full SystemSpec certification.

Inspect `result.json`, `m1_allocation.json`, `candidate_archive.jsonl`,
`SEARCH_DECISION_TRACE.jsonl`, `REGION_CONSTRUCTION_RESULTS.json` and
`stage9_handoff.json`. A handoff is usable only when `ready_for_stage9` is true.
The saved calibration/context and referenced evidence must remain available.

## Real LLM decisions

```powershell
python -m pll_allocation pipeline --initial-allocation-problem configs/stage7/continuous_global_v2.json --initial-allocation-config configs/initial_allocation/physics_tool.json --llm-config configs/stage8b/messages_pilot.json --out experiments/core_llm_01
```

Set `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_MODEL` in the local
process environment. Configuration JSON stores their names only. Use the provider's
Messages-compatible HTTPS endpoint and authentication mode. Do not commit secrets.
The existing `configs/llm_env.json` has a 60 s timeout; the explicit Messages pilot
template uses 180 s. Neither template guarantees provider availability.

`agent/physics_tool_policy.py` supplies physical strategy prompts and validates
versioned decisions. `region_policy.py` and `llm_transport.py` perform real API calls.
The LLM chooses construction strategy, target BW fraction, tuning preference,
region/tool action and budget; it does not replace the inverse solver, M1 or M2.
`search_loop.py`, `decision_adapter.py`, `planner_state.py` and `run_state.py` keep
evidence references, validation, retry/stopping state and budget decisions explicit.

Accepted actions, rejected proposals, provider metadata and observations are saved
under each run. Check actual call metadata (`real_network_call`) and the reported
LLM call count to distinguish a real request from deterministic/TEST/replay output.
A provider timeout remains `LLM_PROVIDER_FAILED`; it is not proof of infeasibility
and is not silently relabeled as a successful LLM decision. Shared controllers
retain some legacy labels: a deterministic STOP can say `STOPPED_BY_LLM`, and
Stage9's uninjected mode label can say `REAL_M2_REAL_LLM` even with zero LLM budget.
Use the explicit policy, `LLM_calls` and per-call network metadata to establish
whether an LLM actually ran; those labels alone do not establish a network call.

## Handoff, native M2 and feedback

Build native M2 from the committed sources before M2 execution. This script refuses
an existing destination and binds source/DLL hashes in `identity.json`:

```powershell
cmd /c pll_allocation\verification\build_kernel.cmd
```

`build_kernel.cmd` currently locates MSVC at its standard VS 2022 Community path.
The native DLL, build directory and generated identity are local artifacts; they
are not published as source. Do not substitute simulated results for a failed build.

Verify the deterministic run once, with feedback disabled and no LLM requests:

```powershell
python -m pll_allocation pipeline --stage9-handoff experiments/core_deterministic_01/stage9_handoff.json --stage9-problem configs/stage7/continuous_global_v2.json --stage9-config configs/stage9/verify_only.json --out experiments/core_m2_01
```

Use real LLM feedback after a valid handoff when the provider is available:

```powershell
python -m pll_allocation pipeline --stage9-handoff experiments/core_llm_01/stage9_handoff.json --stage9-problem configs/stage7/continuous_global_v2.json --stage9-config configs/stage9/feedback.json --llm-config configs/stage8b/messages_pilot.json --out experiments/core_feedback_01
```

`agent/handoff.py` checks current Spec/domain, candidate/model fingerprints and the
independent formal M1 recheck. `verification/research.py` adapts the validated
continuous candidate to the existing native TB and measurement functions without
changing the frozen proposal gate, physical equations or measurement algorithms.
It binds the protocol and native build and enforces a subprocess deadline.
`agent/stage9.py` schedules real M2, supplies provenance-bound feedback to the
existing physics-tool loop, selects a distinct legal candidate when available,
rechecks it with M1 and reverifies with M2 within separate hard budgets. It also
supports an explicitly justified repeat after UNKNOWN/execution failure.

M2 independently measures BW and conditional capture time (initial control 0.15 V,
160 us capture window). M2 PM and jitter are unsupported. A numerical envelope
crossing a limit or an inconclusive capture remains UNKNOWN. M1 PASS cannot
overwrite M2 FAIL. `supported_M2_status` is distinct from full `M2_status` and
`FULL_SYSTEMSPEC_CERTIFIED` remains false. The default example's unsupported jitter
prevents complete certification even when supported metrics pass.

Read `stage9_final_result.json`, `m2_verifications.jsonl`, `feedback_summaries.jsonl`,
`agent_decisions.jsonl`, `reallocation_candidates.jsonl` and
`stage9_cost_summary.json`. Real feedback capability in source is separate from
evidence that a particular run completed a real API FAIL-to-new-candidate-to-M2
cycle. TEST injection and replay are explicitly labeled and are not real LLM evidence.

## Source map and regression boundaries

| Area | Maintained paths |
|---|---|
| Contracts and Agent configuration | `configs/`, `exploration/contracts.py`, `block_space/`, `agent/subregion_contracts.py` |
| Inverse and physical prior | `allocation/physics.py`, `exploration/physics_region_builder.py`, `agent/subregion_prior.py` |
| M1 | `physics_mapping/`, `exploration/`, `region_explorer/assessment.py` |
| Decisions and bounded execution | `agent/`, `region_explorer/`, `llm_transport.py` |
| M2, native TB, protocol and verdicts | `verification/`, `configs/verification/` |
| Official CLI and legacy compatibility | `pipeline.py`, `cli.py`, `__main__.py` |

Run the portable core tests (no live LLM request; native M2 build required for
Stage9 request-identity tests):

```powershell
python -m pytest tests/test_initial_allocation_physics_tool.py tests/test_stage7_5_subregions.py tests/test_stage8a_region_explorer.py tests/test_stage8b_llm_region.py tests/test_stage9_feedback.py tests/test_initial_allocation_a_plus.py -q
python -m pytest tests/test_stage8b_final_hardening.py tests/test_stage8b_stabilization.py -q -k "not historical"
```

Optional A+, multi-region, allocation-ablation, stress and report adapters are
retained as source. Historical replay tests/studies may require locally retained
archives under `experiments/` or `docs/.../evidence`; those archives are not runtime
dependencies of initial allocation/Handoff/Stage9 and are not part of this sync.
In particular, `test_window_contract_fix.py`, `test_multi_region_planning.py`,
`test_spec_allocation_ablation.py`, the named historical tests above and the old
Stage4.2 readiness scan are archive-dependent. Missing archives must be reported,
not reconstructed into fake verification evidence. Older phase reports remain
historical records; this guide describes the newly published core path.
