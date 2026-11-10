# P0 已有系统审计

审计日期：2026-11-03（Asia/Shanghai）。主线依据：`PROJECT_CHARTER.md`。证据：`docs/audit/source_inventory_before.json`，工具：`tools/audit_sources.py`。本轮为本地源码、Git、正式小型报告和来源文件核对；没有重算历史大型 RAW，也没有重做晶体管资格。

## 来源身份与版本

父目录为 `F:/LJP/概伦AI/`。字面目录 PLL_AGENT2、PLL_BASELINE 不存在；实际找到 PLL_AGENTV2/PLL_AGENT、PLL_SPEC_ALLOC_BASELINE。下文按其可访问源码审计，不把名称相近当作版本等价证明。

|实际目录|身份与可访问内容|Git 状态|
|---|---|---|
|PLL_AGENTV2/PLL_AGENT|Formulator、Problem2 搜索、agent_runtime、工具后端、MATLAB、实验与结果|自身无 .git；不能给出该副本的提交身份|
|PLL_AGENT|较早独立仓库，用于来源对照|HEAD 00fb7e0a82a5daba3ca1c72b8d1897ef97b86584；存在大量原有修改/删除/未跟踪文件，未清理或复位；完整原始status已保存|
|PLL_SPEC_ALLOC_BASELINE|80 MHz 分配、Legacy Phase2、84 MHz Triplet、fixtures、正式运行、G1 系列|自身无 .git；按文件 SHA 锚定|
|PLL_SPEC_ALLOC_M05_REPO|冻结导入的独立 Git 仓库|baseline-import，ae93e5f3af7bfabc75066099e833c0dcc12c6e67|
|PLL_SPEC_ALLOC_M05_WORKTREE|同仓库共享执行工作流|feat/m05-workflow，a5418ad50c6ba6a840b65d695f07dddfdeb4b121|
|PLL_SPEC_ALLOC_M06_WORKTREE|M05 加 CP 校准反馈|feat/m06-cp-calibration，b428af61e5fce050f1c1d2fb2f6605244efdadb8|
|PLL_SPEC_ALLOC_M07_WORKTREE|M06 加物理证据读取|feat/m07-physical-evidence，1e6b20ae93a466093648e87d34df37bcf7e6b9d0|
|PLLngspice_vs_matlab|Experiment A，MATLAB 行为模型、模块电路、历史表征|文件级追溯|
|PLL_Physics_FactorGraph_MATLAB/PLL_Physics_FactorGraph_MATLAB|模型、characterization、factor extraction、sweep|架构和关系参考，不能自动认证数据等价|
|PLL_FINAL|原开发方案；目前没有完整新主线实现|文档来源|

M05→M06→M07 为线性继承。四个 checkout 的状态为空，无 remote；本目录初始为空且不是 Git 仓库，故直接在用户指定目录建立新主线，无须从包含物理依赖的 M07 创建 checkout。

## 已落实的源码事实

1. Baseline `allocation/candidates.py::generate` 生成完整 CP/LF 网格；`allocation/allocator.py` 逐候选调用真实 Python 行为核心。不是接口占位。
2. Baseline `evaluation/python_behavioral.py` 按参考周期计算带符号 CP 电荷、两状态 RC 精确转移和线性 VCO 相位积分，运行 40 µs。400 周期（80 MHz）或 420 周期（84 MHz）；不是晶体管/边沿级模拟器。
3. `experiments/triplet.py::targets/evaluate_target` 已实现 CP/LF/VCO 五轴联合域，旧正式记录包含 450 候选，不能再声称缺乏联合搜索。该入口同时导入证据/校准/模块执行模块，不适合整体移入最小主线。
4. Legacy `feedback/controller.py::FeedbackReplay` 已有实际模型重评、实现重选、`reallocate_targets` 调用网格搜索和要求差异分类。它主要解决证据开放和模型修订，不能直接当成新课题的 LLM 行为违例修复。
5. M05 的 `feedback/controller.py::ActionGuard/ActionExecutor/WorkflowRunner`、`agents/interfaces.py::WorkflowState/ToolResult` 已可执行。M06 在同一控制器增加 CP 拟合、独立点检查、发布与原候选重评；M07 添加 `evidence/physical.py`。本轮借用边界、预算和 trace 设计，保留小型流程，不整包移植。
6. M07 的 REALLOCATION 动作合同不等于共享 Runner 已实现通用重新分配 handler。Legacy 重分配与 Runner 的接口占位应区分。
7. AgentV2 `agent_runtime/orchestrator.py` 注入 controller/revision factory，`state.py` 记录 SHA 链和预算；`problem2/decision/policy.py::FeedbackPolicy` 已有基于观测邻域的有限搜索。可参考其策略可替换边界，不整体引入 region/realizer/evidence 系统。
8. AgentV2 `problem1/llm_formulator.py::OpenAIProblemFormulator` 有真实外部调用、JSON 校验和日志。但它输出 AllocationProblem，不是完整 JointBlockSpec；不能冒充已完成 LLM 联合分配策略。
9. Baseline `integrations/system_tb_stub.py` 返回 NOT_AVAILABLE/UNKNOWN。`evaluation/protocol.py` 只有 evaluate 协议，当前调用链仍硬接 Python 实现。新主线必须实际注入 Backend；不能用改名后的 stub 代替 TB。

## 模型与数据可信度

本轮逐项核对两个 provenance 清单，共 **97/97 个引用 SHA 匹配**（32+65 个引用，不等于97个独立实验）。完整路径、原声明和本轮实际 SHA 均写入审计 JSON。

旧 `verifier-reports/independent_matlab_comparison.json` 含24组纠正后 MATLAB 对照，9600周期；旧报告给出的全轨迹最大差为相位5.465e-7°、频差0.000386ppm、Vctrl 3.825e-10V。本次将作为历史回归依据，不能称为本轮 MATLAB 新执行，也不能外推为晶体管准确度。

CP 的 q0 是包含局部代理 DC 需求的平衡电荷，禁止再次扣漏电；50 fF/1 GΩ 不是已测真实 VCO 输入导纳。VCO 的已校准锚点属于同一电路；f0/Kvco 的新组合是声明目标。PFD/Divider 在本行为后端是理想固定行为。

历史经验 CP 域仅约±100ps，旧捕获轨迹可能超域；新声明目标模型的数学有效域与历史电路经验域分开记录。G1/G1.1 的数值失败/未知保留，不能为新主线提供通过标签。

## 审计限制

- 本轮不声明完整审查所有2425个源文件的语义；清单提供指纹，重点模块按上述调用链阅读。
- 数据目录只统计扩展名/数量/体积，原 RAW 不读入策略。旧报告中的仿真次数是历史记录，不记为本轮成本。
- MATLAB 可执行文件可发现于 E:/matlabR2021a/bin/matlab.exe；可发现不等于许可证及接口已验收。
- 不能将 AgentV2 的 Python 3.13、numpy、GUI 和仿真工具依赖整体带入新的 Python 3.12 最小系统。

结论：直接提取已回归的行为积分与测量核心；适配原候选域、物理关系和冻结协议；参考 AgentV2/M05 的策略与执行边界；隔离 M06/M07 的物理证据及 sizing 逻辑。具体见其余 P0 产物。
