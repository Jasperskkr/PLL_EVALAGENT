# 职责命名与兼容边界

本次审查覆盖维护源码、Python导入、原生生成器/构建脚本、配置、测试夹具、结果文件和文档。后续名称应回答“负责什么”，不再表达项目推进阶段。

## 主要命名

|旧位置|推荐位置|职责|
|---|---|---|
|`verification/stage6c.py`|`verification/nonideal.py`|非理想行为验证编排|
|`verification/stage6c_native.py`|`verification/nonideal_noise_native.py`|非理想与噪声的原生仿真适配|
|`verification/stage6c_identity.py`|`verification/nonideal_noise_identity.py`|原生源码、生成器与二进制身份绑定|
|`verification/stage6c_kernel.cpp`|`verification/nonideal_noise_kernel.cpp`|非理想与噪声事件内核|
|`block_space/extensions.py`|`block_space/profiles.py`|噪声/非理想参数profile的合同、校验与派生量|
|`verification/closed_loop.py`|`verification/phase_step.py`|相位阶跃响应分析|
|`verification/closed_loop_native.py`|`verification/phase_step_native.py`|相位阶跃原生适配|
|`verification/closed_loop_kernel.cpp`|`verification/phase_step_kernel.cpp`|相位阶跃激励与事件观测|
|`verification/build_closed_loop.cmd`|`verification/build_phase_step.cmd`|构建相位阶跃后端|
|`track_a/runner.py`|`allocation/first_allocation.py`|旧冻结问题的首次分配执行|
|`track_a/benchmark.py`|`studies/allocation_baselines.py`|等预算分配基线编排|
|`track_a/experiments.py`|`studies/simulated_repairs.py`|显式模拟反馈修复练习|
|`track_a/audit.py`、`report.py`|`_legacy/archive_audit.py`、`archive_report.py`|依赖历史材料的审计与报告工具|
|`track_a/__main__.py`|`allocation/__main__.py`|旧基线CLI；正式主线仍使用pipeline|

`configs/verification/profiles/nonideal_combined.json` 已按职责命名，保持名称和参数载荷。它是预设研究profile，名称不暗示来自器件拟合或已通过完整认证。

`M1`、`M2`、`v1`、`v2` 表示模型层级或数据版本，具有技术含义，继续保留。

## 构建和运行

默认构建目录改为 `build_phase_step/`、`build_return_ratio/`、`build_nonideal_noise/`。相位阶跃库名改为 `phase_step.dll`；导出函数保持原ABI。标准理想后端的 `build/` 和 `kernel.cpp` 保持原样。

```powershell
cmd /c pll_allocation\verification\build_phase_step.cmd
cmd /c pll_allocation\verification\build_return_ratio.cmd
cmd /c pll_allocation\verification\build_nonideal.cmd
```

重命名后的源码与旧身份不同，须在全新目录构建。不得把旧identity文件改成新哈希来绕过检查，旧构建目录和实验记录保留。

非理想/噪声后端优先读取 `PLL_NONIDEAL_NOISE_BUILD_DIR`；未设置时接受旧 `PLL_STAGE6C_BUILD_DIR`；都未设置时使用新的默认目录。

内部样本集合使用 `calibration_samples`；数值验证入口使用 `run_validation()`；反馈CLI内部字段使用 `verification_*`。旧 `stage7_samples` 属性、`run_stage1()` 和 `run_stage9_feedback(..., stage9_config=...)` 是兼容入口。

新增/推荐的结果文件为 `exploration_report.md`、`region_exploration_report.md`、`verification_problem_resolved.json`、`verification_config.json`、`verification_run_events.jsonl`。原有 `verification_handoff.json`、`verification_result.json` 等职责名继续使用；历史结果名仍输出兼容副本。

## 有意保留的旧名称

本次不对所有字符串做全局替换。以下记录承担兼容或证据职责：

- 旧Python模块只作转发，旧命令只作兼容入口，正式实现与活动调用使用新位置。
- schema、protocol_id、model version、strategy/source标签和部分序列化键保留原值，例如 `pll-stage9-result-1.0`、`ready_for_stage9`、`STAGE7_CALIBRATION`。更改这些值需要独立的数据合同升级。
- 配置profile的ID、来源描述，以及历史实验路径保留实际出处；不能为消除阶段字样改写研究来源。
- 旧JSON测试夹具的文件名已改为职责名，文件内容保持原字节，其候选ID和证据元数据保留。
- 六份原分配实现保持原字节，其中旧标签属于受保护的数值来源合同。
- `_legacy` 中的归档工具保留旧材料路径，明确不属于默认分配链。

因此，搜索阶段字样仍会找到上述历史合同和兼容记录；它们不再作为活动实现的位置或项目阅读入口。

## 检查和迁移证据

`configs/provenance/naming_migration.json` 记录全部21项文件迁移、源码更新前后SHA及兼容入口。原有配置迁移收据保留，后续身份变化通过该收据衔接。活动物理关系索引绑定当前源码；物理方程和原始来源没有换成其他实现。

`tools/audit_architecture.py` 同时检查职责依赖、原分配源码字节和活动文件/导入命名。新增活动模块若出现 `stage数字`、`track_a` 等路径会失败；已声明的兼容转发层单独列出。接口回归验证旧模块与新模块对象一致，而非复制一份实现。

本次实际测试和数值对照见 [运行说明](RUNNING.md)，逐文件用途见 [代码导读](CODE_MAP.md)。
