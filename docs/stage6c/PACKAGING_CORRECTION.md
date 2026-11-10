# Independent candidate export failure and correction

Candidate01 ZIP SHA256 `cdca18b0b0727837ee35806167198c7225158b72c5fded9f6576e7240174d302`, 5,774,268,407 bytes. Its34,312 manifest entries passed full SHA/CRC, saved trace chains and evidence paths;21,796 trace-to-manifest artifact SHA/bytes matched independently. All four backends built freshly in a new F: extraction. This did **not** establish a usable export.

The complete fresh test run failed:386 passed/92 failed in37.02s. Independent JUnit grouping found missing packaged inputs only: examples/regular80.json84 failures, unsupported_jitter80.json2, tight80.json1, finite_domain80.json2, frozen80.json1, joint84.json1, and experiments/stage4_2/readiness_05/summary.json1. The reproduction harness stopped before the full pipeline experiment; it did not hide or bypass these failures.

Correction is limited to package selection: include the complete examples/ and learn/ directories, the two original Stage4.2 readiness summary/coupling inputs, plus original root Git attribute/ignore files. Models, tests, frozen problems, thresholds and native sources are unchanged. Already-compressed NPZ payloads are now stored inside ZIP without another deflate pass; payload SHA remains unchanged. Candidate02 must be independently extracted/built/tested/run from scratch again.

Original candidate01 and F:/LJP/PLL_Stage6C_results/export_acceptance_01 remain. Small failure evidence is self-contained under experiments/stage6c/zip_export_acceptance_failed_01, with original paths and SHA in ORIGIN_MANIFEST.json. Test count alone and ZIP integrity alone are insufficient evidence of reproducibility. Final observed acceptance will be documented in a new FINAL_DELIVERY_ACCEPTANCE.md, leaving earlier trace-bound document revisions unchanged.
