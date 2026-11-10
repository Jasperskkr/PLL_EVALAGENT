# Independent M2 noise validation — protocol 1.0

**Physical source/statistical measurement gates pass in the tested domain; original protocol 1.0 inference remains partially UNKNOWN.** Four sources resolve conditionally; VCO and all-source bundles retain UNKNOWN because the original deterministic one-microsecond frequency hold gate fails under stationary VCO frequency noise. This report does not replace those verdicts with PASS. No new allocation is certified by this experiment.

## Frozen run and evidence

Native v3, generated source and complete adapter/build identity were bound before execution. Five independent seeds [11,23,47,71,101], two steps [0.4,0.2] ns, 200 us deterministic warmup and 4 ms noisy observation, 20 ns recording, 10 kHz–1 MHz integration, periodic Hann 16384-point Welch with 50% overlap and mean detrending were preserved. No slope removal or spur deletion. Each bundle includes two matched noise-off runs and ten noisy runs. Reference reconstruction has the declared sinc^4 spectrum limitation. Continuous effective CP and gated UP/DOWN are separate physical models.

## Results

| Source | M2 jitter ps | Conservative 95%/dt interval ps | dt variance difference | M2/M1 jitter | Original v1 verdict |
|---|---:|---|---:|---:|---|
| reference | 2.765527 | [2.728594, 2.828690] | 1.6573% | 1.013970 | STATISTICALLY_RESOLVED_CONDITIONAL |
| vco | 63.324609 | [62.498595, 64.239630] | 0.6272% | 1.004573 | UNKNOWN |
| cp | 0.518104 | [0.506931, 0.525441] | 0.9063% | 0.998166 | STATISTICALLY_RESOLVED_CONDITIONAL |
| resistor | 1.141910 | [1.122204, 1.161282] | 0.0602% | 1.000331 | STATISTICALLY_RESOLVED_CONDITIONAL |
| all | 63.373781 | [62.499149, 64.283301] | 0.5860% | 1.004215 | UNKNOWN |
| gated_cp | 0.104324 | [0.101465, 0.105908] | 2.6544% | UNSUPPORTED: no duty equivalence | STATISTICALLY_RESOLVED_CONDITIONAL |

No limit was passed to the source harness, so these are measurements and model-validation evidence, not jitter-constraint PASS labels. Gated CP absolute M1 comparison is explicitly UNSUPPORTED_UNCALIBRATED_DUTY_EQUIVALENCE. Statistical intervals use Student-t across five independent seed integrated variances and a conservative union over dt. Overlapping PSD segments are not independent Monte Carlo samples; intervals are approximate and conditional on the declared stationary processes.

## Independent checks

- `phaseC_sources_01`: all 7 native/source/statistics tests passed in 3.37 s. Separate source statistics show declared/observed variances within 0.4%, exact dt scaling [2,0.5,2,2], cross-source correlation below 0.00489, free VCO PSD slope −1.98256 and coefficient ratio 1.00679. Standalone process generation is recorded separately from PLL native calls.
- `noise_independent_01/reprocess.py`: independent direct NumPy DFT/periodogram reconstruction from all 60 saved raw trajectories, with an explicit periodic Hann and manual one-sided scaling, reproduces stored PSDs and phase variances within 5e-12 relative tolerance. An independent t4 95% interval calculation reproduces each stored dt-union jitter interval. This reanalysis costs zero native calls and is not a new sample.
- `vco_lock_diagnosis_01`: all 40,000 one-us blocks over ten VCO trajectories were checked. Only the original 100 ppm block-frequency bound fails (857–908 of 4000 blocks per run); all phase/control/clamp/slip checks pass. Whole-observation average frequency error ranges −1.035 to +1.271 Hz; half-window means −5.594 to +4.851 Hz. Phase peak ≤1.119 degrees, full control range ≤2.295 mV, no observed slips or clamps.
- Independent continuous-loop spectral integration predicts one-us mean-frequency standard deviation 6457.956 Hz from the declared white Snu=100 Hz²/Hz, versus observed 6449.7–6662.1 Hz. The original 100 ppm limit is 8000 Hz, about 1.24 sigma. This explains frequent finite block-bound failures without making a new acceptance claim. A new stochastic tracking definition must be separately frozen and audited.
- `terminal_equivalence_02`: ten saved reference trajectories give exact equality of eight original terminal fields and all final ten capture blocks when scanning the last 160 us with absolute timestamps. Earliest capture time is intentionally different and must never be inferred from that suffix. No source or protocol changed in this comparison.

## Cost and preserved failures

Full six-bundle experiment: 72 native completed, 0 native failures, 60.997624 native seconds, 1134000072 integration points. Process wall time 1262.452491 s, dominated by repeated original capture block scans and persistence. No LLM calls.

The run process returned 0. Its conservative source-manifest wrapper returned 1 because four new, unloaded files were added during execution. All 177 pre-existing manifest entries were unchanged, including every executed source and frozen JSON. `noise_sources_execution_01/source_scope_review.json` explains the additions without overwriting the original receipt.

Protocol-1.1 helper development is separate and was not imported by this run. Independent malformed probes found a short/inverted-trace acceptance gap and then a last-record large-gap acceptance gap. Both failed versions remain under phaseC_tracking_01/_02; author fixes passed 13 tests plus three independent malformed probes under _03. A verifier-only terminal comparison first failed JSON serialization of numpy.bool_ after a successful numerical assertion; failure evidence is retained under terminal_equivalence_01 and a new _02 carries the correction. These are zero-native data/test costs, not hidden simulations.

## Actual command and boundary

```powershell
$env:PLL_STAGE6C_BUILD_DIR = "<workspace>/pll_allocation/verification/build_stage6c_v3"
python -B tools/run_stage6c_noise_validation.py --out experiments/stage6c/noise_sources_01 --gated
```

Use fresh output directories for reruns. Exact commands, source SHA, raw traces, PSD observations, per-seed measurements, native journals and final summaries are retained. Source simulation validity, stochastic tracking, capture, BW and strict periodic PM are distinct claims. Strict periodic PM and full original SystemSpec certification remain UNKNOWN/false.
