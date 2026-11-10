# Actual source commands and reproduction

Workspace: F:/LJP/概伦AI/PLL_allocation. Python3.12.10 x64 Windows11; existing NumPy/SciPy/pytest and MSVC2022 builds. Actual precise executable, versions and platform/compiler identities are in each receipt before.json; M1/model/protocol identities in run_manifest/source_manifest. Source version is master cd70cf4 plus exact uncommitted Stage5 adapter hashes. No wheel installation or cross-platform execution is claimed.

The original Stage5 pre-edit Baseline is experiments/stage5/baseline_frozen_01. Postmerge Baseline is experiments/mainline_consolidation_20261105_01/postmerge_baseline. Stage5 post-interface compatibility Baseline is interface_baseline_01. All independently executed; candidates and M1/M2 semantic results compare exactly. Baseline uses formal frozen inputs, not research overlay.

Actual new study commands, from workspace root:

```powershell
python -B -m pytest -q tests -p no:cacheprovider --basetemp=experiments/stage5/interface_tests_01/tmp --junitxml=experiments/stage5/interface_tests_01/tests.xml
python -B -m pll_allocation pipeline --strategy analytical --out experiments/stage5/interface_baseline_01
python -B experiments/stage5/run_stage5.py --phase firstshot --out experiments/stage5/firstshot_01
python -B experiments/stage5/run_stage5.py --phase repair --firstshot experiments/stage5/firstshot_01 --out experiments/stage5/repair_01
python -B experiments/stage5/run_stage5.py --phase local --firstshot experiments/stage5/firstshot_01 --out experiments/stage5/local_01
python -B experiments/stage5/run_stage5.py --phase local --firstshot experiments/stage5/firstshot_01 --resume-local experiments/stage5/local_01 --out experiments/stage5/local_02
python -B -m pytest -q tests -p no:cacheprovider --basetemp=experiments/stage5/final_tests_01/tmp --junitxml=experiments/stage5/final_tests_01/tests.xml
python -B experiments/stage5/collect_stage5.py --firstshot experiments/stage5/firstshot_01 --repair experiments/stage5/repair_01 --local experiments/stage5/local_02 --out experiments/stage5/summary_01
python -B experiments/stage5/audit_stage5.py --firstshot experiments/stage5/firstshot_01 --repair experiments/stage5/repair_01 --out experiments/stage5/result_audit_01
python -B experiments/stage5/collect_stage5.py --firstshot experiments/stage5/firstshot_01 --repair experiments/stage5/repair_01 --local experiments/stage5/local_02 --out experiments/stage5/summary_02
python -B experiments/stage5/audit_stage5.py --firstshot experiments/stage5/firstshot_01 --repair experiments/stage5/repair_01 --summary experiments/stage5/summary_02 --out experiments/stage5/result_audit_02
python -B experiments/stage5/write_reports.py --summary experiments/stage5/summary_02
```

local_01 exits1 only after S0 complete, during cost field aggregation. local_02 explicitly reads finished S0 and runs S3; do not present it as a clean first local run or add S0 cost twice. Traceback/original evidence/helper bookkeeping change are preserved. PhaseA helper-only local-branch edit detected by verifier is documented in DEVELOPMENT_AND_PROVENANCE.md; formal runtime identity remained fixed.

Each first-shot subprocess uses the sole formal interface, e.g.:

```powershell
python -B -m pll_allocation pipeline --strategy analytical --scenario experiments/stage5/scenarios/S1.json --m2-budget 1 --repair-budget 0 --out experiments/stage5/firstshot_01/runs/S1__analytical
python -B -m pll_allocation pipeline --strategy random --scenario experiments/stage5/scenarios/S1.json --seed 11 --m2-budget 1 --repair-budget 0 --out experiments/stage5/firstshot_01/runs/S1__random__11
python -B -m pll_allocation pipeline --strategy llm_agent --scenario experiments/stage5/scenarios/S1.json --m2-budget 1 --repair-budget 0 --out experiments/stage5/firstshot_01/runs/S1__llm_agent
python -B -m pll_allocation pipeline --strategy analytical --scenario experiments/stage5/scenarios/S1.json --feedback-from experiments/stage5/firstshot_01/runs/S1__random__11/attempt_001 --m2-budget 2 --repair-budget 1 --out experiments/stage5/repair_01/runs/S1__random__11
```

All exact actual subprocess arguments/returncodes/stdout/stderr/wall times are saved in firstshot_01/receipts, repair_01/receipts and phase wrapper receipts. RealLLM reads existing configured environment; no credential or HTTP authorization header is exported. Do not substitute replay/mock and label it a fresh network call.

Reproduction must use **new nonexistent output names** and fresh basetemp parents. Never rerun these commands into frozen historical destinations. The helper is an experiment driver; it does not create a second allocation engine or change the formal entry point. Review export contains source, small results and SHA manifests without DLL/NPZ/cache. Build native backends from provided commands before new source-checkout reproduction.
