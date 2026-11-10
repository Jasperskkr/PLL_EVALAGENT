# Stage 7 M1 Exploration — Baseline Audit

2026-11-10；工作区 `F:/LJP/概伦AI/PLL_allocation`，分支 `master`，HEAD `e395f24859cdd81e3deb5ea83ba3f9598a27cd16`。本轮不切分支、不创建副本。原有修改是 D024/预检文档及两份历史 ZIP 删除，保持原状。此前同 HEAD 的完整回归实跑 478 passed / 43.76s，证据见 `../stage7_10/BASELINE_TESTS.xml`；本阶段完成后另跑新增验收和完整回归。

| 审查文件 | 实际语义与本阶段取舍 |
|---|---|
| `block_space/contracts.py` | `make_candidate/check_parameters` 强制原实验域；C1/C2 为离散 choices，且频率固定为 10MHz×8。保留冻结合同；Stage7 用独立连续域合同，不放宽旧 checker。 |
| `physics_mapping/model.py` | `evaluate/MetricRequest/M1Evaluator` 是正式 M1；17 个显式 SI 输入，6 个自由变量。正 Icp/R/C/Kvco、整数 N、线性 VCO、内部调谐点、理想 CP/LF。8000 点默认频率扫描求 BW/UGF/PM。C1/C2 本身允许任意正数。原 evaluator 逐字节保留并直接调用。 |
| `physics_mapping/registry.py` | 只读能力索引绑定原域、原 SystemSpec 和源码；不能直接接受新域，也不执行求解。保留其绑定，不伪称新域经过历史验证。 |
| `physics_mapping/experiment.py` | `parameters_from_experiment` 已支持 range；旧 `validate_experiment/judge_experiment` 要求 v0 draft、频率/BW/PM 全部存在且来源为 M1，不能表达禁用/待测 Jitter、Lock Time。复用参数构造函数，新增 V2 Spec 判决合同，正式数值仍调用同一 M1。 |
| `allocation/physics.py` | `inverse_at_shape(model,C1,C2,target_bw,x,meter)` 接受连续电容，依赖 axes/bounds；可复用以生成种子。`raw_prediction` 是快速代数根；`pm_ceiling`/`phase_interval` 为连续 LF 相位必要条件。`propagate` 枚举旧 choices，不直接套用新域。 |
| `allocation/allocate.py` | analytical/SLSQP 均枚举电容；sensitivity 只对 Icp/Rz/f0/Kvco 求局部差分。原实现保留，不复制优化器。Stage7 增加六个连续变量的局部差分适配，扰动点仍走同一正式 M1。 |
| `allocation/multispec_search.py` | Stage6B `SearchController` 是原 A/B/C、M2 反馈及信任域搜索；不改历史定义。其逐候选检查/预算/证据原则沿用，Stage7 不运行 M2。 |
| `allocation/agent.py` | 工具决策与 Messages transport；本阶段不导入运行、不调用 LLM，不把物理种子标为 Agent 成果。 |
| `pipeline.py` | 正式入口 `python -m pll_allocation pipeline`；Stage6B `run_multispec` 调原 `run_pipeline` 完整 M2。新增显式探索选项路由至同包的探索接口，旧默认和 A/B/C 不变。 |

模型域只表示理想连续锁定点数学模型能力，用户扩大参数范围不会获得电路能力、周期稳定、捕获或噪声认证。M1 的源公式和采样等价性边界保留；正式 M1 数值失败不退回代数结果作为通过。

## 本轮实现合同

- 独立 `pll-research-problem-2.0`：六个连续 range、SI 单位、default、linear/log 尺度；固定 topology/N/f_ref/电压及非理想项；每个 Spec 独立启用、上下限及评价来源。
- 原 M1 支持的指标参与 M1 可行性；Lock Time 待 M2，Jitter 未配置可信映射则 UNSUPPORTED。全 Spec 未评价完不得输出完整 PASS。
- 正参数、域及内部调谐为模型必要条件；最大 C2/C1 给出全域 PM 必要上界。未找到样本只报未找到；仅有严格必要条件矛盾才报告 M1 假设下不可行。
- Scrambled Sobol 固定 seed；默认点和连续形状反解种子；样本/代数/正式 M1 各有预算。SHA256 精确候选去重，不舍入参数。
- 可行代表点在配置坐标中选取；附近盒子仅为采样支持的搜索建议。六参数归一化差分保留扰动 Evidence IDs、单侧/双侧和域受限状态。
- 输出新建目录，拒绝覆盖。PhysicsContext 供 Stage8 读取；本阶段不实现/启动 Stage8。

历史 `docs/stage7/` 是后更名 Stage6C 的资料。本阶段文档单列 `docs/stage7_exploration/`，不覆盖其内容。复用文件 SHA256 和本轮完整跟踪条目保护清单写入新的 F 盘实验目录。
