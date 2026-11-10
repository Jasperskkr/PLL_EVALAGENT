# Stage7 实际运行命令与位置

全部命令的工作目录显式为 `F:/LJP/概伦AI/PLL_allocation`。实验和测试临时文件均在F盘。以下输出目录已存在，复现时必须换全新目录；程序拒绝覆盖。

```powershell
Set-Location -LiteralPath 'F:\LJP\概伦AI\PLL_allocation'
$env:TMP = 'F:\LJP\概伦AI\PLL_allocation\experiments\stage7_exploration_development_20261110_01\tmp'
$env:TEMP = $env:TMP
$env:PYTHONDONTWRITEBYTECODE = '1'

python -m pll_allocation pipeline --explore-problem configs/stage7/continuous_global_v2.json --out experiments/stage7_exploration_20261110_03/global
python -m pll_allocation pipeline --explore-problem configs/stage7/continuous_tight_v2.json --out experiments/stage7_exploration_20261110_03/tight
python -m pll_allocation pipeline --explore-problem configs/stage7/pm_infeasible_v2.json --out experiments/stage7_exploration_20261110_03/impossible
python -m pll_allocation pipeline --explore-problem configs/stage7/continuous_global_v2.json --out experiments/stage7_exploration_20261110_03/reproducibility
python -m pll_allocation pipeline --explore-problem configs/stage7/continuous_global_v2.json --out experiments/stage7_exploration_20261110_03/budget_one --seed 0 --exploration-budget 1

python -m pll_allocation pipeline --explore-problem experiments/stage7_exploration_20261110_02/negative_inputs/invalid_input.json --out experiments/stage7_exploration_20261110_03/invalid_input
python -m pll_allocation pipeline --explore-problem experiments/stage7_exploration_20261110_02/negative_inputs/numerical_failure.json --out experiments/stage7_exploration_20261110_03/numerical_failure
python -m pll_allocation pipeline --explore-problem experiments/stage7_exploration_20261110_02/negative_inputs/not_found.json --out experiments/stage7_exploration_20261110_03/not_found

python -m pytest -q --basetemp=experiments/stage7_exploration_development_20261110_01/pytest_full_final --junitxml=experiments/stage7_exploration_development_20261110_01/tests_full_final.xml
```

invalid_input是预期拒绝，退出2，其余7个探索运行退出0；结论以result状态为准。后六个CLI命令由subprocess按上述argv实际顺序执行，stdout/stderr/返回码保存在 `_03/additional_run_commands.json`。global/tight及完整回归直接通过终端执行，相关产物/manifest/XML均保留。Python运行时位于C盘是既有安装，不代表在C盘创建工作区或实验输出。

开发验收 `_01` 执行了global/tight；`_02` 执行相同五个主案例及三负例，分别保存各自版本源指纹，未覆盖成最终结果。正式报告以 `_03` 为准。

复验：用公开 `load_physics_context` 加载7份context；比较global/reproducibility的完整样本bytes和科学摘要；逐项核对基线14,868条tracked指纹、HEAD和原有文档前缀。机器回执在 `FINAL_RECEIPT.json` 指向的F盘审计文件。
