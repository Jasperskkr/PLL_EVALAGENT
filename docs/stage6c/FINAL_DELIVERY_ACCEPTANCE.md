# Stage 6C 最终验收补充

2026-11-10。此文件记录最终观察到的验收结果，补充并取代 `DELIVERY_ACCEPTANCE.md` 末尾“archive pending”的历史状态。此前报告、失败、trace绑定的文件不改写；研究分析以 `FINAL_RESEARCH_REPORT.md` 为准。用户要求的研究扩展已接入原正式pipeline；没有自动提交或合并master。

## 实际验收结果

第二版候选包：SHA256 `a2d84640ac8a3c67d369831133ff8b2e270cdb7d3b573a00d489cf522730ca31`，5,811,722,045 bytes，34,350个manifest文件。独立验收通过所有文件SHA/CRC、26条trace哈希链、21,908个证据/trace引用；另逐项核对21,796条artifact的SHA/bytes与manifest完全一致。

在全新 `F:/LJP/PLL_Stage6C_results/export_acceptance_02/extracted/repo` 中实际执行：

1. 从源码重建原3后端及Stage6C可选后端，全部成功，未复制DLL。
2. 全部478项测试通过，无failure/error/skip；pytest进程wall36.4801s。原候选包01的386通过/92失败及补齐输入的修正仍保留，见 `PACKAGING_CORRECTION.md`。
3. 新构建身份重新冻结plan，使用全新空cache，经唯一正式 `python -m pll_allocation pipeline` 运行 J0 A 完整复现实验。
4. 参数、全部M1/M2指标、七项联合约束、每seed统计、两个dt的包络、判决及成本计数与包内保存结果精确一致。结束后18,784个原repo文件逐份SHA不变。

复现新增成本：1个完整M2、120 native、290,090,329积分点、18.9016107 native elapsed秒、44.3634997进程墙钟秒。Windows GetProcessTimes独立测得该pipeline进程CPU40.0000秒（kernel3.046875+user36.953125）。native DLL在此进程内；该CPU只属于这次新复现，不能倒填正式六组CPU。cmd构建回执中的CPU仅shell本身，不代表子编译器总CPU。

独立验收原回执：`experiments/stage6c/zip_export_acceptance_01/FINAL_RECEIPT.json`。39份小证据含全部命令/stdout/stderr、JUnit、四个build identity、新plan3份JSON、编译器与CPU范围说明，均有 `ORIGIN_MANIFEST.json` 的原路径/SHA。完整新run保存在 `F:/LJP/PLL_Stage6C_results/export_acceptance_02/J0_ideal_A_reproduction_01`，最终包纳入 `extra/reproduction/`。重建与复现不是额外优化样本。

## 最终包与 trace 的含义

最终包在通过验收的候选02基础上加入本补充、成功/失败验收证据、最终保护清单及复现原始run。运行源码、测试、冻结问题/噪声/非理想/协议保持；仅打包README/文档和新增证据有变化。最终包的逐文件校验、trace跨绑定和与已验收候选的运行源码等价检查由独立verifier另出sidecar，准确包SHA以同目录PACKAGING_RECEIPT及最终验收回执为准，不宣称本文件包含自身后续验收。

`experiments/stage6c/trace_final_02/artifact_trace.jsonl` 覆盖最终可落盘证据，包括原失败与本次复现的真实事件。第一版trace的21,796个引用维持原字节有效；新trace含第一版trace及新增证据。外层排序是artifact检索顺序，原事件的实际时间和成本仍在payload中；不冒充完整交互对话录制。

最终保护清单见 `experiments/stage6c/protection_final_03`；对原Stage6B170份源码仍仅5个显式可选接口改变，165份不变。相对于只读Stage6B的本阶段源码patch、文件变更表与SHA一并提交。旧Stage6B HEAD/Git状态及170份源字节保护见protection_final_01的独立回执。

## 研究结论保持边界

六组首发与最终均满足本轮研究约束；C把两个环境的条件捕获33/32→29µs、最小裕量.15/.175→.204120164。Jitter区间重叠，100ps约束未影响本轮SLSQP选型，不能宣称jitter或一般可行率优势。E0原六组新跑10完整M2/1060native精确回归；Stage6A八点是历史证据核验与新M1判读，未新跑全八点M2。

Implemented、Numerically Verified、Behaviorally Supported各有指定证据；严格周期PM/Floquet、全局稳定性、CP门控与M1绝对等效、器件准确度和完整原SystemSpec仍Unsupported/UNKNOWN。真实LLM调用0。最终打包验收通过不提升这些物理结论。
