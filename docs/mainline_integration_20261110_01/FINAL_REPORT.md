# F盘主线归并与分配策略研究基线验收

日期：2026-11-10。用户授权：将未进入F盘的Stage6B/6C推进归并并整理项目，在保留原理想流程的同时，把后续研究重心集中到现有可测/可分配规格下的Agent策略与验证反馈。

## 已完成的整理

- F:/LJP/概伦AI/PLL_allocation为统一开发/运行工作区；唯一正式入口仍是`python -m pll_allocation pipeline`。
- 已按来源/SHA归并Stage6B/C源码、配置、测试、工具、报告及Stage6A必要证据。5978文件新建或受保护替换，262份已有同内容文件保持；其中4份替换均已保存原字节备份。复制的轻量历史记录不冒充本次运行。
- 原M1 model、六参数分配/SLSQP、理想kernel/simulator/measure/verify、SystemSpec、Block Space及协议1.1保持。Stage6C显式可选，默认理想路径及M2=1/repair=0预算不变。
- 新Stage6C在F盘默认`build_stage6c`独立构建，身份检查通过；原理想DLL保持SHA `d3374c6da78b8e6ae7e6721492cc8e9d9e9267f65b1fff68b513de1f110d85e2`。
- README/架构/AGENTS/状态及D022已统一，旧根说明原字节存档。源码、必要测试证据与运行/构建/交接副本分开；旧目录、波形、失败和已验收ZIP原地保留，见EVIDENCE_INDEX.md。
- 发布`configs/stage6b/B1.json`和B2，为原冻结问题逐字节副本，避免从历史实验目录寻找正式研究输入。

完整来源见SOURCE_REUSE.json；精确转移计划、备份、Git状态及脚本见本项目`experiments/mainline_integration_20261110_01/`。没有reset/clean/stash/强制覆盖，也没有新LLM调用。

## 原理想流程的归并前后证据

| 新运行 | 完整M2 / native | 结果与比较 |
|---|---:|---|
| 归并前Analytical | 1 / 106 | BW 226403.93447205875 Hz，M2_PARTIAL_PASS |
| 归并前Random seed23及修复 | 2 / 220 | BW 713783.7917007345 FAIL → 新完整候选205385.56797859407 PASS |
| 归并后Analytical | 1 / 106 | 候选、完整M1/M2科学值、约束与成本计数逐字段精确一致 |
| 归并后Random seed23及修复 | 2 / 220 | 同上精确一致，修复仍真实生成新完整候选并复验 |
| Git干净导出Analytical | 1 / 106 | 全新构建后与归并前科学结果精确一致 |

比较保留测量duration/window、数值包络、失败、未知及真实调用计数；仅排除运行名称/候选运行ID/路径/源码清单/执行耗时等溯源字段。首次完整候选在首次TB前写盘、结构化反馈实际回传、trace与修复复验已核验。

严格周期PM、原微Hz频率认证仍UNKNOWN，完整SystemSpec认证false。此处BW通过不表示完整Verified JointBlockSpec。

## 联合扩展与独立导出

- F盘完整tests：478通过，0failure/error/skip。
- Stage6B B1 C：3候选槽、3新M2/318native，空cache真实重算；候选顺序、全部科学值和约束与旧研究一致。捕获37→33µs，第三候选捕获UNKNOWN保留，停止诊断并保留前一研究可行候选。旧六组研究中的C曾复用B首发cache，因此旧成本为2M2/212native；本次不伪称调用数相同。
- Stage6C J0 A：1新M2/120native，七项研究约束通过；候选、全部科学值、独立seed统计、双dt包络和判决与原study精确一致。不是新增优化增益实验。
- Git index tree `621eae37c512437b5d149d9bb358488098b5a959`无.git干净导出，四后端fresh MSVC构建、478tests及上表Analytical真实M2全部通过。5939份原导出文件SHA未变；9个Python进程的open/ctypes审计禁止从C盘Codex工作区和F盘母项目读取研究输入，违规0。证明运行及测试不依赖未提交的外部输入。

本次CLI验收共11完整M2/1196native：归并前3/326，归并后7/764，独立导出1/106。测试内TB/机制检查另计，不当作独立策略样本；构建CPU只记录启动进程，编译器子进程不混计。精确argv、returncode、stdout/stderr、wall/可用CPU及每次成本分别保存在各命令回执。

## 保留的失败及工程解释

归并后审计脚本三次过严假设分别涉及运行candidate_id、Stage6B v1.0无逐项evidence_path、父进程授权Git暂存；均保存原失败，并在新审查脚本中明确兼容，未改运行源码、测量合同或重跑成功仿真。

第一次Git导出发现core.autocrlf把部分非冻结源码导出为CRLF。原导出保留；新增.gitattributes稳定普通Python源码为LF，原冻结`-text`规则保持。第二次导出运行源码与F盘逐字节一致后才做独立验收。既有生成核的两处空白及末尾空行保持，避免无依据地改变源/构建身份。

## 后续研究重心

执行边界见`docs/research/ALLOCATION_STRATEGY_SCOPE.md`：

1. 固定现有模型、域与协议，核心研究用M2 BW/指定条件捕获、M1名义PM/内部调谐；Stage6C仅作可选固定环境。
2. 下一项优先补齐现有Policy边界中的真实LLM反馈修复和多指标Policy接入，保持Runner独立约束/TB/预算/判决。
3. 先真实首发与FAIL后修复验收，再做等预算策略对照及无反馈/标量/结构化反馈消融，比较首发/最终研究可行率、裕量、成本和失败。

本次没有实现新的Agent策略或调用真实LLM。正式真实LLM仍仅支持工具辅助首发，真实LLM反馈修复仍未实现；多指标当前只有原A/B/C。噪声/周期PM/全局稳定/器件精度未完成项不会因归并而升级。模型完善和SystemSpec扩展不再是上述策略研究的前置条件。

Git提交与master最终指针由后续本次FINAL_RECEIPT.json绑定；原有两份ZIP删除及无关未跟踪材料保留，不纳入此次提交。
