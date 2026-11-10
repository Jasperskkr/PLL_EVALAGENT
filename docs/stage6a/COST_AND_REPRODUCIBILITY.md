# 计时、成本与复现

环境：Windows11、Python3.12.10、NumPy2.5.3、SciPy1.18.1、pytest9.2.0、MSVC19.37.32824/toolset14.37.32822。精确executable/platform/compiler/DLL/source SHA见`safety_01`与`verifier_setup_01`。未执行wheel安装或跨平台验收。

8次完整M2共852个完成原生仿真，23.257073原生秒；额外重复capture pair为2次、0.021965原生秒。研究合计854次、23.279037原生秒，无原生失败或真实LLM请求。Pipeline内部墙钟合计77.276179秒，8个进程墙钟84.347788秒；重复pair墙钟0.150673秒。原始native集成点、DLL/内核、每次实际参数/步长/完整波形/提取结果均在独立raw目录。

|计时对象|实测值|含义|
|---|---:|---|
|正式M1单点evaluate中位数|34.10ms|24次完整扫描/根求解，含指标，不含TB|
|已有廉价代数单点中位数|57.8µs|4725点raw_prediction；不可冒充正式M1.evaluate|
|M2双步长capture中位数墙钟|0.11949s|独立原生+提取/保存，含固定160µs轨迹|
|一个base BW sweep中位数墙钟|1.69704s|包含网格/自适应bracket，只是单个幅度/步长/窗口|
|四个BW sweep合计中位数墙钟|8.12230s|原协议base/half amplitude/half step/double window，需全部检查|
|完整Pipeline每候选内部墙钟|9.46–10.01s|cost.total_elapsed_s；加capture、M1前/后评价、判决、IO及合同检查|

组件实测见`cost_summary.json`与逐候选receipt/timing/native清单。计时器在进程内包装原函数，只调用一次，不改变输入/返回值/源码；通过runpy执行原`pll_allocation`模块和原CLI参数。完整M2始终由正式pipeline控制。posthoc M1嵌套在comparison时间中，不重复相加；单次BW sweep不能代替已收敛完整BW验证。未笼统宣称固定加速倍数。

较外层的instrumentation module墙钟为9.714–10.291秒/候选；包含解释器启动的进程墙钟为10.339–10.912秒/候选。三者计时起止不同，不混作同一成本。

analysis_01/02是M2前开发期两轮相同网格，均保留成本，不当独立样本；analysis_02是权威候选分析。`analysis_cost_ledger.json`记录两轮分析共96次完整M1、冻结proposal7次、repair父项重判及候选检查3次、Pipeline前/posthoc16次、root汇总10次、verifier重判8次，已记录非测试完整M1合计140次；廉价代数/条件根另列。测试内M1/native不完整插桩，因此单列进程墙钟，不虚构内部精确调用总数。三次native build合计15.216624秒；预回归27.405627进程秒；最终376项回归28.219163进程秒。

所有历史失败保留：首次compiler版本探针引号错误；后续cl /Bv无输入源返回预期D8003并保留完整版本；候选driver首次将canonical proposal SHA误作raw文件SHA，**在任何M2前**失败，修复后明确resume，首次本地preflight开销未单独计时，不能虚构时间；E1边界真实BW失败和修复谱系均保留。没有重跑挑结果、删除失败或放宽门限。

从隔离研究根目录运行，始终使用**不存在的新输出路径**；原始路径不能直接复跑覆盖：

```powershell
python -B experiments/stage6a/study.py --analyze experiments/stage6a/analysis_NEW
python -B -m pll_allocation pipeline --strategy analytical --proposal experiments/stage6a/frozen_01/E0_analytical_proposal.json --m2-budget 1 --repair-budget 0 --out experiments/stage6a/reproduction_NEW/E0_analytical
python -B -m pll_allocation pipeline --strategy analytical --proposal experiments/stage6a/repair_01/E1_BW_repair_proposal.json --m2-budget 1 --repair-budget 0 --out experiments/stage6a/reproduction_NEW/E1_BW_repair
python -B experiments/stage6a/collect.py --out experiments/stage6a/summary_NEW
python -B experiments/stage6a/audit.py --summary experiments/stage6a/summary_01 --out experiments/stage6a/audit_NEW
python -B -m pytest -q tests -p no:cacheprovider --basetemp=experiments/stage6a/finaltests_NEW/tmp --junitxml=experiments/stage6a/finaltests_NEW/tests.xml
```

pytest的basetemp父目录需先新建。全新checkout先按现有`verification/build_kernel.cmd`、`build_return_ratio.cmd`、`build_closed_loop.cmd`重建；这些命令拒绝覆盖已有build。精确实际运行命令与instrumentation见verifier脚本/receipts；已完成实验不应直接重启driver以覆盖原目录。所有完整候选已经在首次M2前冻结落盘，源身份可从原始dirty snapshot和frozen plan追溯。
