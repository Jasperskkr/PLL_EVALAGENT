# V1 SystemSpec-to-VCO-Spec test matrix

本报告由 `python run_v1_spec_matrix.py` 确定性生成。正例运行完整 V1 pipeline；负例验证 PN 一维分配不会掩盖 lock-time/power 违例。

## 表 0：12 步 pipeline 的测试证据

| 步骤 | Pipeline 节点 | 本次验证证据 |
|---|---|---|
| 1–3 | SystemSpec → SystemTB → residual | system_spec.json + initial_system_evaluation.json + 表 1 |
| 4–5 | characterization → sensitivity | vco_characterization.csv + sensitivity.json |
| 6–7 | PN boundary → margin | required_vco_spec_boundary.json + recommended_vco_spec.json + 表 2 |
| 8–9 | candidate → BlockTB → SystemTB | block_feasibility.json + 表 3 |
| 10–11 | cost selection → final SystemTB | realized_vco_instance.json + final_system_evaluation.json |
| 12 | trace/schema/graph | trajectory.jsonl + BlockMeta + Graph v2 + artifact completeness assertion |

## 表 1：SystemSpec → VCO Spec 正向分配

| Case | Temp (C) | Jitter limit (fs) | Initial (fs) | Residual (fs) | Initial | Required PN | Recommended PN | Abstract @rec (fs) | Selected | Final (fs) | Final |
|---|---|---|---|---|---|---|---|---|---|---|---|
| matrix_jitter_140fs | 25 | 140.000 | 83.367 | -56.633 | PASS | -111.497359 | -112.997359 | 117.795 | candidate_baseline | 83.367 | PASS |
| matrix_jitter_100fs | 25 | 100.000 | 83.367 | -16.633 | PASS | -114.419920 | -115.919920 | 84.140 | candidate_low_noise | 41.783 | PASS |
| matrix_jitter_80fs | 25 | 80.000 | 83.367 | 3.367 | FAIL | -116.358120 | -117.858120 | 67.312 | candidate_low_noise | 41.783 | PASS |
| matrix_jitter_60fs | 25 | 60.000 | 83.367 | 23.367 | FAIL | -118.856895 | -120.356895 | 50.484 | candidate_ultra_low_noise | 26.363 | PASS |
| matrix_jitter_50fs | 25 | 50.000 | 83.367 | 33.367 | FAIL | -120.440520 | -121.940520 | 42.070 | candidate_ultra_low_noise | 26.363 | PASS |
| matrix_jitter_80fs_three_temperatures | -40/25/125 | 80.000 | 100.650 | 20.650 | FAIL | -117.994487 | -119.494487 | 67.312 | candidate_ultra_low_noise | 31.828 | PASS |

## 表 2：PN 边界双向验证

注：PN 数值越负代表要求越严。本表在求得边界两侧各取 0.05 dB，检查紧一侧 PASS、松一侧 FAIL。

| Case | Required PN | Tighter PN | Tighter jitter | Result | Looser PN | Looser jitter | Result |
|---|---|---|---|---|---|---|---|
| matrix_jitter_140fs | -111.497359 | -111.547359 | 139.196 | PASS | -111.447359 | 140.808 | FAIL |
| matrix_jitter_100fs | -114.419920 | -114.469920 | 99.426 | PASS | -114.369920 | 100.577 | FAIL |
| matrix_jitter_80fs | -116.358120 | -116.408120 | 79.541 | PASS | -116.308120 | 80.462 | FAIL |
| matrix_jitter_60fs | -118.856895 | -118.906895 | 59.656 | PASS | -118.806895 | 60.346 | FAIL |
| matrix_jitter_50fs | -120.440520 | -120.490520 | 49.713 | PASS | -120.390520 | 50.289 | FAIL |
| matrix_jitter_80fs_three_temperatures | -117.994487 | -118.044487 | 79.541 | PASS | -117.944487 | 80.462 | FAIL |

## 表 3：Allocated Spec → Candidate → BlockTB/SystemTB 反向验证

| Case | Candidate | PN knob | Worst PN in context | BlockTB | PLL jitter (fs) | Lock (us) | Frequency (GHz) | Power (mW) | SystemTB |
|---|---|---|---|---|---|---|---|---|---|
| matrix_jitter_140fs | candidate_baseline | -116.000 | -113.232 | PASS | 83.367 | 36.520 | 5.000000000 | 5.422 | PASS |
| matrix_jitter_100fs | candidate_low_noise | -122.000 | -119.232 | PASS | 41.783 | 36.520 | 5.000000000 | 5.422 | PASS |
| matrix_jitter_80fs | candidate_low_noise | -122.000 | -119.232 | PASS | 41.783 | 36.520 | 5.000000000 | 5.422 | PASS |
| matrix_jitter_60fs | candidate_ultra_low_noise | -126.000 | -123.232 | PASS | 26.363 | 36.520 | 5.000000000 | 5.422 | PASS |
| matrix_jitter_50fs | candidate_ultra_low_noise | -126.000 | -123.232 | PASS | 26.363 | 36.520 | 5.000000000 | 5.422 | PASS |
| matrix_jitter_80fs_three_temperatures | candidate_ultra_low_noise | -126.000 | -121.515 | PASS | 31.828 | 36.600 | 5.000000000 | 5.959 | PASS |

完整候选逐项结果见 `reverse_candidate_validation.csv`。

## 表 4：一维 PN allocation 的正确拒绝案例

| Case | Jitter limit (fs) | Lock limit (us) | Power limit (mW) | Tight PN trial | Blocking checks | Conclusion |
|---|---|---|---|---|---|---|
| matrix_lock_30us_not_pn_allocatable | 80.000 | 30.000 | 8.000 | -130.000 | lock_time | REJECTED as expected |
| matrix_power_5mw_not_pn_allocatable | 80.000 | 40.000 | 5.000 | -130.000 | power | REJECTED as expected |

## 自动断言

- `tighter_jitter_maps_to_tighter_pn`: **PASS**
- `boundary_tighter_side_passes`: **PASS**
- `boundary_looser_side_fails`: **PASS**
- `recommended_abstract_specs_pass`: **PASS**
- `selected_candidates_pass_blocktb`: **PASS**
- `selected_candidates_pass_systemtb`: **PASS**
- `all_case_evidence_artifacts_exist`: **PASS**
- `non_pn_violations_are_rejected`: **PASS**

140 fs 和 100 fs case 的初始 SystemTB 虽然已 PASS，但 candidate 仍按“边界 + 1.5 dB 设计裕量”的 Block requirement 筛选；因此 100 fs case 会选择 low-noise candidate。

## 结论

在固定 PLL 架构、行为模型和其余约束可满足时，jitter SystemSpec 可以确定性映射为一维 VCO PN requirement；更严格的 jitter 会得到更严格（更负）的 PN。边界两侧的 PASS/FAIL 和候选回代结果共同构成正向求解与反向验证证据。若失败来自 lock time 或 power，PN-only allocator 会拒绝分配，说明必须进入 PN × Kvco 或多 Block allocation。
