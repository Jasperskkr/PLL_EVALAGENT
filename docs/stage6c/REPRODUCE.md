# Reproduce Stage6C

Windows x64, Python3.12, NumPy/SciPy/pytest, MSVC2022 C++17. Original matching environment versions and exact executedcommands saved in experiments/stage7/pretests_01 and stage6c receipts. No SPICE/PDK/LLM service required. Work from repo root; archives require actualfullsource snapshot, not masterHEAD alone.

Fresh archive has no nativebinaries. Rebuild originalthreebackends and optionalextension into NEW directories. Defaultoriginals build/build_stage4/build_stage4_1_r2; if existing choose cleanexport rather than delete historicalfiles. Optionalbackend selected by explicitenv; originalidentitychecks remain. Examples:

```powershell
cmd /c pll_allocation\verification\build_kernel.cmd
cmd /c pll_allocation\verification\build_return_ratio.cmd
cmd /c pll_allocation\verification\build_closed_loop.cmd
cmd /c pll_allocation\verification\build_stage6c.cmd "$PWD\pll_allocation\verification\build_stage6c_repro_01"
$env:PLL_STAGE6C_BUILD_DIR = "$PWD\pll_allocation\verification\build_stage6c_repro_01"
python -B -m pytest -q tests -p no:cacheprovider --basetemp=experiments/stage6c/repro_tests_01/tmp --junitxml=experiments/stage6c/repro_tests_01/tests.xml
```

Create basetemp parent before pytest if absent. Never overwrite existingoutput. `tools/generate_stage6c_kernel.py` emits source only with exclusivecreation; archivealreadycontainsexactgeneratedsource, andtest independentlyregeneratesinmemory. Nativeidentitybinds source/generator/adapter/binary so anyeditrequiresfreshbuild; do noteditidentityJSONtobypass.

Modelmechanismvalidationtools (notalternateallocationentry): `tools/run_stage6c_nonideal.py --out <new>`; `tools/run_stage6c_noise_validation.py --protocol configs/stage6c/protocol11_01/noise_protocol.json --gated --out <new>`. Eachmustusecompletefrozenprofiles/5seeds/pairedsteps/full4ms; no shortcapturereplacedjitter. Protocol1.0historicalUNKNOWNmustremain. P1/sources/fixtures testsdistinguishedfromphysicalexperiments.

Formaljointallocationusesonlyexistingentry:

```powershell
python -B -m pll_allocation pipeline --multispec configs/stage6c/joint_frozen_01/J0_ideal.json --method A --out <new_J0_A>
python -B -m pll_allocation pipeline --multispec configs/stage6c/joint_frozen_01/J0_ideal.json --method B --out <new_J0_B>
python -B -m pll_allocation pipeline --multispec configs/stage6c/joint_frozen_01/J0_ideal.json --method C --out <new_J0_C>
```

LikewiseforJ1_nonideal. `tools/freeze_stage6c_study.py --out <newplan>` + unchanged `tools/run_stage6b.py --frozen <newplan> --out <newstudy>` generateall6commandswithsharedsource/profile-boundcache. NewplanrequiredafterrebuildbecausebinarySHAchanges; originalplanisimmutableevidenceandshouldrejectdifferentbuild. Cachemustnotbehandeditedorcopiedasnewmeasurements. Cachehitconsumesslot,zeroadditionalnativecalls. `tools/audit_stage6c_study.py --study <newstudy> --out <newaudit>` verifiestracehashchainsandconstraintartifactpaths. Newfreshnoise-rerunstatsmaydifferfromsavedones; assessdeclaredCI/dtcriteria, notpointwiseindependenttrajectories. Fixedseed/samebuildRNGexactrepeatabilitytested.

For archive, savedstudyunderstudy/; historicruntimeabsolute/relativepaths areprovenance, notreplayasfreshcalls. Originalresulttreeshaandtraceallowreview; newrerunsusefreshoutputandfreshcache. Noautomaticmerge/commit. FinalreportdistinguishesImplemented/NumericallyVerified/BehaviorallySupported/Unsupported/FutureWork.

Additional raw trees are stored as `extra/legacy/` (fresh E0 Stage6B regression) and `extra/smoke/` (formal Stage6C CLI smoke). Final delivery may also include `extra/reproduction/` from an independently extracted candidate. These saved trees retain the original absolute paths as provenance. `repo/experiments/stage6c/stage6a_evidence_audit_01` holds all8 historical witnesses and originalmanifest/receipt provenance, not all historical Stage6A raw and not a fresh simulation claim.

Archive creation/validation tools are `tools/package_stage6c.py`, `tools/accept_stage6c_zip.py`. Use `--extra legacy=<existing-directory>` and matching `tools/trace_stage6c.py --extra` bindings when including other completed raw trees. They inspect/copy evidence only and never simulate or replace the formal pipeline. Acceptance receipts for the final ZIP are sidecars because a file cannot contain its own final SHA.
