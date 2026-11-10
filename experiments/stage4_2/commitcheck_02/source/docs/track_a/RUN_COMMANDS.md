# 实际执行命令与复现

工作目录：`F:\LJP\概伦AI\PLL_allocation`；Python为`C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\python.exe`。SciPy1.18.1、pytest9.2.0。输出目录必须不存在；再次复现请改为新的run_id，不覆盖下列记录。

1. 审计实际文件及Git状态，读取PROJECT_CHARTER、PROJECT_STATUS、P0四报告、Stage1/1.5报告和实际API。原目录不是Git仓库：执行`git init`、`git add .`、本地基线提交（acf49b881d3e2d22eed879fbc6eca5a3a9a61ccc），再`git switch -c track-a/physics-guided-allocation`。未修改其他旧仓库。
2. 开发检查：`python -c`导入`analytical/optimize/assess_m1`，打印候选/结果与成本；详见REVIEW_AND_DEVELOPMENT_RECORD。单元测试依次写入`tests_development_01.xml`（25项）、`tests_development_02.xml`（30项），完整回归早期写`tests_full_01.xml`（204项）、`tests_full_03.xml`（212项）。开发记录与正式结果分开。
3. 真实LLM：

```powershell
python -m pll_allocation.track_a run --strategy llm_agent --out outputs/track_a_llm_20261104_01
```

已配置环境变量的值不写日志、不展示密钥。实际模型deepseek-v4-pro，三次请求均HTTP200及结构化决策成功；耗时/usage/请求/响应/候选保留。该次原始记录不重写；当前代码只增强非数值验证和账本。

4. 保护清单：调用`protection_snapshot('.', 'docs/track_a/protected_before.json')`，覆盖5123份原有受保护文件。`reuse_manifest.json`记录8个已审查复用/参考文件的绝对路径与SHA；旧输出完全只读。
5. 正式比较及审查修复后再现：

```powershell
python -m pll_allocation.track_a benchmark --out outputs/track_a_benchmark_20261104_01
python -m pll_allocation.track_a benchmark --out outputs/track_a_benchmark_20261104_02
```

每次先写plan、全部target快照与哈希，再运行六目标×五策略；两轮不是独立统计样本。配置：`configs/track_a/benchmark_plan.json`。首次正式提交前允许解析/M1设计查询，但没有当前目标M2反馈；M1成本逐次记录，正式提交预算1、M2预算0。分配成本与正式独立M1、16角后选诊断分别报告。

6. 七类模拟反馈：

```powershell
python -c "from pll_allocation.track_a.experiments import simulated_repairs; from pll_allocation.track_a.core import load_model; m=load_model('configs/BLOCK_SPACE_MODEL_V1.json'); simulated_repairs(m,m['experiment']['system_spec'],'outputs/track_a_simulated_repair_20261104_01')"
```

source=SIMULATED，无真实M2修复成功率。后续无变化保护由测试单独验收；原实验文件保留。

另实际调用`simulated_agent_repairs(m,m['experiment']['system_spec'],'outputs/track_a_feedback_agent_20261104_01')`，执行七种失败的独立反馈Agent mock工具链、保存结构化日志，不计真实LLM/M2修复成绩。

7. 完整回归与交付核验：

```powershell
python -m pytest -q --junitxml=docs/track_a/tests_final_20261104.xml
python -m pll_allocation.track_a.audit --out docs/track_a/DELIVERY_CHECKS_FINAL.json
python -m pll_allocation.track_a.report
```

最后一条仅从已保存结果生成报告和原字节Proposal副本，不调用新LLM/M1/M2。final Junit包括旧179项及新增物理/优化/Agent/反馈/证据绑定/预算测试。运行时源清单在每个run的source_manifest.json；报告附release_manifest.json记录最后代码版本。

补充独立反馈Agent后再次执行完整回归，保留为`tests_final_20261104_02.xml`；最终报告为`TRACK_A_REPORT_FINAL.md`，机器交付副本在`delivery_final/`、最终源指纹在`release_manifest_final.json`。前一次报告及215项记录保留，不覆盖实验。

8. 实例再次分配（以下为复现示例，交付时不重复执行）：

```powershell
python -m pll_allocation.track_a run --strategy analytical --out outputs/track_a_reproduce_unique_id
python -m pll_allocation.track_a run --strategy sensitivity_optimization --out outputs/track_a_opt_unique_id
```

仅`docs/DECISIONS.md`和`docs/PROJECT_STATUS.md`更新阶段信息；其他旧源码/测试/冻结输入/历史结果保持。并行出现的`track_b/`不修改、不提交。阶段结束不合并两个分支。
