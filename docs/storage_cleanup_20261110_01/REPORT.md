# C盘PLL工作副本清理实录

2026-11-10，依据用户“全部清理，保证F盘主线代码；数据无所谓；后续不得在C盘建工作区”的明确授权执行。

删除两个stage6b-bundlecheck完整目录，以及stage6a-multispec-feasibility、stage6b-sensitivity-allocation、stage7-noise-nonideal下的experiments/delivery。PowerShell对显式白名单的绝对路径逐项验证，以LiteralPath删除；未使用reset、clean、stash或跨shell递归删除。C盘可用空间实测从约5.091GiB到16.988GiB，增加11.897GiB（系统其他写入可能影响差值）。

三处managed worktree的归档被应用保护拒绝，两处因其他任务占用、一处为当前任务主checkout。未绕过保护，仍分别留44,536,632 / 44,982,109 / 48,929,868字节，总约132MiB。不得称全部工作树已移除，也不得继续在此运行研究。

F:/LJP/概伦AI/PLL_allocation的master起点e11a4b028ba052c6ce55eb227c4bb18397576c91。清理前后340个受保护文件SHA256相同，理想和Stage6C原生构建身份校验通过，pipeline --help通过。源码/模型/协议未修改；此次无新M2/LLM调用。原有两份ZIP未暂存删除与其他未跟踪文件保持。

机器回执见RECEIPT.json；完整before/after/deletion_receipt/deletion_events/validated_deletion_plan保存在F盘experiments/storage_cleanup_20261110_01，不随主线重新打包大数据。开发约束写入AGENTS.md与D023，后续实验、临时索引、构建与导出均在F盘。

实际执行方式：先运行protect_mainline.py生成指纹，再运行cleanup.ps1，完成后逐文件重新SHA256核对；调用verification.build_identity.check_build与stage6c_identity.check_build，执行python -B -m pll_allocation pipeline --help。此次不重复此前已完成的478项物理回归。
