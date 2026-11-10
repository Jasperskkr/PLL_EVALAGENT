# 当前统一主线架构

统一工作区：`F:/LJP/概伦AI/PLL_allocation`。原始研究章程保留，2026-11-10研究重心更新见D022及`docs/research/ALLOCATION_STRATEGY_SCOPE.md`。

```text
python -m pll_allocation pipeline
  ├─ default: run_pipeline / AllocationStrategyPolicy
  │   ├─ frozen inputs/hash → full first proposal saved
  │   ├─ domain + M1 → original ideal M2
  │   └─ feedback → optional deterministic repair → full M2 again
  └─ explicit --multispec: run_multispec / original A/B/C
      ├─ versioned research problem + same frozen base assets
      ├─ Analytical / sensitivity + original SLSQP
      ├─ same run_pipeline → real complete M2
      ├─ per-hard-constraint judgment + source-bound cache/costs
      └─ C deterministic search → recheck every supported constraint
          └─ optional Stage6C profile: nonideal/noise M2 + independent statistics
```

## 所有权与边界

M1归`physics_mapping/`，Allocation/Agent归`allocation/`，M2归`verification/`。Policy只能提议完整候选与理由；Runner拥有输入绑定、预算、TB和最终判决权。默认路径未启用非理想或噪声。Stage6C关闭新增机制时复用原模拟器；不维护另一正式Pipeline。

原六参数分配、M1公式、理想kernel、域、SystemSpec和协议不变。新增`multispec_constraints/search`来自Stage6B；Stage6C的噪声优化钩子受原solver源码锁控制，不替换冻结`allocate.py`。

首个完整候选在首次TB前保存。每次完整M2内部包含多次native仿真，二者分开计数。缓存使用候选/来源/协议/profile绑定，不能冒充新测量。每次调整后完整检查全部支持硬约束；FAIL/UNKNOWN不能被其他指标改善抵偿。

默认预算为1完整M2、0repair；显式预算才允许原确定性修复。真实LLM已可工具辅助首发，但正式LLM修复仍返回`REAL_LLM_REPAIR_NOT_IMPLEMENTED`。后续策略工作应在现有边界补齐，不把历史mock或legacy run/suite当成实现。

## 判决范围

默认M2可靠BW通过时，周期PM和微Hz精度仍UNKNOWN，整体通常`M2_PARTIAL_PASS`。Stage6B/C的`RESEARCH_JOINT_FEASIBLE`是混合证据的限定研究结论，`FULL_SYSTEMSPEC_CERTIFIED`仍false。M1名义PM、有限扰动恢复和严格周期/全局稳定分开。

核心Agent策略研究固定BW、名义PM、内部调谐、条件捕获的定义；可选噪声/非理想环境不作为进一步完善M1/M2的任务。新增指标或模型修改必须有另行授权和版本化依据，不能为策略获胜事后改变门限。

## 构建与记录

原native身份保留；Stage6C新建自己的F盘构建身份，加载时检查原核、生成核、生成器、适配器及DLL SHA。默认扩展目录`verification/build_stage6c`，不同新构建通过`PLL_STAGE6C_BUILD_DIR`显式选择。禁止覆盖旧build或修改identity绕过检查。

原始实验不移动；本地运行与交接副本通过.gitignore与维护源码分开。必要历史JSON测试输入逐份纳入提交，其他历史证据原位置及完整包见`docs/mainline_integration_20261110_01/EVIDENCE_INDEX.md`。本次来源/备份/SHA/真实命令、归并前后科学结果、失败与干净导出验收见同名experiments目录及最终报告。

Stage3A.1原架构原字节保存在`docs/mainline_integration_20261110_01/prior_guides/MAINLINE_ARCHITECTURE.md`，不将旧阶段的版本号/测试数混作当前验收。
