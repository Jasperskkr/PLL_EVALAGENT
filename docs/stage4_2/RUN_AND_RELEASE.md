# Stage4.2 执行、保护与独立提交

正式输入基线：`47afcb72011636e838b03d81cf91bcec49744a77`。本阶段分支`codex/stage4-2-readiness`。当前工作区另含Stage4研究成果，不纳入本阶段生产源码提交。既存两个ZIP删除和历史未跟踪输出保持原状；不执行reset/clean/stash，不改Track B子仓库。

## 实际命令和证据

```powershell
python tools/audit_stage4_2.py --snapshot yes --out docs/stage4_2/pre_audit
python tools/run_stage4_2.py --out experiments/stage4_2/readiness_01
python tools/run_stage4_2.py --out experiments/stage4_2/readiness_02
python tools/run_stage4_2.py --out experiments/stage4_2/readiness_03
python tools/run_stage4_2.py --out experiments/stage4_2/readiness_04
python tools/run_stage4_2.py --out experiments/stage4_2/readiness_05
python -m pytest tests -q -p no:cacheprovider --junitxml=experiments/stage4_2/finaltests_03/tests.xml
python -m pll_allocation.physics_mapping.registry --registry docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json --metric BW_Hz --route
python tools/release_stage4_2.py --export experiments/stage4_2/commitcheck_02
# 在导出source目录：build_kernel.cmd；pytest tests；run_stage4_2.py --out experiments/stage4_2/reproduction_01
python tools/audit_stage4_2.py --before docs/stage4_2/pre_audit --out docs/stage4_2/final_audit_02
```

所有实验/测试输出目录均新建、拒绝覆盖；命令首次生成的两份JSON在判决适配问题发现后完整移入readiness_01，与该轮后处理失败记录一起保留；当前交付JSON由最终readiness_05复制，历史运行不修改。重复轮次不算独立统计样本。当前代码运行还保留脚本和Registry适配器的原字节快照。

|记录|结果|解释|
|---|---|---|
|pretests_01|300 passed，21.94s|原主线283+当前未提交Stage4的17项|
|finaltests_01|311 passed，21.17s|新增研究测试初版11项|
|finaltests_02|312 passed，20.17s|新增换行等价边界测试|
|finaltests_03|313 passed，21.62s|再补规范单位拒绝，最终完整回归|
|readiness_01|数值扫描通过，候选判决适配错误|漏传hash/units/protocols，原judge正确UNKNOWN；失败摘要保留|
|readiness_02|数值/候选通过|完整MappingResult传递修复|
|readiness_03|数值/候选通过|增加原字节+仅换行归一化哈希|
|readiness_04|数值/候选通过|补干净导出证据回退/源码快照|
|readiness_05|最终权威；1728网格、1512有效、212预测规格通过|补规范单位拒绝，物理结果不变|
|commitcheck_01|295 passed、1 failed，28.89s|Git archive继承CRLF转换，旧字节哈希夹具失败；未改测试|
|commitcheck_02|296 passed，26.71s|显式禁用导出换行转换，原核重编译；不含Stage4实现/测试|
|commitcheck_02复现实验|数值和10点指标/判决完全相同|无历史outputs，使用本阶段来源快照；domain_scan.csv逐字节一致|

每轮研究成本94次正式M1、1512次cheap预测、1512次独立数值多项式参考、1738次显式域检查；主工作区五轮合计470/7560/7560/8690。本阶段研究程序M2=0、LLM=0。测试内部原生调用未全部逐次持久化，不伪报总精确TB调用数；JUnit墙钟与保存的测试调用另计，不把它们当新物理实验。

导出复现另增加一轮94/1512/1512/1738，全部研究运行总计564/9072/9072/10428；不是六个统计独立样本。失败的commitcheck_01在测试失败后即停止，未运行研究复现。复现输入/摘要/版本哈希/逐项相等检查保存于commitcheck_02根目录，临时源码副本和编译缓存不进入提交。

## 冻结与保护方法

开始清单含31,163个既有文件、3,088,192,384字节（跳过.git、缓存和测试tmp），记录路径/大小/SHA；包括Stage4原始波形、DLL和审查包。重要脏源码先原字节备份；此前存在的删除不“恢复”，因为它们不属于本阶段变更。

结束时逐项复核，只允许`docs/DECISIONS.md`和`docs/PROJECT_STATUS.md`追加Stage4.2记录；旧字节必须是新文件前缀。Stage4代码、M1、allocation、原M2、SystemSpec、Block Space、Protocol1.1、历史数据/已有测试与子仓库不变。具体计数/差异以`final_audit_01/protection.json`为准。

Registry本身不作为正式配置替代；14个来源路径同时绑定原字节SHA和仅CRLF→LF归一化SHA。冻结配置在当前工作区为CRLF、Git blob为LF，这一已知差异显式记录；归一化后有其他内容变化仍拒绝。原kernel与build identity继续采用其原机制，不受Registry字节规则影响。

## 提交边界与重现

本阶段独立Commit从原Stage3A.1父Commit提交：新Registry适配模块/研究工具/新增测试、六份交付、有限实验数据/来源快照/哈希/测试与保护记录，以及两份阶段日志中的**Stage4.2增量**。两份日志的index由HEAD原文加本阶段追加段构造，工作区保留Stage4未提交原段；不会把Stage4改动随`git add`一起提交。不使用`git add -A`。

提交前用一次性无Git源码导出检查Stage3A.1+本阶段文件，重编译原内核并执行回归/新实验重现；它是测试夹具，不是新工程或长期框架。实际当前主工作区313项与干净基线导出296项均通过，差别为未提交Stage4的17项。详见commitcheck_02/verification.json和两个JUnit记录。导出不是新Git仓库。

新运行示例`python tools/run_stage4_2.py --out experiments/stage4_2/my_new_run`，目录必须不存在。历史Stage4原目录不在干净导出时，工具只读取本阶段提交的小型证据快照和历史候选hash索引，不需原始波形/DLL；这些是历史复用，不冒充新M2。本轮未做wheel安装或跨平台验收，旧源引用测试仍依赖本机已存在的MATLAB来源文件，不能声称跨机器完全自包含。

Commit hash在完成提交后的回执和最终汇报中提供，避免把自身hash写进自身。所有改动停留在本阶段范围，提交后停止等待Leader，不推进Stage4.1。
