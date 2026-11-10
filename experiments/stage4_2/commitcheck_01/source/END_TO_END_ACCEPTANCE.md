# 端到端验收

截至2026-11-03：**P0审计、P1最小合同和P2真实行为纵向链已完成；P3真实LLM提议/修复和P4的LLM公平比较尚未完成，P5为部分交付审计。**

## 本轮实际命令

在 `F:/LJP/概伦AI/PLL_allocation` 执行：

```powershell
python -B tools/audit_sources.py --out docs/audit/source_inventory_before.json
python -B tools/create_examples.py
python -B tools/inherit_matlab_reference.py
python -B -m pytest -q -p no:cacheprovider --junitxml=docs/validation/tests.xml
python -B -m pll_allocation suite --out outputs/final_behavioral_suite --budget 30 --policies rule grid random feedback
python -B -m pll_allocation run --problem examples/joint84.json --policy rule --out outputs/final_repro_joint84 --budget 30
python -B -m pll_allocation run --problem examples/regular80.json --policy replay --replay outputs/final_behavioral_suite/regular80__rule/initial_joint_block_spec.json --out outputs/final_saved_proposal_replay --budget 1
python -B -m pll_allocation run --problem examples/regular80.json --policy llm_initial --out outputs/p3_live_initial --budget 1
python -B -m pll_allocation run --problem examples/tight80.json --policy llm_feedback --out outputs/p3_live_bounded --budget 3 --max-attempts 3
python -B tools/audit_sources.py --out docs/audit/source_inventory_after.json --compare docs/audit/source_inventory_before.json
python -B tools/validate_delivery.py
```

历史生成/正式输出路径已经存在，重跑须替换为新的输出目录；不要覆盖上述证据。部分源提取通过本轮Python脚本完成，字节和来源SHA由legacy_manifest记录；运行主链不需要重新提取。

## 验收证据

- 最终93 passed，0 failed，0 errors，0 skipped；93项包含24组数值锚点和24组完整历史MATLAB轨迹（共9600周期）、单位/合同、首次保存、失败修复、预算、异常、子进程TB、回放和总超时路径。
- 正式套件20组运行，共198次完整行为TB；规则/网格/随机/反馈基线共用冻结输入、空间、TB和30次评价预算。逐项成本/指标见POLICY_COMPARISON_REPORT.md。
- 80MHz非零q0常规及0.19°收紧目标、84MHz联合目标均找到可行点。反馈策略示例：80µA、6fC、3820Ω→真实相位0.270089669° FAIL；基于该违例提议110µA、6fC、3820Ω，完整TB测得0.196436600° PASS。两个完整候选都保留。
- 0.1°目标的30点有限域全部评价后未找到；不宣称连续域或电路全局不可行。抖动无模型，实际TB后返回UNSUPPORTED_SYSTEM_SPEC，不改变目标。
- 84MHz重复运行decision_sha256一致；脚本核验完整文件、逐周期数、输入/候选绑定、trace链、预算及运行源码SHA。
- 从规则策略真实保存的首次候选实际执行离线回放，明确标记saved_proposal_replay_v1，新的完整行为评价1次、LLM请求0次；未冒充新LLM分配。
- 2425个旧源文件指纹比较无变化；97/97旧来源引用匹配。24份MATLAB record原SHA匹配；其CSV/语义以本轮SHA另存。RAW只做元数据盘点，没有虚称重新测量。

## 明确未完成

两次真实服务请求都未产生可用候选：当前配置模型deepseek-v4-pro，HTTP 200后读取超时；第一次旧socket超时实际约120.57s，第二次总进程期限60.03s并已停止。调用输入、状态和成本存于对应llm_calls目录，token/费用未知。没有伪造首次候选或规则替代。

因此真实LLM初始分配、真实LLM失败后修复、LLM与基线的统计对照均未验收。MATLAB实际命令后端尚未接入；当前Python后端依据历史MATLAB回归，外部JSON命令桥只完成真实子进程Python TB测试。采样频域、噪声/抖动和电路实现资格均未验收。

这份交付完成的是可运行研究底座和可审计的确定性纵向验证；不代表原prompt的全部最终标准已经满足。
