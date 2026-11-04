# P1 合同与约束验收

2026-11-03。P0产物落盘后完成版本化Problem/五Block候选/评价/轨迹合同，见 INTERFACE_CONTRACT.md 与 contracts.py。

实际命令：`python -B -m pytest -q -p no:cacheprovider`，64 passed，0 failed，0 skipped（3.49s）。包括单位/符号/共同条件、参数完整性与范围、CP方向耦合、fout=N*fref、有限数、模型域、冻结测量协议。来源快照10份保持提取时字节；24个纠正后MATLAB参考案例重新执行Python积分并与历史期望比较。

数据对象采用版本化JSON DTO，不为每个对象机械创建类。范围为固定Integer-N、N=8、10–10.5MHz参考、1.8V/27C、40us/tail50/hold20协议；扩大范围需模型版本及回归，不能由Policy自行决定。未知指标保留原SystemSpec并返回UNSUPPORTED，不删除约束。

物理映射复用原 signed_charge/equilibrium_timing、精确RC和VCO积分；新screen仅给平衡相位和Veq。完整动态测量不使用screen结论。外部Verifier/Backend通过Protocol注入；external argv/JSON桥用真实子进程运行同一行为TB的集成测试通过，MATLAB实机尚未执行。
