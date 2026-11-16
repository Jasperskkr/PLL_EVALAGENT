# 维护工具

分配和反馈都通过 `python -m pll_allocation pipeline`。这里仅保留五个服务于现有源码、模型关系和可选内核的维护工具。

|工具|具体工作|产物/使用时机|
|---|---|---|
|`audit_architecture.py`|检查正式模块依赖方向；核对六份原分配实现的来源 SHA256|只读审计 JSON；整理代码后检查|
|`build_block_relation_atlas.py`|用原反解和正式 M1 整理冻结模型变量关系、条件域及局部示例，并做独立 KCL 数值核对|JSON/CSV/HTML 关系图谱和计费；帮助理解现有模型，不是新的 Allocation Solver，也不执行 M2/LLM|
|`create_verification_profiles.py`|生成预声明的噪声、非理想环境和协议模板|17份 JSON 及 manifest；只写全新目录，不覆盖活动配置|
|`generate_phase_step_kernel.py`|从理想内核生成相位阶跃观测/激励扩展|`phase_step_kernel.cpp`；维护生成源码时使用|
|`generate_nonideal_noise_kernel.py`|从同一理想内核生成可选噪声/非理想扩展|`nonideal_noise_kernel.cpp`；维护生成源码时使用|

从仓库根目录运行，例如：

```powershell
python tools/audit_architecture.py --out experiments/my_audit_01.json
python tools/build_block_relation_atlas.py --out experiments/my_atlas_01
python tools/create_verification_profiles.py --out experiments/my_profiles_01
```

输出路径必须全新；审计文件的父目录须先存在。两个内核生成器直接运行也拒绝覆盖现有 `.cpp`。仓库已包含生成源码，正常编译/分配无需再次生成；不要为执行生成器删除冻结源码。非理想构建入口为 `pll_allocation/verification/build_nonideal.cmd`。

移除了70个旧阶段审计、固定实验运行、汇报绘图、打包和一次性迁移脚本。它们服务于旧研究过程，正式 Pipeline 不依赖它们。可复用的计算窗口适配器已迁入 `pll_allocation/agent/computational_window.py`，仍采用原 Policy/Runner 和真实 API；旧批量压力实验编排已删除。历史实验不随源码发布，本地历史保留。
