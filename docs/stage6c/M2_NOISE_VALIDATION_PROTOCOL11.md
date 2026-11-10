# Independent M2 noise validation — protocol 1.1

**Phase C passes within the declared process, parameter, offset-band and observation domain.** All six fresh bundles resolve statistically and all sixty noisy trajectories pass the separately versioned finite-observation tracking definition. This does not certify global stability, strict periodic PM, transistor accuracy, infinite-band jitter, or the complete original SystemSpec. Protocol 1.0 VCO/all UNKNOWN evidence remains unchanged.

## Protocol revision and independent gates

`NOISE_TRACKING_PROTOCOL_REVIEW.md` and the original v1 report explain the revision. The original deterministic cold-capture/pre-noise gate and thresholds remain unchanged. Protocol 1.1 separately requires no observed cycle slips/clamps/rails, the original 5-degree wrapped divided-phase bound and 5-mV per-block control bound, and the original 100-ppm mean frequency bound over each half-observation. One-microsecond frequency results remain explicit diagnostics. This is a finite-observation definition, not an exact tail probability or global stability theorem.

Add an explicit 100 us noise-on settling period following the 200 us deterministic warmup, then retain a full 4 ms PSD observation. Sources, their coefficients, five seeds, paired steps, offset band, Hann/Welch estimation and statistical quality gates are unchanged. Manifest `configs/stage6c/protocol11_01/manifest.json` has 17 entries independently matched; noise_protocol.json SHA256 is `40c012def35caf1b395b8f247127462bf9328358d34d3a67b2d0abb80cab0241`.

Independent adversarial checks found incomplete/reversed traces and then a final large gap could pass the first helper versions. Author fixes now reject all three, and the final tracking guard suite has 13 passing tests. Saved VCO scalar block checks exactly match the batched implementation across ten runs. Fresh combined pretest suite has 59 passes (6.91 s), with source SHA unchanged. All this evidence is preserved under phaseC_tracking_01/_02/_03 and phaseC11_tests_01.

## Fresh complete measurements

| Source | Jitter ps | 95%/dt union ps | dt variance difference | M2/M1 jitter | Tracking |
|---|---:|---|---:|---:|---|
| reference | 2.762615 | [2.723220, 2.796074] | 0.4879% | 1.012902 | 10/10 finite observations |
| vco | 63.637621 | [62.853560, 64.648148] | 0.4836% | 1.009538 | 10/10 finite observations |
| cp | 0.517059 | [0.508003, 0.525959] | 0.2605% | 0.996152 | 10/10 finite observations |
| resistor | 1.143393 | [1.120916, 1.165437] | 0.6881% | 1.001631 | 10/10 finite observations |
| all | 63.707228 | [62.879330, 64.675533] | 0.4638% | 1.009498 | 10/10 finite observations |
| gated_cp | 0.103249 | [0.102716, 0.106054] | 2.2390% | unsupported duty equivalence | 10/10 finite observations |

The source harness receives no jitter limit, so jitter_constraint_status remains UNKNOWN by contract, despite statistically resolved measurements. The predeclared 100 ps allocation constraint must be judged by its own Runner. Gated CP is separately validated and has no absolute M1 comparison without measured duty normalization.

Each source has 12 fresh native calls including two matched noise-off trajectories. Full cost 72 native completed, 0 native failures, 62.180883 native seconds, 1161000072 integration points, 139.418671 s process wall time. New stochastic data are freshly computed, never promoted from saved v1 reanalysis. No LLM calls. Source manifest recorded no changes during the full run.

`noise_independent_02/reprocess.py` reconstructs all 60 raw trajectories with explicit NumPy DFT/periodogram one-sided normalization and independent t4 interval calculations; every stored variance/PSD and interval agrees within 5e-12 relative tolerance. This costs zero additional native calls. Fine-step PSD/M1 median ratios remain close to one for all continuous source models; reference finite reconstruction shaping is retained, and gated CP equivalence is not assumed.

## Actual commands and limits

```powershell
$env:PLL_STAGE6C_BUILD_DIR = "<workspace>/pll_allocation/verification/build_stage6c_v3"
python -B -m pytest -q tests/test_noise_stage6c.py tests/verification/test_stage6c_nonideal.py tests/verification/test_stage6c_noise.py tests/verification/test_stage6c_tracking.py -p no:cacheprovider --basetemp=experiments/stage6c/phaseC11_tests_01/tmp --junitxml=experiments/stage6c/phaseC11_tests_01/tests.xml
python -B tools/run_stage6c_noise_validation.py --out experiments/stage6c/noise_sources_02 --protocol configs/stage6c/protocol11_01/noise_protocol.json --gated
python -B experiments/stage6c/noise_independent_02/reprocess.py reference vco cp resistor all gated_cp
```

Reruns require new output directories. Tests, actual command receipts, complete raw evidence, per-seed results, diagnostic deterministic terminal failures, actual stochastic checks, native events, source/build SHA and cost records remain reviewable. Conditional five-seed CI is approximate, Welch segments are not independent samples, and paired-step union is not a formal error theorem. Strict periodic PM remains UNKNOWN, and FULL_SYSTEMSPEC_CERTIFIED remains false.
