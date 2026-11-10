# Stage 3A 集成审计与实施方案

日期：2026-11-04（Asia/Shanghai）。此文先于生产代码修改落盘。范围依据用户 Stage 3A 指令；不重设模型、范围、SystemSpec 或测量协议。

## 源码事实与冲突

|模块|真实实现|集成处理|
|---|---|---|
|原 v1 主线|contracts / policies / runner / behavioral；周期电荷 + 精确 RC；旧 80/84MHz 协议|保留兼容入口与全部回归，不用于认证 Stage1.5 的 BW/PM|
|Stage1|physics_mapping.model / experiment；SI 语义、连续 M1 与原 judge|直接复用，不修改公式|
|Stage1.5|block_space.contracts；正式 BLOCK_SPACE_MODEL_V1、41变量语义、17参数、六自由变量|唯一正式模型取 configs；保留 draft 元数据；不得变域|
|Track A|allocate / physics / agent / repair / core；解析逆向、SLSQP、敏感度、MessagesPolicy、完整 Proposal|原位复用数值/Agent代码，增加 allocation 薄边界，不复制成第二套算法|
|Track B|verify / simulator / measure / experiments / run_suite / kernel.cpp|提取验证器及其调用闭包至 verification，改包内导入和资源定位；不搬整个研发项目|

Track B 与父项目各有 .git；父 HEAD=e5bf67a032831d431819bce24177930179e431fc，分支 track-a/physics-guided-allocation；Track B HEAD=dc661f6f7694562444438410f39190571b51a398，独立分支。Track B 未跟踪于父项目，不能当成父仓库正式可安装模块。父树已有两份历史ZIP删除和新增ZIP/Track B；这是本轮开始前状态，保留。原始 git status 和文件 SHA 随阶段审计保存。

重复包括 Track B baseline 模型/注册表快照，以及两条线各自的 M1 后处理。正式运行只读 configs 的模型，Track B 快照保留为历史；后处理 M1 成本另计。旧 v1 参数/测量合同与 Stage1.5 不能互换。Track B 脚本使用 experiments、simulator 等顶层模块名和 sys.path 插入，存在导入串线风险，正式包使用相对导入。

Track B verify 实际调用捕获双步长与四组频响扫描，无 mock；测量后才调用 M1 作对照。1.0 / 1.1 存在捕获相位定义和BW二分宽度差异；正式选择既有 1.1。原 comparison_after_measurement 读取1.0中的三项收敛门限，它们与1.1相同；提取后显式传完整1.1文档，记录该适配并检查数值不变。

## 不可混淆的语义

- 官方 SystemSpec 来自 Stage1.5 model.experiment.system_spec（10MHz×8，BW 150–300kHz，PM≥50°，频率等式容差1e-6Hz）。独立文件为同内容视图，通过 hash 绑定，不创建另一套目标。
- M1_PASS 仅对应既有 M1_SPEC_PASS。M2部分通过表示至少一个必需指标PASS、无必需指标FAIL且仍有UNKNOWN；原整体UNKNOWN继续保存。它不代表完整行为通过。
- BW采用既有连续 divided-phase 观测；边沿专用观测等价性未知。PM、UGF与频率微Hz精度继续UNKNOWN；捕获是初态/窗口条件证据。
- Track A的反馈合同需要 allocation-feedback-1.0、参数hash、source=M2、kind及FAIL/UNKNOWN；Track B输出列表缺少该信封。增加带候选/协议/指标状态绑定的适配器，并实际调用原 interpret_feedback；不增加学习算法，不以未知PM驱动盲目修复。
- 首次提交在任何本次M2前落盘；导入历史Proposal显式标为既有候选复验，LLM调用为0，不能算新LLM首发。

## 最小架构及实施顺序

1. 保存本方案、来源SHA、初始Git状态与保护清单，跑原 tests 和 track_b/tests 基线。
2. 保留 physics_mapping、block_space 和 track_a 算法原文件；新增 allocation 接口、verification 正式包、pipeline Runner。唯一推荐入口增加 `python -m pll_allocation pipeline`；原 run/suite 为旧v1兼容入口。
3. configs 保留正式模型/方程注册表；新增统一流程配置、同内容SystemSpec视图和逐字节1.1协议。精确hash锁定模型/版本/协议/候选，拒绝静默混用。
4. 从Track B提取5个Python调用闭包、kernel.cpp与构建入口；原始轨迹留原处；新轨迹写 experiments 下独立raw目录。包运行不读取track_b目录及其build。复用DLL记录二进制SHA及源文件SHA，提供本地重建入口。
5. Runner独立检查、落盘、M1、完整M2、反馈回传和预算。支持解析、优化和真实LLM；可通过显式修复预算复用已有确定性repair；默认只首发+反馈接收。
6. 记录每次完整运行的输入、模型/协议/代码/依赖、首次候选、M1/M2、偏差、Agent日志、成功及失败成本。拒绝输出覆盖。保留所有失败实验。
7. 完整回归、两策略实际M2、历史Track A候选M1精确和M2容差回归、真实LLM调用（若服务失败如实记）、各状态及反馈/版本拒绝测试；落盘验收报告后停止等待Leader。

## 依赖与验收边界

本机 Python3.12.10、NumPy2.5.3、SciPy1.18.1、pytest9.2.0。旧pyproject未声明Track A/B依赖，需加入集成extra与包资源；MSVC C++17原生DLL仅Windows运行，缺后端必须UNKNOWN。真实LLM使用现有环境变量，不导出凭据。没有 ngspice/PDK/MOS/sizing 运行依赖。

历史 outputs、track_b/outputs、data/verification_reference 和各阶段报告均保留；Track B嵌套仓库本轮不删除、不合并、不改写。最终清单列可归档内容和仍不能删除的证据。审计只声明实际阅读的运行闭包，不将文件指纹视为所有历史源码已逐行审查。
