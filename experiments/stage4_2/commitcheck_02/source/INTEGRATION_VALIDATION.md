# Stage 3A.1 独立验收与发布记录

2026-11-04，本报告记录本轮真实执行。修改前已落盘结构审计/方案、Git状态和295份重要文件备份；ZIP SHA256=`dc7e94c45072f4b12478c082d15e0950fabc46fac0ae5d4aa91cce8f5c4b4617`，本地保留不入发布包。19,966份既有文件纳入保护清单。冻结公式、SystemSpec、六参数域、协议1.1及历史输出不改。

## 回归

|本轮执行|tests|PASS|FAIL|ERROR|SKIP|experiments/下的报告|
|---|---:|---:|---:|---:|---:|---|
|迁移前tests+原Track B|273|273|0|0|0|stage3a1_pretests_20261104_01/tests.xml|
|迁移后首轮|273|272|1|0|0|stage3a1_postmigration_tests_20261104_01/tests.xml|
|修复导入后的Verification|28|28|0|0|0|stage3a1_verificationtests_20261104_01/tests.xml|
|正式套件第一轮，含9项迁移测试|282|282|0|0|0|stage3a1_finaltests_20261104_01/tests.xml|
|原Track B独立测试|28|28|0|0|0|stage3a1_original_trackb_tests_20261104_01/tests.xml|
|无Track B/outputs/DLL缓存的导出，重新编译|282|282|0|0|0|stage3a1_isolated_20261104_01/tests.xml|
|最终正式套件，含10项迁移测试|283|283|0|0|0|stage3a1_finaltests_20261104_02/tests.xml|

283=原219+Stage3A 26+迁入Track B 28+本阶段10。单独原Track B 28属于重复验证。最终套件22.43s；隔离282项22.72s。发布后包回归的实际结果另记RELEASE_MANIFEST，不提前计为完成。

保留失败：迁移首轮`protocol`导入遮蔽本地v1.0回归夹具，删除该导入后原断言/阈值通过；正式配置始终为1.1。新增超时测试首次9 PASS/1 FAIL，原因是新测试写LLM_TOTAL_TIMEOUT而既有实现返回LLM_TOTAL_PROCESS_TIMEOUT；按实际异常和状态修正新测试，生产Agent未改。未删除失败或放宽数值门限。

实际命令（各basetemp父目录先新建）：

```powershell
python -m pytest -q tests track_b/tests -p no:cacheprovider --basetemp=experiments/stage3a1_pretests_20261104_01/tmp --junitxml=experiments/stage3a1_pretests_20261104_01/tests.xml
python -m pytest -q tests -p no:cacheprovider --basetemp=experiments/stage3a1_finaltests_20261104_02/tmp --junitxml=experiments/stage3a1_finaltests_20261104_02/tests.xml
python -m pytest -q track_b/tests -p no:cacheprovider --basetemp=experiments/stage3a1_original_trackb_tests_20261104_01/tmp --junitxml=experiments/stage3a1_original_trackb_tests_20261104_01/tests.xml
python tools/isolate_stage3a1.py --out experiments/stage3a1_isolated_20261104_01
python tools/validate_stage3a1.py --out experiments/stage3a1_acceptance_20261104_01
python -m pll_allocation pipeline --strategy llm_agent --out experiments/stage3a1_llm_retry_20261104_01
```

## M1/M2真实新实验

迁移前已新调用四策略保存M1_baseline.json。迁移后相同seed23/冻结配置，四组候选全部参数及完整M1 assessment逐字段相同。M2与Stage3A小型正式参考的metrics、constraints、overall_status也逐字段相同。计时、ID、路径不参与数值比较；脚本相对/绝对1e-12，实际四组exact=true，非验收门限修改。

|策略|M1 BW Hz|M1 PM °|M1 UGF Hz|M1 Vctrl V|M2 BW Hz|BW偏差|BW/整体|
|---|---:|---:|---:|---:|---:|---:|---|
|Nominal|222379.1834929631|56.44269021253223|138176.44113161|0.4|222853.09255111087|+0.213109%|PASS/UNKNOWN|
|Analytical|225000.0000001216|72.24720983805331|167166.52042501146|0.6|226403.93447205875|+0.623971%|PASS/UNKNOWN|
|Optimization|204356.65129092903|72.24720983799878|151829.31836725006|0.6|205385.56797859407|+0.503491%|PASS/UNKNOWN|
|Random seed23|709216.5657616763|40.93678773935426|433690.96121378196|0.4635157032269488|713783.7917007345|+0.643982%|FAIL/FAIL|

M2 PM/UGF全部UNKNOWN；频率虽有尾窗口实测值，冻结1e-6 Hz精度未认证，约束UNKNOWN。前三组M2_PARTIAL_PASS，随机M2_FAIL，不能以M1或捕获结果补齐完整PASS。旧Track A正式解析Proposal原JSON夹具的M1全字段不变，且同候选真实M2数值相同。

原确定性反馈修复新运行：FIRST_SHOT随机BW713783.7917007345 FAIL → 原repair/SLSQP完整新候选 → FEEDBACK_REPAIR BW205385.56797859407 PASS，整体UNKNOWN。反馈实际进入Agent层，回执RECEIVED_BY_ALLOCATION_AGENT，无新增学习算法。

真实LLM首次HTTP200、达到1500 token后JSONDecodeError，无候选、M1/M2均0，28.477s/1次网络请求。新目录同配置重试3次HTTP200，deepseek-v4-pro执行SolveInverseAllocation → EvaluateM1 → SubmitCandidateForM2，Runner随后106次原生仿真，M1/M2与解析相同，41.244s、M2_PARTIAL_PASS。真实LLM修复仍未实现；未用mock替代失败；提示词/工具/transport/模型配置未为重试修改。

主验收四组+修复+LLM成功共7次完整M2、758次原生仿真；含LLM失败共4次真实网络请求，总墙钟133.522s。测试中的额外仿真另计；货币成本无账单保存null。首次候选均在TB前落盘，工具trace、反馈、失败成本保留。

## 结构、构建与保护

六模块逐字节迁移，来源SHA/语义/域见migration_manifest.json。AST审计29份正式源码无旧Track A/B导入，Verification不依赖allocation；测量AST与原Track B相同，kernel/协议逐字节相同。运行时import blocker拒绝旧路径仍生成Proposal、执行M1及真实原生M2短仿真。独立导出205份源/配置/必要小参考，无track_b/outputs/现成DLL，MSVC2022 x64重新编译后282项通过；跨平台NOT_VERIFIED。

原构建脚本可能先覆盖DLL再因identity已存在失败；现拒绝已有输出目录。数值核未改，加载继续校验源码/DLL SHA，无伪造后备。新DLL SHA及编译日志已存isolation.json/native_build.log。MSVC二进制含构建元数据，不要求DLL字节重现；源Hash、运行回归、指标等价分别检查。

发布前发现原Git把部分参考数据换行归一化，而旧测试按原字节SHA核验。新增.gitattributes限定data、fixtures及迁移实现保留原字节，提交既有快照的真实字节；工作区数据SHA不变，非数值/协议修改。包从最终Git对象读取、逐文件SHA，避免仅当前工作区通过。

最终保护审计见docs/stage3a1/final_audit_01/audit.json，检查19,966既有文件，授权变更限定清单，Track B HEAD/status及历史记录不变。两份预先删除ZIP与三个外部审查ZIP保持原状且不提交；raw/备份留本地。只按显式allowlist暂存，不reset/clean。

## 发布与边界

代码Commit冻结后，tools/release_stage3a1.py由该Git对象生成根目录RELEASE_MANIFEST.json、stage3a1_review_bundle.zip和外部SHA256文件。manifest/ZIP为外部资产，避免Commit自引用；包内内容与Git对象逐字节相同，输入Hash、测试、环境和缺口绑定同一Commit。最终Commit/包回归读取发布manifest。

尚未验收：真实LLM反馈修复、多seed公平统计、PM/UGF/微Hz认证、噪声/抖动/功耗与域外可信度、跨平台、wheel安装。本阶段不继续扩展。
