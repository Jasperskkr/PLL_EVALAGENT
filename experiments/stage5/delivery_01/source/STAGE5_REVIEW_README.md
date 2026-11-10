# Stage5 review snapshot

Source checkout export; no DLLs, raw NPZ waveforms, secrets, virtualenvs or caches. HEAD cd70cf4 plus exact Stage5 source hashes; changes are not yet a Git commit. Canonical frozen assets unchanged. Use original configs, not copied old release manifests as new version claims.

On Windows with MSVC2022 x64 and Python NumPy/SciPy/pytest dependencies:

```powershell
.\pll_allocation\verification\build_kernel.cmd
.\pll_allocation\verification\build_return_ratio.cmd
.\pll_allocation\verification\build_closed_loop.cmd
python -B -m pytest -q tests -p no:cacheprovider
python -B -m pll_allocation pipeline --strategy analytical --scenario experiments/stage5/scenarios/S1.json --out experiments/new_stage5_reproduction
```

New outputs must not exist. Saved study files are evidence/replay, not new LLM execution. Existing configured real LLM transport reads environment values at runtime; no credential is included. Full-size raw waveforms stay in the original workspace, and native/wall costs refer to actual source runs. No wheel or cross-platform validation is implied.
