# PLL Physics Mapping Foundation — Stage 1 交付

2026-11-04（Asia/Shanghai）。Task A–E 已完成本阶段实现和 Python 数值验收，待用户审阅；研究目标仍是行为级规格分配。未运行 MATLAB Runtime、M2 事件 TB 或 LLM。未产生 Verified JointBlockSpec。

## 实现与证据

|任务|完成内容|产物|
|---|---|---|
|A|审查指定 MATLAB 六文件、Python 合同/行为内核及相关依赖；统一 41 个变量/指标语义，记录冲突与公式风险|`VARIABLE_SEMANTICS.md`、`variable_mapping.csv`、`audit/source_manifest.json`|
|B|隔离实现 F_FREQ_PLAN / F_TUNING / F_KPFD / F_LF_TF / F_LOOP，显式单位、有效域、状态和频域响应|`pll_allocation/physics_mapping/model.py`|
|C|SystemSpec v0 研究草案；Block Space v2 支持 fixed/range/choices、单位、Block、角色、来源和 validity|`configs/physics_mapping_stage1_v2.json`、`experiment.py`|
|D|默认点及四个扰动点、独立多项式对照、11 个异常案例、参数快照和成本；新增 69 项测试|`outputs/physics_mapping_stage1_20261104_02/`、`tests/test_physics_mapping_stage1.py`|
|E|可执行 M1 和共享 MetricRequest / MetricEvaluator / MappingResult；M0/M2 明确 UNSUPPORTED|`MULTIFIDELITY_INTERFACE.md`|

主运行目录：`outputs/physics_mapping_stage1_20261104_02/`。保留先前冒烟目录 `_01`；没有覆盖任何输出。核心只用 Python 标准库，不新增运行依赖，不修改 pyproject.toml。

## 默认点与误差

|指标|本次 Python M1|历史 Python 参考|误差|门限|
|---|---:|---:|---:|---:|
|Vctrl_required / V|0.4|0.4|0 V|≤1e-6 V|
|UGF / Hz|138176.44113161|138176.4411317168|相对约 7.73e-13|≤0.005|
|BW / Hz|222379.1834929631|222379.18349260243|相对约 1.62e-12|≤0.005|
|PM / deg|56.44269021253223|56.44269021253223|0°|≤0.2°|

历史参考来自实际审查的 MATLAB v3.4 `results/python_crosscheck_results.json`，该文件明确写 `INDEPENDENT_PYTHON_REPRODUCTION_ONLY; MATLAB_RUNTIME_NOT_EXECUTED`。不是本次 MATLAB 实机验证。

## 参数扰动传播

未列出的参数均保持默认理想点。每个点完整参数与参考来源保存在运行目录 `numerical_comparisons.json`，对照方法是本次独立的 ω² 幅度多项式正根求解，非历史 MATLAB 扰动数据。

|变化|Vreq / V|UGF / Hz|BW / Hz|PM / deg|
|---|---:|---:|---:|---:|
|Icp=120 µA|0.4|161504.173103|263205.355734|56.12227020|
|Rz=4500 Ω|0.4|155083.740792|254940.763657|55.41954449|
|Kvco=25 MHz/V|0.32|167216.999974|273227.368744|55.96392022|
|Icp=140 µA，Kvco=20/1.4 MHz/V|0.56|138176.441132|222379.183493|56.44269021|

Icp 或 Kvco 增大，BW/UGF 同步变化；Rz 变化同时影响零极点与三个环路指标。最后一点验证 Icp×Kvco 不变时连续环路响应不变，而 Vreq 改变。全部独立数值对照满足指定误差门限。

## 异常、语义与范围

运行报告保存无锁点、锁点落在电压边界、负 Icp、Kvco 单位错误、CP mismatch/leakage、PFD reset、q0、VCO 曲率、缺失 UGF 交越、缺失 BW 交越共 11 个案例。均得到明确 OUT_OF_DOMAIN / UNSUPPORTED / NUMERICAL_FAILURE，系统 metrics 为空，草案判决 UNKNOWN。单测另外覆盖 LF 负载、非有限值、未知 convention/metric、错误扫描条件、结果参数哈希绑定及输出拒绝覆盖。

默认研究配置 fref=10 MHz、N=8、fout=80 MHz、BW 150–300 kHz、PM≥50°，保留 draft=true。默认点及扰动点得到的是 M1_SPEC_PASS。UGF 只作诊断。配置中的范围是声明的行为实验域，范围内组合仍须检查 tuning；未作晶体管可实现性承诺。

M1 仅理想对称 CP、zero reset/leakage/q0、线性 VCO、无额外 LF 负载；非零非理想条件没有被理想近似替代。MATLAB `valid_locked_linearization` 未检查 leakage 等风险已记录，原 MATLAB 文件未修改。Kvco 使用 Hz/V、f0 使用 0 V 截距、phase 使用 ref-div rad，与 v1 的锚点/相位/q0 语义显式区分。

## 回归与保护

最终完整测试 **162/162 通过**：原有 93 项 + 新增 69 项，其中原有 24 组 MATLAB 参考轨迹测试全部通过。结果见 `tests_final_20261104.xml`。这些轨迹是历史回归，不计为本次 MATLAB 调用。

保护核对 **4835/4835 既有文件未变化**，含全部 MATLAB 工程文件、既有 Python 包/测试、冻结配置、输入、历史输出和原章程。证据为 `audit/protected_before.json` 与 `audit/protected_after.json`。新包、新测试、新配置和新文档不在旧文件集合中。仅追加更新 `docs/DECISIONS.md` 和 `docs/PROJECT_STATUS.md`。

## 实际执行命令

在工作区根目录依次实际执行（相对参数均相对于 `F:/LJP/概伦AI/PLL_allocation`）：

```powershell
python tools/audit_physics_mapping_sources.py --matlab-root 'F:/LJP/概伦AI/PLL_Physics_FactorGraph_MATLAB_v3_4_FULL_Visualization/PLL_Physics_FactorGraph_MATLAB_v3_4_FULL_Visualization/PLL_Physics_FactorGraph_MATLAB_v3_4_FULL' --out docs/physics_mapping_stage1/audit
python -m pll_allocation.physics_mapping --config configs/physics_mapping_stage1_v2.json --out outputs/physics_mapping_stage1_20261104_01
python -m pytest tests/test_physics_mapping_stage1.py -q
python tools/build_physics_variable_mapping.py
python -m pytest -q --junitxml=docs/physics_mapping_stage1/tests_20261104.xml
python -m pll_allocation.physics_mapping --config configs/physics_mapping_stage1_v2.json --out outputs/physics_mapping_stage1_20261104_02
python -m pytest -q --junitxml=docs/physics_mapping_stage1/tests_final_20261104.xml
python tools/audit_physics_mapping_sources.py --verify-before docs/physics_mapping_stage1/audit/protected_before.json --out docs/physics_mapping_stage1/audit/protected_after.json
```

首轮新增测试 62 项、完整测试 155 项；随后补入公共请求边界和单位语义测试，最终新增 69 项、完整 162 项。各阶段记录均保留。复现时为 `--out` 和 JUnit XML 使用新路径；实验入口拒绝覆盖目录。数值入口每次记录 16 次 M1 尝试（含失败）和 5 次独立参考求解，MATLAB/M2/LLM 调用均为零。

## 后续边界

本阶段 A–E 完成；M0/M2 实现和连续模型与事件模型一致性验证留待后续。已有 P3 的真实 LLM 首次分配/修复及公平实验仍未验收，状态不因本次基础模块完成而升级。接入 M2 后，再在同一参数语义下检验采样效应、捕获、限幅及非理想模型；禁止直接把 M1_SPEC_PASS 写成完整行为验收。
