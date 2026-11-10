# PLL 行为级联合规格分配与 Agent 策略研究

统一开发和运行目录：`F:/LJP/概伦AI/PLL_allocation`。唯一正式入口为 `python -m pll_allocation pipeline`。

当前研究重点是：**在固定模型、Block Space 和可测规格下，比较 Agent 的首次完整联合分配，以及有限预算内验证反馈对修复的价值。** 现有 M1/M2 作为冻结研究基础使用；进一步完善模型或规格不是策略研究前置条件。研究边界和下一步接口任务见 [分配策略研究方案](docs/research/ALLOCATION_STRATEGY_SCOPE.md)。

## 当前可运行过程

```text
冻结 SystemSpec / 拓扑 / Block Space
  → 完整 BlockSpec 首次分配并落盘
  → M1 物理预测与域检查
  → 理想行为 M2
  → 部分指标判决与结构化反馈
  → 可选确定性修复
  → 全量复验 / trace / 成本
```

模型为10 MHz参考、N=8、80 MHz输出的固定Integer-N CPPLL；六个自由变量为Icp/Rz/C1/C2/f0/Kvco。M1预测BW、连续PM、调谐点；M2独立测量BW并给指定初态下捕获/频率/控制诊断。原完整SystemSpec的周期PM及微Hz频率精度仍UNKNOWN，不签发完整Verified JointBlockSpec。

Stage6B在同一pipeline提供统一研究硬约束、A/B/C和确定性反馈搜索。Stage6C提供显式可选的固定噪声/非理想环境、独立多seed统计及复验。研究联合可行只针对已声明的支持指标，不升级完整认证。

## 运行

Windows x64、Python 3.12、NumPy/SciPy，原生后端需MSVC2022 C++17。已有构建加载前检查源与DLL身份；从源码新导出需按[复现说明](docs/stage6c/REPRODUCE.md)独立重建，禁止覆盖已有构建目录或手改identity。

```powershell
# 默认1次完整M2、0次反馈修复；输出目录必须全新
python -m pll_allocation pipeline --strategy analytical --out experiments/my_analytical_01

# 完整随机首发 → 可靠BW违例 → 确定性修复 → 完整复验
python -m pll_allocation pipeline --strategy random --seed 23 --m2-budget 2 --repair-budget 1 --out experiments/my_repair_01

# 原Stage6B研究问题和方法：A解析，B敏感度/SLSQP，C加确定性反馈
python -m pll_allocation pipeline --multispec configs/stage6b/B1.json --method C --out experiments/my_joint_01
```

可选Stage6C通过`--multispec configs/stage6c/joint_frozen_01/J0_ideal.json --method A`等启用。F盘新建的默认可选后端为`pll_allocation/verification/build_stage6c`；使用另一个新构建时显式设置`PLL_STAGE6C_BUILD_DIR`，不使用C盘旧DLL。Stage6C观察时长/频带/seed固定，不可用短捕获RMS代替噪声jitter。

真实LLM工具辅助首次候选已接入`--strategy llm_agent`，需要显式可用的外部服务配置。**真实LLM反馈修复以及多指标A/B/C中的LLM Policy接入尚未完成**；当前正式反馈修复由确定性算法执行。本次归并不调用真实LLM。

## 目录与维护边界

| 目录/文件 | 用途 |
|---|---|
| `pll_allocation/physics_mapping/` | 唯一正式M1，噪声为独立可选模块 |
| `pll_allocation/allocation/` | 解析/敏感度/SLSQP、Agent工具、确定性修复与联合约束 |
| `pll_allocation/verification/` | 唯一正式M2、测量/判决/构建身份及可选扩展 |
| `pll_allocation/pipeline.py` | Runner独立控制检查、预算、真实TB、复验及trace |
| `configs/` | 原冻结输入与版本化研究问题，Stage6B发布副本在`configs/stage6b/` |
| `tests/` | 维护的单元、数值、接口与回归测试 |
| `docs/research/` | 当前Agent策略研究方案 |
| `docs/stage5/`、`stage6a/`、`stage6b/`、`stage6c/` | 各阶段原任务、实现、证据范围和限制 |
| `experiments/<new>/` | 不覆盖的新运行及本地原始结果；与源码提交分开 |
| `docs/mainline_integration_20261110_01/` | 此次F盘归并计划、最终验收和证据索引 |

大型历史结果、完整波形和已验收压缩包保留原位置，见[证据索引](docs/mainline_integration_20261110_01/EVIDENCE_INDEX.md)。不递归搬走旧目录；`handoff_exports/`、`outputs/`、旧`track_b/`和`run/suite`只作历史/兼容，不作为当前策略研究入口。旧README及架构说明原字节保存在[prior_guides](docs/mainline_integration_20261110_01/prior_guides/README.md)。

原始任务保留在[PROJECT_CHARTER.md](PROJECT_CHARTER.md)，授权与范围更新见[docs/DECISIONS.md](docs/DECISIONS.md)，当前状态见[docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)。本次验收以[FINAL_REPORT.md](docs/mainline_integration_20261110_01/FINAL_REPORT.md)为准；旧报告中的“待合并/停止”是当时阶段状态。
