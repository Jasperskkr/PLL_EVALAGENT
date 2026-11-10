# 源码与历史证据位置

本次把正式实现、版本配置、测试、工具、必要研究报告与轻量实验记录集中到F盘。旧目录与旧证据不移动、不覆盖；复制的历史记录保留原运行路径/时间/SHA，它们不是本次新执行。

| 内容 | 位置与使用方式 |
|---|---|
| 统一开发/运行项目 | `F:/LJP/概伦AI/PLL_allocation` |
| 本次归并与回归 | 本项目`experiments/mainline_integration_20261110_01/`及同名docs目录 |
| 原Stage6C源码来源 | `C:/Users/Lenovo/.codex/worktrees/stage7-noise-nonideal/PLL_allocation`，后续作为归并来源/历史参考 |
| Stage6A完整原始研究树 | `C:/Users/Lenovo/.codex/worktrees/stage6a-multispec-feasibility/PLL_allocation/experiments/stage6a` |
| Stage6B原始研究树 | `C:/Users/Lenovo/.codex/worktrees/stage6b-sensitivity-allocation/PLL_allocation/experiments/stage6b` |
| Stage6C正式六组完整原始结果 | `F:/LJP/PLL_Stage6C_results/study_01` |
| Stage6C已验收完整源码/结果包 | `F:/LJP/PLL_Stage6C_results/delivery_final_02/PLL_Stage6C_reproducible_bundle.zip` |
| 上述包独立验收 | `F:/LJP/PLL_Stage6C_results/delivery_final_02/acceptance_01/FINAL_ACCEPTANCE_RECEIPT.json` |

完整包SHA256：`eef48c1c26412de7354a11f1a1cfa01f4907055a41dff8281125a7388aa95acb`。本次不重打或修改该包。

F盘新继承的`experiments/stage6a`是已恢复的测试/代表点子集；`experiments/stage6b`与`stage6c`是筛除native二进制、NPZ/NPY数组、raw/tmp/build/cache后的记录副本，**不是完整原始波形镜像**。需要完整PSD/波形/历史哈希树时使用上述原始位置或已验收ZIP，不能仅对轻量副本宣称全文件完整性。

当前测试依赖的少量历史JSON和Stage6A判决辅助脚本会随源码提交；其余本地实验、导出和构建通过.gitignore与源码分开。忽略文件不代表删除，既有已跟踪历史文件仍保留。
