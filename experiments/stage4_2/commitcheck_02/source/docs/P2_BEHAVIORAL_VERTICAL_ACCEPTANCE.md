# P2 首条纵向链验收

2026-11-03，在P0和P1产物基础上执行：

```powershell
python -B -m pll_allocation run --problem examples/regular80.json --policy rule --out outputs/p2_first_vertical --budget 30
```

输出：VERIFIED_BEHAVIORAL_PASS，首次候选通过；实际完整行为评价1次、400参考周期，最小归一化裕量0.017817001961826645。相位解析预测与实际TB测量差为7.296324399833076e-05度，分开保存，未把预测直接作为测量。

`outputs/p2_first_vertical/` 含冻结输入、空间、拓扑、首次/最终联合规格、独立约束、完整TB测量、实际周期波形、标准metrics、带SHA链轨迹和run_manifest。新入口运行依赖为Python标准库和本地提取内核，不读取旧仓库或历史runs。ngspice/MATLAB调用均为0；Python行为积分是真实新执行。

64项测试含真实初始FAIL→后续完整候选→真实TB PASS、异常计费UNKNOWN、输出拒绝覆盖、无LLM环境不伪造候选。上述仅验收声明行为模型，不授予电路实现、独立高保真或噪声资格。
