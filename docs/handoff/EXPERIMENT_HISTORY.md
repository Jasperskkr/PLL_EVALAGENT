# 实验发展与证据索引

所有数字除另注明均为历史实际记录，本次打包复现另外列在reproduction_validation。下列主要源码/实验路径相对repo；早期outputs名称为原工程证据路径，对应副本可能在historical_support.tar.xz的source_variants/master_evidence内。最终部分早期实验/raw侧文件存于evidence_metadata.tar.xz，可按存储索引原字节恢复；不是所有表中历史路径都在repo散文件中。原始绝对路径/工作树身份由provenance保存。本包保留报告、源配置、候选、真实请求/响应、判决和成本；完整波形覆盖范围见EVIDENCE_COVERAGE，不以历史报告替代缺失raw。

## 阶段1、1.5、Track A/B

|阶段|目标/新增能力|主要数据与结论|证据/未解决项|
|---|---|---|---|
|Stage1|从MATLAB物理关系提炼独立连续M1，统一SI/41语义|默认Vreq=.4V，UGF138176.441132Hz，BW222379.183493Hz，PM56.44269021°；4扰动点与11异常检查；162历史测试|docs/physics_mapping_stage1；outputs/physics_mapping_stage1_20261104_02；M2/LLM=0|
|Stage1.5|固定六轴Behavioral Block Space、版本/约束/公式合同|139点中134域内，124数学有效，44M1通过/80规格失败/15UNKNOWN；32点64事件步长对照；179测试|docs/stage1_5、outputs/block_space_v1_20261104_01；26点条件频率/控制一致，6点边界/不可调；未测BW/PM|
|Track A|物理逆向、±1%敏感度/SLSQP、工具型真实LLM|解析BW225k/PM72.2472°；最小归一化裕量名义.128854/解析.349375/优化.444944。两轮六目标×五策略结果一致；117正式M1/3116廉价预测每轮；219测试|docs/track_a/TRACK_A_REPORT_FINAL；outputs/track_a_*；重复轮次非独立样本；M2=0|
|Track B|独立边沿/Euler TB、BW激励、条件capture、协议1.1|真实native波形/步长/幅度/窗口校验；闭环BW可测，PM反演仅诊断；28历史独立测试|后续正式抽取到verification，tests/fixtures/verification与stage3a报告；完整原TrackB raw并未全打入|

Track A真实deepseek-v4-pro三次HTTP200选择解析→M1→提交，约51.296秒，候选等于解析；没有数值质量增量证据。原P3更早两次真实请求超时仍保留，不能被后来成功覆盖。原24组MATLAB/9600周期回归是继承参考数据，不是本次或Stage6A新执行MATLAB。

## 3A / 3A.1、4、4.2、4.1

- **3A工程集成**：正式pipeline贯通；五组主实验、六次完整M2共644 native。解析225000→226403.934472Hz，优化204356.651291→205385.567979Hz，均BW PASS而overall UNKNOWN。随机713783.791701Hz失败，经确定性repair/SLSQP变205385.567979Hz通过。真实LLM三动作后同Runner执行106 native。273正式回归；第一次47夹具错误记录保留，后续新目录通过。证据docs/stage3a及experiments/stage3a_*。
- **3A.1所有权/发布**：六算法正式归allocation，TrackA兼容；verification不依赖历史TrackB。283正式+28原TrackB历史测试，独立无DLL/历史目录副本重编译282通过。7完整M2/758 native，真实LLM先JSON失败，再同配置新目录成功。冻结提交47afcb7；精确发布/复验以repo内RELEASE和docs/stage3a1记录为准。
- **Stage4局部返回比**：原事件更新不变，加Series/Clamp相位端口与谐波诊断；3例局部交越收敛。v0.1低频DC失败保留，v0.2 pilot恢复状态；反向侧带转换近1，严格周期UGF/PM仍UNKNOWN。300正式+28历史TrackB测试；未新调用LLM。源码最终在7270f31 checkpoint保存。证据根UGF_PM_*与experiments/stage4_summary_20261105_05。
- **Stage4.2先于4.1实施**：只读Mapping Registry和域审计；1728有限网格、1512数学有效、212M1规格通过；10个未来M2见证点（7M1过/3失败）保留，未跑新M2/LLM。提交66c4ddb。证据docs/stage4_2、experiments/stage4_2/readiness_05。不能用212/1728当全域成功率。
- **Stage4.1固定候选验证**：C01–C08开发、C09/C10 holdout固定一次套件；10点局部频响与阶跃恢复支持映射。BW最大相对差.624%，Series/Clamp局部UGF最大.553%/.00792%，局部PM最大差.0487°/.0101°。原正式9UNKNOWN/1BW FAIL，完整PASS0。3632 native（含340pilot）/111.751原生秒；328正式+28历史TrackB，独立源码重建328通过。提交3a6a6e1→6f93a5f→c71798c→cd70cf4。证据docs/stage4_1与experiments/stage4_1。

随后master从acf49b8快进到cd70cf4，Stage3A.1/4/4.2/4.1都可达；不表示Stage5/6A已提交。归并后真实解析baseline重现相同BW/PM及UNKNOWN语义。

## Stage5：首发策略比较与修复

权威汇总 `experiments/stage5/summary_02`，scenario_results.csv、candidate_trace.jsonl保留；summary_01为原先版本不覆盖。源为master cd70cf4加未提交pipeline/scenarios适配，原六算法、内核、范围和Protocol1.1未变。

|场景|BW kHz / PM最小°|Analytical M1→M2 BW kHz|真实LLM|结论|
|---|---|---|---|---|
|S0|150–300 / 50|225→226.403934|3动作，同解析|BW通过，正式overall UNKNOWN|
|S1|180–230 / 60|205→206.058498|3动作，同解析|同上|
|S2|240–280 / 55|260→262.123340|HTTP200后JSON失败，无候选|LLM网络失败成本保留，无M2|
|S3|290–300 / 50|295→296.839212|3动作，同解析|BW通过，正式overall UNKNOWN|
|S4|150–300 / 73|M1相位上界不可行|预检跳过|5arm均无候选/无M2/无LLM|

Random seeds11/23/47每场景各一个合法未筛选首发，跨场景配对参数。M1 BW约415680.878/709216.566/325978.718Hz，PM约45.661369/40.936788/56.361690°；M2 BW416781.139/713783.792/326827.895Hz。12首发均M1失败且M2 BW FAIL；没有重抽、用解析替换或排掉失败点。Random与强物理基线的预算/策略差别应保留，不能从小样本推断LLM普遍优越。

全部PhaseA完成才修复12个真实BW FAIL，各增加1次完整M2后BW通过：9次REALLOCATE_WITH_BOUNDS（旧SLSQP），3次COORDINATED_SCALE_REPAIR。关键反例S3/random11：M1 BW294221.229Hz、PM45.661369°，M2 BW294644.315Hz通过但PM预测仍失败。Stage6A强制联合重判为FAIL，不能称12/12联合成功。

|成本/验收口径|历史实际值|
|---|---|
|主策略|19首发完整M2 +12修复=31；2078+1272=3350 native|
|主策略原生秒/进程墙钟|89.356s /501.744s；M1 posthoc单列|
|局部S0/S3频响+阶跃|490 native，开发错误及resume保留|
|主策略+局部|3840 native /102.702原生秒；576.121s主实验进程墙钟含保留失败|
|再加两个baseline|33完整M2 /4052native，不能与主策略样本混算|
|真实LLM|10请求：9有效动作/1JSON失败；新LLM反馈修复0；货币成本null|
|回归|接口与最终各351测试；独立最终297项场景/数据/谱系检查|
|完整SystemSpec认证|0，required PM和1µHz频率仍UNKNOWN|

输入/缓存tokens与输出usage保留于原始response及成本文件。S2标记REAL_LLM_NOT_EXECUTED指没有完成allocation，并不表示没发网络请求。局部cost字段错误、wrapper元数据错误和PhaseA helper bookkeeping变动都有原记录。

本包可以离线审查全部结构化结果，重跑确定性策略/修复；真实LLM历史token/动作只能追溯或显式重验保存proposal，新API调用需要外部服务且无法保证同答。Stage5全部密集波形是否携带以EVIDENCE_COVERAGE为准，不能把报告称为全raw重现。

## Stage6A：联合可行域、边界误差与条件捕获

来源独立 `codex/stage6a-multispec-feasibility` 工作树，HEAD仍cd70cf4；冻结/新增证据均未提交。正式M1/M2/分配算法不改；研究脚本study.py及tests/test_stage6a_joint.py新增。

M2前analysis_02权威：4725公式网格、4095调谐有效、E0公式可行602。E1粗网格0可行，但条件shape扫描53个非空区间，解析也找到可行点，不能报告不可行。578条件记录中E0非空369、E1非空53。E1仅50pF/2nF的相位上界足够；抽查的近相位下界shape点（x≈3.835869）受R下限限制，BW上限为203.845kHz；这是该点的条件上限，不是整个低x分支的上限，峰值及高shape见证点可行。f0自由时没有强制第三方调谐冲突。

|候选|M1 BW kHz|M1 PM °|M2 BW kHz|条件锁定µs|研究判决|
|---|---:|---:|---:|---:|---|
|E0 Analytical|225.000|72.247210|226.403934|33|联合研究可行|
|E0 SLSQP|204.356651|72.247210|205.385568|37|联合研究可行|
|E0不同电容对|225.000|56.442690|225.4724|16|联合研究可行|
|E1 Analytical|295.000|72.247210|298.165943|24|联合研究可行|
|E1 upper shape|299.500|70.043687|301.453585|35|可靠BW FAIL|
|E2低Kvco近上轨|225.000|72.247210|226.403934|38|40µs deadline通过|
|E2高Kvco中心|225.000|72.247210|226.403934|36|40µs deadline通过|
|E1确定性BW修复|293.0882|70.043687|294.926117|36|重查全部研究约束后可行|

E0沿用基准，E1 BW290–300k/PM≥70°，E2以E0加capture≤40µs。E0中心33µs复用作E2第三对照，不重复计新样本。首次7项中6研究可行，修复后共7/8；这是刻意见证点集合，不是统计成功率。

边界BW包络[301329.396069,301567.929345]Hz整体超过300k，排除了仅因包络交叠而UNKNOWN。修复包络[294812.358419,294976.918885]Hz在窄区间内部，PM仍70.043687°、Vreq.448926V。该反例证明局部约1%的M1/M2误差可改变紧规格判决；未给全域误差界。

E2同RC/增益乘积，同M1 BW/PM/UGF，但改变增益分摊和Vreq，得到33/36/38µs；近轨pair重跑逐字段一致。早期clamp/滑周不妨碍协议定义的终端持续锁定。所有E2通过，未执行捕获repair，不能宣称捕获反馈必要性或收益。

8完整M2=852 native/23.257073s；重复capture2次/.021965s，总854/23.279037s。pipeline内部77.276179s，8进程84.347788s，单候选内部约9.46–10.01s；正式M1中位34.10ms、cheap57.8µs、完整四BW sweep中位8.1223s。非测试已记录完整M1共140次，测试内部调用不完整插桩，不能合并猜测。

历史最终376测试通过；独立结果/报告复核、191项root审计、14709文件原目录保护记录保留。原正式判决7UNKNOWN/1BW FAIL，严格周期PM和µHz频率仍UNKNOWN，FULL_SYSTEMSPEC_CERTIFIED=0。证据入口 `docs/stage6a/FINAL_RECEIPT.json`、`experiments/stage6a/summary_01/*.json`、frozen_01、m2_01、repair_01、capture_repeat_01及各成本/receipt。

## 可复现与只能追溯的边界

可直接从本包运行：M1公式/域、解析/敏感度/SLSQP、Stage6A前置网格、全部保存proposal的确定性M2重验、窄研究约束重判、Stage5单场景确定性首发和repair。须Windows/native依赖，始终新目录。

只能历史追溯或有条件复现：真实LLM请求/外部服务；旧MATLAB runtime实机新执行；未全携带的早期海量raw；原Git未提交前的编辑时间顺序；跨平台/轮子安装。原始小文件、源SHA和已知缺失清单一起保留；不把无法新执行的部分写成已复现。

现场发现Stage6B已有实际B1/B2 A/B/C实验，另置source_variants/stage6b，历史404测试/10新增M2/3缓存/1060native。其结果不修改上面的Stage6A样本和结论，详见CURRENT_STATUS_AND_RESEARCH_GAPS。
