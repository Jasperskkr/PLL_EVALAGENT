# 当前主线架构

研究目标与范围由PROJECT_CHARTER.md冻结；详细设计见P0_TARGET_ARCHITECTURE.md和docs/INTERFACE_CONTRACT.md。

入口为 `python -m pll_allocation`，生产包为pll_allocation，不导入本机旧pll_spec_alloc或pll_agent。contracts.py负责Problem与五Block候选、单位和声明域；policies.py负责规则、网格、随机、反馈和真实LLM提议；behavioral.py适配原字节内核并独立度量/判决；runner.py持有输入冻结、完整TB、预算、首次保存、trace和报告；cli.py仅构造配置和策略。

Policy负责设计，不能改SystemSpec或决定跳过TB。Backend负责实际行为计算及测量事实，MetricVerifier负责冻结验收。FastScreen的解析平衡相位单独存储；同一行为积分器不会被拆成两次伪独立验证。

运行路径：Problem→Policy→完整JointBlockSpec先保存→ConstraintChecker→FastScreen→40µs行为TB→MetricVerifier→输出；FAIL时将真实违例与解析耦合关系回传，有限修复。UNSUPPORTED指标在一次实际测量后明确终止，运行异常计费UNKNOWN。外部模拟器通过可注入Protocol或argv/JSON桥接入，接口存在与外部MATLAB实际验收分开。

当前物理域限定10–10.5MHz参考、N=8、1.8V/27C，模型为周期电荷/理想RC/线性VCO。声明目标的经验准确度尚未建立，PASS范围是该模型；没有物理资格升级。真实LLM服务当前超时，P3/P4的LLM贡献比较仍未完成。
