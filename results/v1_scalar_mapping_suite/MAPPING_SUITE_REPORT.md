# V1 多类型一维 SystemSpec-to-VCO-Spec 映射报告

本报告由 `python run_v1_mapping_suite.py` 确定性生成；模型与指标均没有随机采样。

| System metric | System limit/target | Initial | VCO search knob | Search boundary | Candidate | Final | Probed shape | BlockTB | SystemTB |
|---|---:|---:|---|---:|---:|---:|---|---|---|
| integrated_jitter | 8e-14 s | 8.33673495e-14 | pn_anchor_1mhz_dbc_hz | -116.358124 | -118 | 6.62210396e-14 | single_boundary_over_probed_range | PASS | PASS |
| lock_time | 3.4e-05 s | 3.652e-05 | k1_hz_per_v | 624385357 | 700000000 | 3.072e-05 | feasible_window_or_non_monotonic_over_probed_range | PASS | PASS |
| power | 0.0052 W | 0.00542207672 | nominal_power_w | 0.00479520988 | 0.0047 | 0.00509675211 | single_boundary_over_probed_range | PASS | PASS |
| frequency | 5.8e+09 Hz | 5.662e+09 | f0_hz | 4.60527391e+09 | 4.61e+09 | 5.80000116e+09 | feasible_window_or_non_monotonic_over_probed_range | PASS | PASS |

## 解释

- `single_boundary_over_probed_range`：在本次显式扫描范围内只有一个 PASS/FAIL 分界，可作为一维上下界。
- `feasible_window_or_non_monotonic_over_probed_range`：宽范围内有多个分界，只能在记录的 validity bracket 内使用局部一维映射；不能宣称全局单调。
- frequency→f0 的真正 Block 能力含义是目标频率是否落入 VCO tuning coverage；f0 是当前行为模型中的搜索参数。
- 每条映射都执行一个显式的一维 candidate grid；按可行性和相对 base parameter 的最小改变量选择 candidate。完整结果见 `candidate_search.csv`。
- 所有 candidate 都先通过冻结 context 下的 BlockTB，再用同一 realized instance 独立重跑 SystemTB。SystemTB PASS 但 BlockTB FAIL 的候选不会被选择。
