# Mainline Safety Report

Stage6A研究根目录为`C:/Users/Lenovo/.codex/worktrees/stage6a-multispec-feasibility/PLL_allocation`，分支`codex/stage6a-multispec-feasibility`。原目录`F:/LJP/概伦AI/PLL_allocation`保持master，不合并、不提交、不push、不stash、不清理或丢弃用户改动。

开始与当前master HEAD均为cd70cf445d2ac6789550b7df2da6736221262045，Stage3A.1=47afcb7、Stage4=7270f31、Stage4.2=66c4ddb、Stage4.1=cd70cf4均为其祖先。Stage5没有完整提交，收据明确依赖HEAD加工作树SHA；本轮没有把HEAD冒称为完整Stage5源码。

原工作树tracked差异：docs/DECISIONS.md、docs/PROJECT_STATUS.md、pipeline.py、pipeline_contracts.py四个修改；两份原ZIP删除。另有Stage5源码/测试/文档/研究证据、关系图谱与大量历史输出未跟踪。逐行完整清单、binary diff、分支/log/remotes、依赖和字节清单在`experiments/stage6a/safety_01`，不在报告中省略后宣称干净。

隔离前先逐文件复制并校验14,709份非忽略文件，共478,501,915字节；保留两份既有缺失tracked文件状态。原ignored raw/build/cache留原地未动，隔离区重建三个native后端；其源码与原manifest一致。Git分支继承的旧未提交差异仍未提交，研究基线明确为HEAD+baseline_files.json。未引入第二套正式模型或Agent。

Stage6A新增内容仅docs/stage6a、experiments/stage6a及tests/test_stage6a_joint.py；隔离区只追加DECISIONS/PROJECT_STATUS阶段记录。正式pipeline/M1/M2/Allocation/配置/方程/域/协议未改。M1仍physics_mapping，策略/repair仍allocation，M2仍verification；唯一正式运行入口仍`python -m pll_allocation pipeline`。研究driver只准备候选、记录计时和重判研究阈值，不持有第二套模拟器或分配实现。显式proposal通过原接口复验，正式SystemSpec与研究场景分别保存。

测试：开始364 passed，研究判决12 passed，最终376 passed；最终无失败/错误/跳过。预回归与最终回归分别真实执行，不能相加称为独立测试覆盖。最终81份正式与冻结研究源码/配置SHA零变化。E0真实Baseline复验完整候选/M1/M2语义一致。Stage5 S3/Random11反例仍判联合FAIL。

初次及最终结果/保护audit_01/02各191检查通过：8个候选真实M2与输入binding、native调用/时间、首次落盘trace、冻结source、Registry、历史反例、原14,709份文件SHA、原Git状态及HEAD全部一致。独立verifier另有88项结果审计与74项报告审计全通过。保护检查与静态元数据核对不产生新M1/M2或LLM；verifier结果汇总8次M1重判已独立计账。

未做wheel安装、跨平台验收、Git新提交或master合并。DLL、raw轨迹、日志、失败证据均保留在隔离区；源码/小型报告可独立审查。旧工程、冻结输入和历史运行没有被覆盖。
