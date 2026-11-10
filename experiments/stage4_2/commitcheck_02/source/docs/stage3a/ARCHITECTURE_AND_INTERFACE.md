# Stage 3A 正式架构与运行接口

正式推荐入口：`python -m pll_allocation pipeline`。旧`run/suite`与各阶段入口保留作兼容/历史复现，它们不能替代本入口对Stage1.5的M2验收。

```text
configs/
  BLOCK_SPACE_MODEL_V1.json        原Stage1.5正式模型，未改
  PLL_EQUATION_REGISTRY_V1.json    原公式注册表，未改
  SYSTEM_SPEC_STAGE1_5.json        model.experiment.system_spec同内容视图
  pipeline_stage3a.json           版本/hash绑定、预算、LLM环境变量配置
  verification/protocol_v1_1.json 原Track B协议逐字节提取
pll_allocation/
  physics_mapping/                原物理公式/M1/judge，未改
  block_space/                    原域加载与约束检查，未改
  track_a/                        原解析、优化、Agent、repair算法，未改
  allocation/__init__.py          共用策略接口、原算法调用及反馈接收
  verification/                   Track B最小运行闭包、原生核、构建与身份检查
  pipeline_contracts.py           输入/结果版本检查、状态/反馈信封适配
  pipeline.py                     独立控制落盘、M1、全M2、预算、反馈、报告
experiments/<new-run>/
  run_manifest.json              输入、源码、协议、依赖、策略/LLM配置、预算
  input_system_spec.json / block_space_snapshot.json / protocol_snapshot.json
  initial_joint_block_spec.json  首次M2前冻结
  AllocationProposal.json        首次正式完整候选、原M1及元数据
  attempt_001/                   约束检查、M1、M2、偏差、反馈与Agent接收凭据
  raw/attempt_001/                成对捕获、四组频响的请求/轨迹/测量/收敛
  allocation_trace.jsonl / cost_events.json / result.json / report.md
```

Track A继续在原位置维护；allocation为薄接口，没有复制算法。verification不是第二个Track B工程：只保留五个运行模块和原生核，移除研究套件、画图、历史读取与独立CLI。原Track B目录保留为只读研发证据。正式包没有顶层`experiments`等脚本导入或对track_b运行路径的依赖。

## 执行

在项目根目录，Python 3.11+，安装项目integration依赖（实际测试Python3.12.10、NumPy2.5.3、SciPy1.18.1）。

```powershell
python -m pip install -e ".[integration,test]"
python -m pll_allocation pipeline --strategy analytical --out experiments/my_analytical
python -m pll_allocation pipeline --strategy sensitivity_optimization --out experiments/my_optimization
python -m pll_allocation pipeline --strategy llm_agent --out experiments/my_llm
python -m pll_allocation pipeline --strategy random --m2-budget 2 --repair-budget 1 --out experiments/my_repair
python -m pll_allocation pipeline --proposal docs/track_a/delivery_final/AllocationProposal.json --out experiments/my_reverification
```

目录必须不存在。源checkout内默认配置基于包位置解析，无需依赖当前工作目录。已在系统临时目录作为CWD实际完成一次正式Proposal复验。CLI返回0表示流程执行完成；必须读取result.status与full_behavioral_pass判断科研结论，M2_PARTIAL_PASS并非完整通过。

本机已审查并逐字节提取原DLL供实际验收，二进制不进入Git；新机器须先构建：

```powershell
.\pll_allocation\verification\build_kernel.cmd
```

使用原MSVC C++17 Windows核和原编译选项，默认VS2022 Community路径；其他安装位置需显式调整构建脚本。首次构建生成build/identity.json，运行前核对源/二进制SHA。构建目录是可重建本地产物，重建前需保留或移走已有identity记录，避免覆盖。缺DLL、身份不符或数值超域返回UNKNOWN并保留失败成本。没有跨平台原生后端或已验证wheel分发；pyproject只打包源码/构建入口和正式配置，不把本机DLL放进通用wheel。本机缺setuptools，未进行pip安装/wheel构建验收；上述源码入口和依赖实际可运行。

## Python合同

`run_pipeline(out, strategy, *, config_path=None, proposal_path=None, m2_budget=None, repair_budget=None, llm_config=None, policy=None)`。

`AllocationPolicy.propose(model, system_spec, meter, out, history)`返回完整SI候选和元数据；`receive_feedback(candidate, feedback)`接收版本化反馈。Runner拥有最终检查/执行/判决权。默认FIRST_SHOT一次；显式修复预算只复用已有Track A repair。所有正式新候选在当前次M2前保存，已有候选复验单独标记。未知测量/超域停止自动调参、保留诊断，LLM首发后可接收反馈但真实LLM修复策略未实现。

`AllocationProposal`沿用`allocation-proposal-1.0`，17参数、单位、四项conventions、固定工况、SystemSpec、版本与hash绑定。原M1不能认证M2。

`verification.verify(proposal, new_out)`直接执行提取的Track B验证闭包，输出`behavioral-verification-result-1.0`。Runner额外检查候选/SystemSpec/模型/源文件/协议版本、所有必需约束、整体判决和禁止的PASS升级。

`allocation-feedback-1.0`补全Track B诊断列表缺少的信封：source=M2、候选hash、SystemSpec/BlockSpace/协议hash、kind、FAIL/UNKNOWN、各指标和可靠性、通过/失败/未知列表、偏差、原因、剩余预算。实际调用原`track_a.repair.interpret_feedback`，后续确定性修复读取同一history；可检查`agent_feedback_receipt.json`及实际修复轨迹。

## 状态与成本

|字段|语义|
|---|---|
|FIRST_SHOT|当前运行首次提交，无当前运行M2反馈；设计期M1查询独立计数|
|FEEDBACK_REPAIR|收到本次真实M2后提交完整新候选；继续完整M2|
|M1_PASS / M1_FAIL / M1_UNKNOWN|原M1 judgment映射；不是行为认证|
|M2_PARTIAL_PASS|至少一个必需指标PASS、无必需FAIL、仍有UNKNOWN；原M2整体UNKNOWN保留|
|M2_FAIL|至少一个必需指标可靠失败|
|M2_UNKNOWN|没有已通过的必需指标，或后端/域/数值错误|
|M2_PASS|所有必需指标独立PASS；当前协议不能产生此状态|

当前BW可为PASS/FAIL/UNKNOWN，PM和微Hz频率精度不能PASS。UGF无直接环路注入为UNKNOWN。捕获/锁时/电压是协议条件下的诊断，不擅自变成新增SystemSpec门限。

M2_calls计完整验证器调用，不等于原生仿真次数。单次通常106点，本轮失败首发114点；每次包含真实双步长捕获及四套全扫描。native_completed_runs、native_failed_attempts、integration_points、native_elapsed_s和总耗时分别记录。Track B测量后重算M1另计M1_posthoc_calls，M1_total_calls包含它。LLM真实调用/原始响应/usage/耗时在attempt_001/llm_calls；未提供货币单价时monetary_cost=null。测试注入异常不计真实LLM或成功M2成绩。
