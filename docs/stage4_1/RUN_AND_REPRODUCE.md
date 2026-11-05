# Source checkout reproduction and interfaces

Windows x64/MSVC2022 Community、Python3.12.10，NumPy/SciPy/pytest；matplotlib用于图。精简包是源码快照，不是wheel；原pyproject二进制资源合同未扩展。跨平台未验收。所有输出/构建目录必须不存在，工具拒绝覆盖。命令从项目根执行。

```powershell
& .\pll_allocation\verification\build_kernel.cmd
& .\pll_allocation\verification\build_return_ratio.cmd
& .\pll_allocation\verification\build_closed_loop.cmd
python -m pytest -q tests -p no:cacheprovider
python tools/run_stage41.py --mode anchors --out experiments/stage4_1/new_anchors
python tools/run_stage41.py --mode development --anchors experiments/stage4_1/new_anchors --out experiments/stage4_1/new_development
python tools/collect_stage41_frequency.py --development experiments/stage4_1/new_development --out experiments/stage4_1/new_frequency_checks
python tools/reanalyze_stage41_steps.py --development experiments/stage4_1/new_development --out experiments/stage4_1/new_analysis
python tools/summarize_stage41.py --anchors experiments/stage4_1/new_anchors --development experiments/stage4_1/new_development --refinements experiments/stage4_1/new_frequency_checks --analysis experiments/stage4_1/new_analysis --out experiments/stage4_1/new_development_summary --freeze experiments/stage4_1/new_holdout_lock.json
# 仅在固定开发结果/源码/协议审查后执行；不能据holdout调本轮方法。
python tools/run_stage41.py --mode holdout --lock experiments/stage4_1/new_holdout_lock.json --out experiments/stage4_1/new_holdout
python tools/summarize_stage41.py --anchors experiments/stage4_1/new_anchors --development experiments/stage4_1/new_development --refinements experiments/stage4_1/new_frequency_checks --analysis experiments/stage4_1/new_analysis --holdout experiments/stage4_1/new_holdout --out experiments/stage4_1/new_summary
python -m pll_allocation pipeline --strategy analytical --out experiments/stage4_1/new_pipeline
```

最终版本development直接跑完整六扫频；`collect`只转换已执行六扫回执，M2调用0。`refine`保留用于原开发series/clamp二扫历史补四扫，不能对新六扫重复调用。两种流程成本分别记录。历史原始命令在verifier_*receipt；不将新复现误称本轮新首次或独立holdout。

接口：`closed_loop_native.simulate_step(full_SI_envelope, **settings)`返回18列实际trace、reference/divider edges、事件表、实际dt、源/DLL SHA。`closed_loop.analyze(parameters, run, zero, protocol)`返回独立M2指标、M1事后指标、误差和统一周期曲线；无效工作点返回UNKNOWN且无动态数值。`compare_refinements`不合成PM认证。`summarize_stage41`产生研究合同及CSV，不接管Runner判决；Registry仍只读。

实际权威结果final_summary_01；开发时域analysis_02；holdout时域holdout_01/*/steps；raw请求/NPZ/source/DLL摘要另存，raw路径/字节/SHA在execution_audit/raw_and_artifact_hashes.json。C02读取既有真实Agent Proposal，本阶段LLM0，不能把复验称为新Agent调用。精简包包含完整SI、测试、方法、结果及SHA，不含原始波形/编译件/缓存/密钥。图表采用英文，PDF/SVG矢量+300dpi PNG审查预览。
