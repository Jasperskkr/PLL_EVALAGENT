# Stage3A 实际执行命令与测试记录

日期：2026-11-04（Asia/Shanghai）。以下均实际执行；推荐运行方式另见ARCHITECTURE_AND_INTERFACE.md。每个实验目录创建一次，未覆盖失败结果。

```powershell
# 修改前基线：247 passed
python -m pytest -q tests track_b/tests -p no:cacheprovider --junitxml=experiments/stage3a_baseline_20261104_01/tests.xml

# 审计方案先落盘，保护清单15245文件，然后提取9份运行资源
python tools/integrate_stage3a.py
python -m pll_allocation.verification.build_identity

# 解析：M1_PASS / M2_PARTIAL_PASS；106原生调用
python -m pll_allocation pipeline --out experiments/stage3a_analytical_20261104_01 --strategy analytical
# 优化：M1_PASS / M2_PARTIAL_PASS；106原生调用
python -m pll_allocation pipeline --out experiments/stage3a_optimization_20261104_01 --strategy sensitivity_optimization
# 真实deepseek-v4-pro：3次真实响应，随后106原生调用
python -m pll_allocation pipeline --out experiments/stage3a_llm_20261104_01 --strategy llm_agent
# 真实M2失败→原确定性修复→完整复验：114+106原生调用
python -m pll_allocation pipeline --out experiments/stage3a_feedback_repair_20261104_01 --strategy random --m2-budget 2 --repair-budget 1

# 集成开发测试：22 passed；随后完整回归269 passed
python -m pytest -q tests/test_pipeline_stage3a.py -p no:cacheprovider --junitxml=experiments/stage3a_tests_20261104_01/tests.xml
python -m pytest -q tests track_b/tests -p no:cacheprovider --junitxml=experiments/stage3a_regression_20261104_01/tests.xml

# 显式既有候选复验；实际用python -c导入run_pipeline，os.chdir(TEMP)后调用，证明不依赖CWD
# 等价项目根命令如下（不重复计第二次执行）：
python -m pll_allocation pipeline --proposal docs/track_a/delivery_final/AllocationProposal.json --out experiments/stage3a_reverify_20261104_01

# 加强结果模型/源绑定与错误成本测试后，首轮命令父目录未创建：226 passed / 47 setup errors
python -m pytest -q tests track_b/tests -p no:cacheprovider --basetemp=experiments/stage3a_regression_final_20261104_01/tmp --junitxml=experiments/stage3a_regression_final_20261104_01/tests.xml
# 保留失败记录，创建全新父目录再跑：273 passed
New-Item -ItemType Directory -Path experiments/stage3a_regression_final_20261104_02
python -m pytest -q tests track_b/tests -p no:cacheprovider --basetemp=experiments/stage3a_regression_final_20261104_02/tmp --junitxml=experiments/stage3a_regression_final_20261104_02/tests.xml
```

273包含原219、原Track B28和新26。新测试包括：同模型/协议/原核一致、混用版本拒绝、候选/源/结果绑定、PM/频率不能伪PASS、部分/失败/未知状态、真实全TB前首次落盘、反馈进入原Agent、异常计费、LLM环境缺失无回退、预算约束、DLL身份错误/不可用、真实验证器缺后端UNKNOWN与失败成本、历史M1完全一致。fixture边界测试和异常注入均没有计入正式真实LLM成绩。

本轮没有重新调用MATLAB、ngspice或任何晶体管仿真。原历史24组MATLAB轨迹在完整回归内读取数值比较，不称新MATLAB执行。未安装新依赖、未构建wheel；当前Python缺setuptools已如实记录。未进行Git提交、合并、清理或历史目录删除。

最终只读证据审计命令：

```powershell
python tools/validate_stage3a.py --out docs/stage3a/audit_final_01
```

该命令复核全部保护文件、复用源SHA、关键数值函数AST、原Proposal M1/M2、真实LLM原响应、每次主实验结果与成本，并索引所有主实验文件（含raw）的SHA。源码在早期实验后追加过结果版本/源绑定和异常成本记录，未变公式/测量；每次run_manifest/source_manifest保留实际当次版本，最终273项回归覆盖最终运行源码。
