# BLOCK_SPACE_READINESS_REPORT

## WHAT：最终得到了怎样的 Block Space Model？

得到可加载的 Behavioral Block Space Model v1，位于 `configs/BLOCK_SPACE_MODEL_V1.json`。它包含17个实际输入/假设、41项语义目录、固定拓扑、原样保留的Stage1实验配置、7项可执行联合关系、版本/来源、逐指标可信度和校准记录合同。Declared Domain、Model Validity、M1 SystemSpec Feasible Region分开判定。已完成本阶段，等待技术Leader审阅；未启动Stage2。

## HOW：变量范围如何建立，系统指标如何映射？

1. 当前可分配参数只有Icp、Rz、C1、C2、f0、Kvco。Icp=50–200µA、Rz=2–8kΩ、C1∈{50,100,200}pF、C2∈{0.5,1,2}nF、f0=60–76MHz、Kvco=10–40MHz/V，完整继承Stage1的人工行为范围，未扩域。PFD非理想项、N、参考频率、电压上下限固定。
2. 每个轴保存单位、上下界/choices、nominal、来源、选择理由、角色、适用条件和是否参与计算。范围不是已验证的器件能力。新版loader不能把新契约硬塞进旧v1 Runner；新实验Runner可以直接调用load_model/make_candidate/check_parameters/forward，旧入口保持不变。
3. 显著耦合为Icp×Kvco/N、Rz/C1/C2的零极点与最大PM、f0/Kvco/Vctrl的内部调谐限制。CP非理想与静态偏移存在关系，但当前无可信模型，明确UNSUPPORTED。
4. 系统条件保持10MHz×8=80MHz，支持的SystemSpec为条件频率/内部调谐、连续BW150–300kHz、PM≥50°；UGF只诊断。Jitter、Lock Time、Static Phase Error、功耗未受支持。

## EVIDENCE：哪些计算和实验支持这套模型？

139点记录包含134点声明域内代表采样和5个异常；124个有效M1点全数值一致，44个M1通过、80个M1失败、15个UNKNOWN。32点共64次既有Python边沿插值事件TB获得独立行为摘要，26点条件频率/控制一致；6点的不可调谐/轨边或未捕获情况原样保存。另有4次近轨长窗口/暖启动诊断。

正式参考BlockSpec为预先指定名义点，保存于 `outputs/block_space_v1_20261104_01/REFERENCE_BLOCKSPEC.json`：BW≈222.379kHz、PM≈56.443°、Vreq=0.4V，有约6.443°PM裕量与72.379kHz带宽下界裕量。状态为M1_VALIDATED。名义点另有事件尾频率/控制比较证据，但不代表全部SystemSpec经过M2验收。

## UNCERTAINTY：哪些范围、公式和指标仍不够准确？

BW/PM/UGF仅得到连续公式的独立数值一致性，行为预测误差尚未建立；不能把近机器精度数值误差当模型误差。事件TB为固定步长Euler摘要、稀疏点、有限窗口，无通用锁定证书。C130距上轨仅1mV，从0.15V冷启动到640µs仍无尾窗跟踪，从Vreq暖启动则保持频率；局部锁定点与捕获能力不同。离轨远、高UGF/fref、未测初值/参数组合均不能整体宣称已验证。

校准记录包含Formula/Parameter Domain/Behavioral Model版本、参数哈希、原预测/观测、单位、两边测量协议、证据、原始误差、局限、建议和原因分类。数值错误、假设不适用、语义冲突、缺失效应、协议不一致和未决六类分开。记录不修正原公式，不实现残差拟合。

## READINESS：现在可以支持哪些 Spec Allocation 实验？

足以在严格标注M1范围的前提下，作为下一阶段低成本逆向Allocation原型的候选检查/正向评估接口：分配上述6参数，目标仅为当前频率、连续BW/PM。可研究联合可行性与数值算法行为；不能据此报告完整事件TB的first-shot成功率、捕获/锁定时间、jitter或硅实现能力。44个通过点提供存在性证据，不是整个搜索域的概率成功率。真正用于行为验收的评估器仍须补强。

## NEXT：优先逆向分配器，还是关键行为模型？

建议技术Leader优先批准一个小范围、可保存波形的事件响应/注入验证模块，聚焦BW/PM预测与捕获边界。原因是M1数值实现已在代表域内充分自洽，而尚缺独立动态测量，近轨诊断已经暴露不能把锁定线性模型外推到捕获的风险。M1逆向原型具备接口条件，可在明确其研究标签后另行批准；本阶段不自行启动。

交付索引：机器模型 `configs/BLOCK_SPACE_MODEL_V1.json`；机器公式注册表 `configs/PLL_EQUATION_REGISTRY_V1.json`；公式报告与本报告同目录；域报告 `DOMAIN_VALIDATION_REPORT.md`；逐点CSV和参考BlockSpec在主运行目录。最终测试、保护核对和实际命令见 `ACCEPTANCE.md`。
