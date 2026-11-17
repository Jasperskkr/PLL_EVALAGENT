# 配置目录

这里保存运行输入和来源合同，不存放实验结果。正常使用先修改 `problems/` 的 SystemSpec、六轴范围，再选择 `agent/` 策略和 `verification/` 验证预算。正式入口仍是 `python -m pll_allocation pipeline`。

|路径|用途|使用建议|
|---|---|---|
|`problems/`|nominal、tight、infeasible_pm 三个 ResearchProblemV2 示例；规格、启用项、固定拓扑和六轴范围|复制后修改，合法输入不保证有解|
|`agent/`|确定性、LLM 物理工具策略、区域规划/搜索及预算|按所选 Policy 使用，不是六参数答案|
|`examples/spec_allocation.json`|八个多候选复现输入，继承默认策略配置|仅问题路径及预算覆盖，无实验输出；`tools/run_allocation_examples.py` 生成输入并调用正式 Pipeline|
|`providers/messages.json`|物理工具 Agent 的 Messages API 配置；4000 tokens、180s、thinking disabled|只记录环境变量名，凭据留在进程环境|
|`providers/messages_interactive.json`|原交互入口的独立 API 默认值；8000 tokens、60s|保留原预算差异，不与上一项合并|
|`verification/verify_only.json`、`feedback.json`|Handoff 后一次 M2，或有限反馈重分配|必须先取得 READY Handoff|
|`verification/m2_protocol.json`|正式理想行为 TB 的测量、数值收敛与判决协议|研究对照时固定；不是用户 Spec|
|`verification/phase_step_protocol.json`、`return_ratio_protocol.json`|可选相位阶跃、返回比实验协议|可选验证扩展，不代表完整 PM 已认证|
|`verification/noise_protocol.json`、`profiles/`|可选噪声/非理想验证协议及预声明环境|标准理想链不自动启用；profile 不是器件可实现性保证|
|`model/`|冻结 Block Space、方程、参考 SystemSpec 和 M1 实验合同|供模型/旧默认链和数值回归使用，不是一次成功设计的范围|
|`pipeline.json`|原默认 Pipeline 的模型/协议路径与策略设置|保留无新参数时的兼容行为；新连续域分配用 `--problem`|
|`baselines/`|确定性 M1、联合理想/非理想基线问题与对照设置|供基线/回归调用，不是历史运行结果|
|`provenance/`|原实现、物理绑定、配置迁移和可选 profile 的哈希清单|来源证据，不是实验指标，不手工伪造哈希|

六轴传入后端的单位依次为 A、Ohm、F、F、Hz、Hz/V。规格和变量域必须符合已有合同；当前反解要求启用正 BW 目标。修改问题不能扩大固定拓扑与测量能力。

`agent/spec_allocation.json` 是多候选端到端入口：三种 `mode`、K、总 M1/M2/LLM 预算、质量和去重阈值。`minimum_distance` 使用当前六轴各自的 log/linear 归一化坐标，`minimum_margin` 使用原 M1 judge 的最小归一化裕量。真实 API 默认禁用。原 `agent/deterministic.json`、`llm_physics.json` 及其单点输出合同保持兼容。

本次移除了十份完全重复的阶段配置、旧 study 计划/重复输入、过期 manifest、旧版返回比协议及重复依赖表，共17个文件；32份有效配置按职责迁移。迁移记录见 `provenance/config_paths.json`。冻结 JSON 内的历史 ID、来源字符串保留原义，不是仍需读取的旧文件路径。可选扩展构建需生成新身份，不能拿旧 DLL 的身份记录冒充新源码。

职责命名迁移新增 `provenance/naming_migration.json`，记录源码和夹具路径迁移及旧/新身份；原有配置迁移收据保留并可追溯衔接。schema/profile/protocol ID保留历史值，不能从阶段字样推断它仍是活动文件路径。
