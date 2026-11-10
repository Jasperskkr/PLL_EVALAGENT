# 原始证据覆盖、归档与缺失边界

所有源码/配置与被携带证据保持原字节。压缩仅改变存储方式，不删掉必需模块或核心失败证据。新实验与原历史分开；本包不包含任何运行密钥。

|内容|包内实际位置与覆盖|
|---|---|
|Stage5结构化证据|repo/experiments/stage5：五场景、全部首发/修复proposal、M1/M2判决、request/measurement/summary/complete原生侧文件、LLM真实请求响应/失败、summary_02、成本与谱系。旧master补充在historical_support.tar.xz。|
|Stage6A结构化证据|repo/experiments/stage6a：analysis_01/02、全部冻结候选/计划、8次完整M2、repeat、研究联合重判、强制Stage5反例、原始成本/失败/审计/最终回执。|
|Stage6A波形|8次完整M2的852条native轨迹及额外2条capture重复，共854条原NPZ全部携带；包括E1真实FAIL与修复，未删失败。|
|Stage5波形|31次主策略M2的全部62条冷捕获轨迹；S3/random11首次FAIL与BW-pass/PM-fail修复的完整频响波形。其它密集频响/局部端口波形未全携带，但所有小文件结果/原生请求及原路径SHA可追溯并可按原配置重跑。|
|Stage6B补充|冻结独立源码、全部已复制结构化正式/复现结果、原始trace与调用/判决；携带正式10次M2的20条冷捕获轨迹，未全携带其完整频响波形。晚到变化另列stage6b_late_observation，不静默覆盖。|
|Stage1–4历史|原研究报告、来源SHA/公式/输入、有限网格、局部工程结果及当前测试闭包保留；早期全部密集raw/原TrackB整仓/旧项目全仓不携带。|
|本次新复现|reproduction_validation保存构建/命令/环境/测试/数值/完整判决和比较；新生成的大波形在本机validation_work/validation_portable_01，不重复塞包当第二批历史样本。|

## 无损历史支持归档

historical_support.tar.xz包含复制自原master的重复密集历史小文件，原包路径为source_variants/master_evidence。全部46306个成员逐SHA解读验证后才合并存储，原源文件从未删除。provenance/historical_storage_index.json保存每个成员的原路径、长度、SHA。使用scripts/expand_historical_support.py --out NEW安全展开并再次逐SHA验证。核心repo直接可读/可跑，不需先展开。

## 实际波形/图表计数

|类别|文件数|原字节数|
|---|---:|---:|
|Stage6A all formal/repeat waveforms|854|359636656|
|Stage5 captures and full seed11 counterexample|274|100157106|
|Stage6B supplemental captures|20|3767041|
|original visual evidence|2|427763|

## 真缺失与未认证

原工作树中两份历史ZIP已删除，本次保持该状态；对应文本/源码仍在。本包不携带Git对象库、外部LLM服务/密钥、原MATLAB运行环境、旧PDK/晶体管工程或所有原始大型RAW。缺环境或原波形时只能审查结构化结果/原报告，不能说已重跑它们。

当前没有严格周期PM/µHz精度认证数据，也没有Jitter/Power/RUR正式模型；这属于能力未建立，不是漏打一个文件。没有捕获失败/LLM修复证据时不得补写成功故事。

## 打包与复现期间保留的问题

首次6B物化检查发现仅剩identity而无DLL的旧native缓存会阻止默认重编译：只从新交接staging排除4份缓存identity并记录excluded_native_cache.json，未改源算法/任何原树。首次物化检查也发现6B打包脚本在另一工作树并发更新，前后SHA及晚到版本单独保留。

无Git归档环境是否通过所有历史测试须以reproduction_validation内实测为准。不能把位于现有Git仓库子目录的独立源码副本测试，通过上层.git发现后，误称完全不依赖Git的归档验收。该边界及实际失败会明确报告。

## 最终存储调整（保持证据原字节）

初次普通ZIP超出512000000字节；因此将早期实验结构化细节、raw测量JSON/CSV侧文件和部分大型保护清单合并到evidence_metadata.tar.xz。它们仍是包内证据，全部成员逐SHA解读校验后才从新staging散文件转为归档；原工作树不变。元数据补充树通过scripts/expand_evidence_metadata.py --out NEW恢复，也可--verify-only审查。provenance/evidence_metadata_storage_index.json给出全部原相对路径/长度/SHA；不把归档成员误写成直接散文件。

所有已携带NPZ保持直接路径（Stage6A854、Stage5 274、Stage6B20条），核心源码、配置、测试、Stage5/6A proposal/M1/M2最终判决、LLM记录及研究汇总保持直接路径。新复现本机大波形还包括validation_work/stage6a_strict_no_git_01；本包只保存其完整数值/判决与运行凭据，不重复计为历史新样本。
