# Stage 7 配置、运行与 Stage 8 读取接口

Stage7 只做可配置的连续域 M1 探索，所有数值评价调用现有 `physics_mapping.model.evaluate`。Stage6B 的域、SystemSpec、解析/SLSQP/Sensitivity、M2、A/B/C 不变。新模块不接 LLM，也不启动 M2。

## 唯一正式 CLI 与 Python 接口

在 `F:/LJP/概伦AI/PLL_allocation` 中运行，输出目录必须全新：

```powershell
python -m pll_allocation pipeline --explore-problem configs/stage7/continuous_global_v2.json --out experiments/my_stage7_01
python -m pll_allocation pipeline --explore-problem configs/stage7/continuous_tight_v2.json --seed 19 --exploration-budget 160 --out experiments/my_stage7_02
```

`--seed` 覆盖 Sobol seed，`--exploration-budget` 覆盖总正式 M1 调用预算（含敏感度扰动）。其他预算在配置中设置。不允许与 `--multispec`、`--m2-budget`、`--proposal`、`--scenario` 等分配/M2选项混用。CLI 退出码 0 表示研究运行完成，不意味着找到可行点或通过完整系统验收；输入错误、目录已存在、执行错误返回 2，具体结论读取 `result.json.status`。

未来 GUI 调用同一接口，不复制求解逻辑：

```python
from pll_allocation.exploration import run_exploration, load_physics_context

result = run_exploration(problem_path, new_output_directory, seed=19, budget=160)
context = load_physics_context(new_output_directory / "physics_context.json")
```

`problem_path`、输出目录可为字符串或 Path。Python 接口拒绝已存在输出目录；非法配置在创建输出前抛出 ValueError。GUI 可保存新配置后调用本接口。Stage7 未实现 GUI 或 Stage8 Agent。

## ResearchProblemV2

JSON `schema_version` 必须为 `pll-research-problem-2.0`。完整示例为 `configs/stage7/continuous_global_v2.json`；收紧规格并修改全部六个参数范围的示例是 `continuous_tight_v2.json`；PM 必要条件矛盾示例为 `pm_infeasible_v2.json`。配置属于用户声明的数学研究域，扩大范围不等于已有电路能力。

| 字段 | 含义 |
|---|---|
| `problem_id` | 自定义问题身份 |
| `topology` | 固定为原 `integer_n_cppll`，不改变 LF 连线 |
| `parameters` | 六轴 `Icp/Rz/C1/C2/f0/Kvco`，每轴必填 `min/max/default/unit/scale` |
| `fixed_parameters` | 原17输入中其余11项，全部显式 `value/unit`；N为正整数，f_ref正值，Vctrl限值有序，其余非理想项本阶段为0 |
| `specs` | 每项 `metric/unit/enabled/evaluation_source`，启用时至少一个 `min/max`；可设非负 tolerance 和正 normalization_scale |
| `exploration` | Sobol、物理种子、M1/代数预算、区域和敏感度设置 |

规范单位：Icp=A，Rz=Ohm，C1/C2=F，f0=Hz，Kvco=Hz/V。六轴均为正的连续区间；`scale=log` 使用自然对数坐标，`linear` 使用线性坐标。`default` 必须在范围内。N/f_ref 在一次运行中固定，允许用户另存新问题改变其值；这是 M1数学模型实验，不扩展 Stage6B 的固定80MHz频率合同。

M1支持的 `BW_Hz`、`PM_deg`、`UGF_Hz`、`output_frequency_Hz`、`Vctrl_required_V`、`Kvco_local_Hz_per_V` 只有在 `evaluation_source=M1` 时才参与 M1 可行性。`lock_time_s/M2` 保留 PENDING_M2；`jitter_s` 和 `power_W` 没有本阶段可信映射则 UNSUPPORTED。不能通过改 source 为 M1 来升级 Jitter 支持。禁用项为 DISABLED；启用但未评价项为 UNKNOWN。支持状态和原模型协议由程序解析生成，用户不能自行填 PASS。

每个支持指标分别保留上下界裕量 `bound_margins`、最紧的 `tightest_bound`、最小裕量及归一化裕量。M1可行只针对启用且有正式M1结果的约束；未启用任何 M1 约束时返回 M1_NOT_REQUESTED，不产生空条件“可行”。完整系统认证始终为 false。

## 探索与初筛

严格检查完整17输入、SI单位、原 M1 的理想性/正值语义、用户范围、固定项、VCO全电压域正频率及内部调谐点。复用 `pm_ceiling(C1,C2)` 检查 `PM <= asin(C2/(2*C1+C2))`；全域上界取 C1最小/C2最大。只有全域必要条件矛盾才报告 `PROVEN_M1_INFEASIBLE`，且只在理想连续M1假设下成立。没有证书或没有找到可行样本均不能宣称物理不可行。

派生映射包括：`Vreq=(N*f_ref-f0)/Kvco`（V）、`Icp*Kvco`（A·Hz/V）、除以N的环路增益、`q=1+C2/C1`、LF零点和非零极点（rad/s）、PM上界（deg）。Routh正性遵循原 M1 正参数假设，最终数值有效性仍由原 evaluator 判定。

物理种子先评价用户默认点，其余复用 `inverse_at_shape`，在连续电容比和形状坐标上反解目标BW。反解失败或越域保留原因和成本，不截断成合法候选。种子数量包括默认点，由 `physics_seed_count` 控制，0表示不加种子。它是启发式起点，不是新的优化器或 LLM 策略。

Sobol使用 SciPy scrambled Sobol、六维、固定seed；配置非2幂样本数时生成下一个2幂单位点集并使用其前n点，生成数/使用数写事件，未使用的点不评价。各轴按其scale变换，不拒绝重抽，因此无效/不可调谐样本也留证据。环境版本写入manifest；复现要求同输入、seed、代码、数值环境。

快速 `raw_prediction` 与正式 `evaluate` 独立计数，代数预算用尽不会替代正式M1或静默跳过它。M1数值失败即 UNKNOWN，保留完整 MappingResult.reason。候选经完整单位信封SHA256精确去重，不做小数舍入；17输入中连续轴统一为float，整数 N 保留整数，数值相同的3820/3820.0不会重复评价。相邻可表示浮点值仍为不同候选。

## 区域与敏感度

先以最小归一化Spec裕量选择一个代表点，再在配置归一化坐标中贪心选择最远点；不把 Sobol 可行点比例当作体积、概率或优化质量结论。区域为代表点周围 `region_radius` 宽度的坐标盒，截在用户域内，附附近已评价可行样本 Evidence IDs。**整个盒子及其角点未认证**，没有聚类连通性或全域稳定性保证。

敏感度仅对选定代表点做六轴正式 M1 差分，使用 `sensitivity_step` 坐标步长；边界单侧、内部对称或截断的局部割线。矩阵定义为 `d(metric/metric_scale)/d(u)`，u为各轴linear/log归一化坐标；另给log elasticity和PM_deg/log(parameter)。每列记录两个扰动点、Evidence IDs和状态。预算/域/必要条件受限时保留空矩阵项，不填0。

M1总预算包括探索和敏感度；预算不足时仍保存未评价候选和原因。区域在全局探索之后、敏感度之前确定，敏感度扰动不被事后计入探索可行集合。Icp/Kvco归一化矩阵因轴范围不同不必相等；同一理想环路增益乘积耦合由log弹性体现，调谐另依赖f0/Kvco。

## 输出与下一阶段读取

| 文件 | 内容 |
|---|---|
| `problem_resolved.json`、`run_manifest.json` | 评价前解析配置、问题/源码/模型指纹、预算与环境 |
| `physics_screening.json` | 严格必要条件、证书、启发式与域边界 |
| `m1_samples.csv` | 每个候选全部17参数、来源、单位、正式M1状态/指标、约束和成本 |
| `m1_samples.jsonl` | 完整候选信封、筛选、快速预测、完整原 MappingResult、差值、判断与Evidence ID |
| `feasible_candidates.json` | 探索可行候选全集，不含后续敏感度扰动 |
| `candidate_regions.json` | 代表点、连续区域建议、最紧约束和支撑Evidence IDs |
| `sensitivity.json` | 六轴矩阵、尺度、stencil、Evidence IDs、耦合摘要 |
| `cost_events.json` | 种子代数根、快速预测、正式M1和候选生成的实际事件 |
| `physics_context.json` | 公式、解析问题、区域、敏感度、证据SHA/IDs和能力边界 |
| `run_events.jsonl` | 候选在M1前写盘；Action/Observation/Decision、失败原因和累计成本 |
| `result.json`、`stage7_report.md` | 实际摘要、状态、成本和限制 |

Stage8使用 `load_physics_context(path)` 校验schema、自身digest、M1模型指纹和所有引用证据文件SHA；移动产物应连同所引用的相对路径文件一起移动。PhysicsContext版本为 `pll-physics-context-1.0`，不是 AllocationProposal，也不能直接送入原冻结 Stage6B checker。下一阶段应使用这里的参数和能力边界显式接入策略，不能把连续域探索假装成旧离散域的认证。

运行状态、成本、问题版本和指纹保存在产物中；预运行快照的cost为当时0，样本cost为累计值，最终报告为总计。`source_fingerprint` 标识本轮实现；`model_fingerprint` 标识所复用物理语义。`scientific_sha256` 排除运行耗时与路径，用于比较固定输入的采样/区域/敏感度摘要；wall/CPU另记，不要求字节相同。计时范围为解析后到筛选/采样/敏感度结束，不含Python启动和最后导出。
