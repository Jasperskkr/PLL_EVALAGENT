# PLL_AGENT 架构与回归审计报告

审计日期：2026-09-24
执行环境：项目 `.venv`，Python 3.13.10

## 结论

本轮完成了 pipeline 拆分后的止血与回归闭环。V1.0、V1.5 主链的数值结论保持不变，
核心科学 artifact 已有逐字节 SHA-256 回归测试。当前 `v1/pipeline.py` 只保留兼容导出，
不再承载业务逻辑。

## 已修复

- `backends/__init__.py` 只导出 protocol，不再隐式加载具体实现；所有模块均可作为冷启动入口导入。
- 补齐 `api/model/evaluation/schema/graph/allocation/verification/backends/workflow` 层依赖守卫。
- `evaluation` 只保留测量事实；BlockSpec constraint judgment 移到 `verification`。
- backend id、judgment id 拼错时立即失败，不再静默回退。
- allocation backend、verification backend、BlockSpec judgment 支持注册扩展。
- `system_evaluation` 不再因为传入 Block context 而静默改变数据形状。
- SystemTB `trajectory_envelope` 与 BlockTB `characterization_window` 明确分名；旧 `context` 暂作兼容别名。
- 轨迹包络增加 rail 与初始条件/收敛方向信息，避免被误读为 VCO 全能力范围。
- `loop_bandwidth_hz` 明确标注为历史兼容名；新名称为
  `effective_noise_shaping_bandwidth_hz`，它不是闭环提取或晶体管级物理带宽。
- 统一 JSON、严格 evidence JSON、内容 digest 与文件 SHA-256；NaN/Infinity 不能进入科学证据。
- 删除多份 digest/file-hash/JSON/CSV helper，避免不同 artifact 的 hash 规则漂移。
- evidence 不再包含临时目录绝对路径；两套不同输出目录生成的关键 V1.5 JSON 逐字节一致。
- matplotlib 输出与科学 evidence 解耦；V1.0 plot 默认关闭，必须显式开启。
- SystemSpec、VCORequirement、VCOParams、CPPLLParams 增加输入不变量校验。
- `*_ref` 在判定前统一解析，错误信息包含可用路径；空约束、重复 id、错误运算方向会立即失败。
- Python 环境固定为 3.13，并补齐可安装的 `pyproject.toml`。

## 对 KNOWN_ISSUES 中 Kvco 诊断的校正

Kvco 并非没有进入反馈环。`relative_frequency_error` 由 `VCOParams.frequency_hz(vctrl)`
计算，因此局部误差对 Vctrl 的斜率包含 Kvco；在相同初始频率下改变 Kvco，第二周期误差和
锁定时间都会改变。

真正需要止血的是命名：原 `loop_bandwidth_hz` 是用于 PN 积分的启发式噪声整形参数，
不能作为提取出的物理闭环带宽。本轮保留数值模型，修正了输出语义并增加回归测试；没有在
架构重构中混入未经重新标定的物理内核改动。

## 回归基线

- pytest：98 passed
- V1.0：PN anchor boundary `-116.358121 dBc/Hz`
- V1.0：required measured VCO PN `-113.511151 dBc/Hz`
- V1.0：selected candidate `candidate_low_noise`，final SystemTB PASS
- V1.5：234 sampled / 221 Block feasible / 51 SystemTB PASS / 51 jointly feasible
- V1.5：9 mapped slices / 9 unmapped slices / 8 off-grid holdouts
- V1.5：PN holdout MAE `0.0006121993064880371 dB`
- V1.5：formal measured Kvco window `1.54–1.84 GHz/V`
- V1.5：formal 2-D BlockSpec PASS

## 仍然成立的边界

- 当前模型是确定性行为模型，不是晶体管级 signoff，也不是物理 CPPLL 参数提取器。
- V1.5 formal BlockSpec 只对当前 synthetic model 和 frozen context 成立。
- Spectre/SPICE/MATLAB backend 的注册缝已经具备，但真实外部工具异常、超时和许可证失败
  需要在接入具体 backend 时定义专用异常与集成测试。
- `context` 和 `loop_bandwidth_hz` 是兼容字段；后续发布 schema v2 时可正式移除。

## 后续扩展规则

- 换数值模型：改 `v1/model/` 或新增 backend，不向 `pipeline.py` 写业务逻辑。
- 新分配算法：放入 `v1/allocation/`，复用 verification service 和严格 evidence helper。
- 新 Block：新增 definition、realizer、measurement backend、judgment strategy，并注册；
  不修改 workflow 核心顺序。
- 改执行顺序：只在真正改变阶段关系时修改 `v1/workflow/service.py`。
- 任何数值或 artifact schema 改动，都必须先更新说明，再显式更新 runner regression hash。
