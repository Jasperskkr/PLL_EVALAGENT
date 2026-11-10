# Stage 1.5 验收与复核入口

2026-11-04（Asia/Shanghai）。P0 必需项已完成；P1 已完成独立数值路径、稀疏事件 TB 接入和初步误差/边界评估，BW/PM 的独立行为误差仍未建立。交付等待技术 Leader 审阅，未启动 Stage 2。

## 六项正式交付

|交付|权威位置|用途|
|---|---|---|
|BLOCK_SPACE_MODEL_V1|`configs/BLOCK_SPACE_MODEL_V1.json`|机器可读行为域，含输入、41项语义、版本/来源、联合约束、逐指标证据|
|EQUATION_MAPPING_REPORT.md|`docs/stage1_5/EQUATION_MAPPING_REPORT.md`|What/How/Domain/Evidence/Limitations；另有机器公式注册表|
|DOMAIN_VALIDATION_REPORT.md|`docs/stage1_5/DOMAIN_VALIDATION_REPORT.md`|范围、134点声明域采样、异常、敏感度、边界、行为不确定性|
|FORWARD_MODEL_VALIDATION.csv|`outputs/block_space_v1_20261104_01/FORWARD_MODEL_VALIDATION.csv`|139行、43列；参数/单位、预测、参考来源、误差、状态、失败原因|
|REFERENCE_BLOCKSPEC.json|`outputs/block_space_v1_20261104_01/REFERENCE_BLOCKSPEC.json`|完整单位参数、M1_VALIDATED、约束裕量、事件摘要、无全M2通过标签|
|BLOCK_SPACE_READINESS_REPORT.md|`docs/stage1_5/BLOCK_SPACE_READINESS_REPORT.md`|WHAT/HOW/EVIDENCE/UNCERTAINTY/READINESS/NEXT；八项问题逐项覆盖|

## 冻结、版本与冲突

Stage 1 `configs/physics_mapping_stage1_v2.json` 原有 `draft=true` 和目标保持。此处“冻结”仅表示为 Stage 1.5 固定实验输入，不能将其升级为全项目最终 SystemSpec。固定 Integer-N CPPLL、10 MHz、N=8、80 MHz；BW150–300kHz、PM≥50°；UGF诊断。旧 v1 的相位/锁定目标与旧 MATLAB 示例 BW100–400kHz、PM45°均未混入。`EXPERIMENT_FREEZE.json` 保留选择理由及来源哈希。

Formula Version=`stage1_m1_1.0.0`；Parameter Domain Version=`stage1_declared_domain_1.0.0`；事件版本由原始 Python 源 SHA 锚定。原有 Stage 1 M0/M2 placeholder 保持不变；本阶段新增的事件适配器是独立交叉验证工具，没有悄悄注册成完整 M2 验收后端。

新模型在扫描后只补充了证据元数据；变量、范围、SystemSpec、公式和版本未变。扫描所用原始模型在 `outputs/block_space_v1_20261104_01/model_snapshot.json`，其哈希与正式模型的对应关系见 `MODEL_FINALIZATION.json`。原始运行结果、输入快照和失败结果均未覆盖。

## 可直接加载的接口

从工作区运行：

```python
from pll_allocation.block_space import load_model, make_candidate, check_parameters, forward

model = load_model('configs/BLOCK_SPACE_MODEL_V1.json')
candidate = make_candidate(model, {'Icp': 120e-6, 'C1': 100e-12})
domain = check_parameters(model, candidate)
result = forward(model, candidate)
```

`make_candidate` 补全固定条件和显式单位，支持连续范围/离散 choices/fixed；`check_parameters` 分开返回 declared_domain、model_validity、联合派生量及原因；`forward` 由固定M1计算和独立规格判决产生 M1_SPEC_PASS / M1_SPEC_FAIL / UNKNOWN。参数或模型状态不明不通过。后续 Allocation Runner 可直接消费该接口；当前旧 v1 Runner 不改 schema、不放宽约束。

核心域/M1只用标准库。事件交叉验证可选依赖 NumPy；本机 NumPy 2.5.3 可用，适配器只从源文件 AST 提取 simulate，不需运行原源文件的 SciPy/图形/写盘入口。无 NumPy 时可用 `--skip-event` 明示未执行；不能伪造行为通过。

## 实际执行与结果

工作目录为 `F:/LJP/概伦AI/PLL_allocation`。按实际执行顺序记录主命令；运行入口和审计输出拒绝覆盖，复现请使用新输出目录和新 XML 路径。

```powershell
python tools/prepare_block_space_v1.py
python -m pll_allocation.block_space --model configs/BLOCK_SPACE_MODEL_V1.json --out outputs/block_space_v1_20261104_01
python tools/build_equation_registry_v1.py
python -m pytest tests/test_block_space_v1.py -q
python tools/diagnose_event_boundary_v1.py
python tools/finalize_block_space_v1.py
python tools/diagnose_event_warmstart_v1.py
python tools/report_block_space_v1.py
python -m pytest -q --junitxml=docs/stage1_5/tests_20261104.xml
python tools/audit_physics_mapping_sources.py --verify-before docs/stage1_5/audit/protected_before.json --out docs/stage1_5/audit/protected_after.json
```

`prepare`、`build_equation_registry`、`finalize`、报告生成及两个诊断脚本用于本次一次性产物构建，已有目标存在时会拒绝覆盖。通常独立复核只需加载正式模型、运行新的 `python -m pll_allocation.block_space ... --out <new-dir>` 和 pytest；不需再次执行构建脚本。

完整测试 **179/179 通过**：原 Stage 1 及旧框架162项 + 本阶段17项。无skip/xfail，历史24组MATLAB参考轨迹仍通过。实际新增测试覆盖输入冻结、域/单位、联合调谐、Routh解析不变量、确定性采样、异常、无/多交越、公式源SHA、校准协议、实际短事件稳态仿真和参考候选。证据：`tests_20261104.xml`。

保护检查 **4896/4896 既有文件未变化**：原工程Python源码、旧测试、Stage 1代码/配置/报告/结果、旧输出、MATLAB工程和章程均已核对。两份允许追加的项目状态/决策文档单独更新；新文件不在既有保护集合内。证据：`audit/protected_before.json` 和 `audit/protected_after.json`。

本阶段主域扫描139点（134个声明域内），124个M1有效点全部数值一致，44个M1规格通过、80个M1规格失败、15个UNKNOWN。32点事件比较共64次仿真，26点获得条件频率/控制一致性，6点不可比/不一致；另4次边界诊断。MATLAB Runtime=0，LLM=0；测试内的短事件调用另计，不混入域扫描证据。未把内部公式一致性当作独立行为模型准确度。

## 校准与后续边界

`pll_allocation/block_space/calibration.py` 提供可执行 discrepancy schema；主运行保留32份原始频率比较记录，含版本、参数哈希、两个测量协议、条件可比性、误差、证据、局限和建议。分类允许数值错误、假设不适用、参数语义冲突、缺失行为效应、测量协议不一致、未决。没有残差拟合、经验修正或修改原公式。近轨跟进分析另存 `CALIBRATION_REVIEW.json`。

足以供明确标注M1研究目标的后续逆向原型消费；不能据此声明完整M2 first-shot成功率。推荐先建立可保存波形的事件频响注入及严格捕获测量，覆盖名义、BW/PM边界、高UGF/fref与近轨点。Jitter/Lock Time/Static Phase Error、非理想CP/reset/负载/曲率仍不受支持。Stage 1.5在此结束。
