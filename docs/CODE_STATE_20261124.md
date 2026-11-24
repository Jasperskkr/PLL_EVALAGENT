# 当前集成代码与发布交接（2026-11-24）

代码已提交并完成提交后的独立检出审核，发布目标为远端main。执行代码受测版本为 `f8ae262212861a0a1803c0781b672029bad3e5b7`；其后的发布摘要补充仅修改文档。完整结果见 [提交版本审核](PUBLISH_AUDIT_20261124.md)。

## 已集成内容

| 范围 | 当前状态 |
| --- | --- |
| 原噪声/M2模型及修复 | 保留连续噪声模型、原生噪声/非理想后端和独立协议；源码可重新构建 |
| 条件物理分配 | 噪声预测、启动构造、统一排序、LLM工具证据；四项开关默认关闭，预测无正式M2 PASS权 |
| 正整数N | 标准连续M2读取当前N，以N×10MHz为输出目标；当前参考/电压轨范围保留 |
| VCO contract | guidance、实测目标点、原用户硬约束、CP交集和f0/Kvco回填再验证；默认分配不依赖开发功能 |
| 输入输出与交接 | 严格外部JSON、结构化错误、相对M1 context、READY一致性、共享交付门禁、权威run_manifest |
| 发布维护 | README/章程/架构/代码导读/审查指南更新；修复干净检出的兼容文件换行属性 |

## 主线与消费边界

`problem + allocator → pipeline → spec_allocation → initial/RegionExplorer/正式M1 → 独立复核与verification_handoff → feedback/原生M2 → delivery → sizing_handoff/run_manifest`。

用户规格和六轴域来自ResearchProblemV2，N是当前问题固定参数；策略预算由allocator控制。正式推荐读 `recommended_M2_supported`，正式候选集合读 `sizing_handoff.json.candidates`，先调用 `validate_sizing_handoff`。完整运行目录可迁移；旧协议/绝对context继续按原版本消费，不升级历史证据。

## 提交后的验收

- 独立克隆304个维护文件，四个后端从提交源码重新构建；完整回归958通过、10项历史档案依赖跳过、零失败/错误，`-W error`。
- 13组Spec/N的真实CLI验收，230项独立检查通过；实际151次M1、36次M2、3844个原生子运行，无LLM/TEST。
- N8 nominal/tight各3/3，N16为2/2；严格N4/N10均1/2；此前N10、lock下限60µs为1/1（实测72µs）。失败、部分与空交付如实保留。
- 12组VCO导出均通过源文件字节/候选/频率校验，原handoff不变；附加函数轨迹覆盖正式父/子进程，无旧业务函数调用。
- wheel内容和实际安装核对通过；受测检出全部维护文件SHA不变，状态干净。

## Git与后续工作

保留既有 `70e9dda` VCO提交，新增 `b6aa626` 完整集成及 `f8ae262` 换行属性修复。用户已授权更新 `https://github.com/Jasperskkr/PLL_EVALAGENT.git` 的main，采用普通快进推送，不改写历史；最终远端身份以Git refs和本次交付回报为准。

实验、outputs、handoff_exports、DLL/build、凭据及 `learn/n10-spec-trace-20261124/` 一次性旧教学追踪均留在本地；可复用物理反解说明已提交。原始证据目录为 `experiments/publish_20261124_01/`。

剩余结构债务是旧模块提前导入、来源依赖与计算依赖仍有交织；正式主线未执行旧业务，后续可单独做延迟加载重构。标准M2 PM/jitter仍UNKNOWN；不保证任意规格、真实器件或PVT通过。结构分类依据见 [结构审核](STRUCTURE_AUDIT_20261124.md)，先前12组矩阵记录见 [多规格验收](SPEC_MATRIX_AND_REMOTE_20261124.md)。
