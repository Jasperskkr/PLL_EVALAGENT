# 多规格全链路验收与远端更新建议（2026-11-24）

本文记录提交前的矩阵与建议。用户随后明确授权提交并更新远端main；实际发布及提交后的独立检出审核见 [提交版本审核](PUBLISH_AUDIT_20261124.md)。下文“未commit/push”和建议命令为该审核时点的状态。

## 结论

本轮完成12组新输入验收：9组进入真实原生M2，2组在M1必要条件检查停止，1组非法N在输入边界拒绝。211项独立产物检查全部通过，未发现串用旧Spec、旧N、其他候选证据或错误交付状态的问题。这里的通过指流程及边界正确，不表示每组Spec都能找到足量候选。

对外输入、权威输出与下游交接已清晰；内部仍有旧模块提前导入的结构债务。本轮只增加验收记录与提交建议，没有继续修改生产代码，没有commit或push。

## 验收方法与实际结果

- 使用固定的316文件源码/配置/本地后端快照；复制时无源码变化，运行后与当前工作区逐文件一致。下述报告编辑发生在该核对之后，不改变执行代码。
- 每组实际执行 `python -B -m pll_allocation pipeline --problem ... --allocator-config ... --out ...`，使用新运行目录；没有Mock、TEST M2或付费API调用。
- 参考频率10MHz，输出目标为当前N×10MHz；电压轨0–1.2V。N4/N16正例将nominal的f0、Kvco域按N/8缩放，其他四轴不变；N10正例保留原六轴域。
- 默认M1预算96、最多2次重分配；各组M2预算及联合交付目标如下。所有PM/jitter的正式M2未支持项保持UNKNOWN。

| 场景 | N / 输出目标 | BW(kHz) / PM下限 / lock上限 | 正式交付/目标 | 实际M1 / M2；M2预算 | 停止原因 |
| --- | --- | --- | --- | --- | --- |
| nominal | 8 / 80MHz | 150–300 / 50° / 40µs | 3/3 | 15 / 5；8 | 达标 |
| tight | 8 / 80MHz | 290–300 / 70° / 40µs | 3/3 | 13 / 4；8 | 达标 |
| N4调谐域匹配 | 4 / 40MHz | 180–220 / 60° / 40µs | 1/2，PARTIAL | 17 / 5；6 | MAX_REALLOCATIONS |
| N10原变量域 | 10 / 100MHz | 200–260 / 60° / 40µs | 1/2，PARTIAL | 19 / 5；6 | MAX_REALLOCATIONS |
| N16调谐域匹配 | 16 / 160MHz | 120–180 / 55° / 80µs | 2/2 | 9 / 3；6 | 达标 |
| 严格锁定时间 | 8 / 80MHz | 150–300 / 50° / 5µs | 0/1，NOT_REACHED | 16 / 4；4 | M2预算耗尽 |
| 极小M2预算 | 8 / 80MHz | nominal | 0/3，NOT_REACHED | 7 / 1；1 | M2预算耗尽 |
| N4保留原调谐域 | 4 / 40MHz | nominal | 0/3 | 0 / 0；8 | PROVEN_M1_INFEASIBLE |
| 过高PM | 8 / 80MHz | 150–300 / 95° / 40µs | 0/3 | 0 / 0；8 | PROVEN_M1_INFEASIBLE |
| AUTO_HYBRID | 8 / 80MHz | nominal | 3/3 | 15 / 5；8 | 无付费授权，确定性分支达标 |
| 四项条件物理增强开启 | 8 / 80MHz | nominal | 3/3 | 35 / 3；6 | 达标 |
| 非法N=0 | 0 | nominal | 无运行产物 | 0 / 0 | 结构化错误，退出码2 |

矩阵合计 **146次M1、35次M2验证、3738个原生子运行、0次LLM**。M2原生子运行数量由幅度/步长/窗口及收敛检查决定，不将一次验证误算为一次原生执行。

N4、N10都实际触发2次 `AGENT_REPLANNING_STARTED`，验证了失败后重新分配链。N4还触发一次UNKNOWN显式复核；最终只交付一个正式通过点，未将UNKNOWN计为通过。lock≤5µs的4次M2均失败，2次重分配后交付仍为空。nominal首两点锁定时间54/45µs失败，后续29/24/35µs通过；tight首点BW失败后换点，均有原生证据。

增强配置本例以更多M1换取更少M2；单一问题的结果不证明策略普遍更优。AUTO本轮未覆盖真实LLM决策分支。

## 调用与交接核对

```text
problem.json + allocator.json
  → cli.main → pipeline.main → run_spec_allocation
  → initial allocation / PoolSearchLoop
  → 物理反解 / RegionExplorer → 正式M1 → 独立M1复核
  → verification_handoff → run_feedback
  → continuous M2 → 原生仿真 / 测量 / 判决
  → 池内换点 / 重分配 / UNKNOWN显式复核
  → validate_sizing_handoff → sizing_handoff → run_manifest
```

独立检查覆盖当前问题与源输入SHA绑定、候选N及六轴域、M2请求与每个原生观测的频率计划、跨阶段问题身份、预算与实际调用账本、交付数量/目标/状态/推荐一致性、权威文件SHA、相对M1 context、未支持指标状态。12组共211项检查全部通过。

另一次完整N8原生运行开启函数轨迹，覆盖CLI父进程与3个M2子进程；该次额外执行9次M1、3次M2、318个原生子运行。观测到正式编排、交付校验与manifest写出；父进程加载74个项目模块，M2子进程各26个。旧v1入口、`_legacy/`、旧冻结分配编排、`track_a/`、`studies/` 没有业务函数调用，`allocation/core.py`、`physics.py` 则确实是主线共享计算。

**仍需后续清理的内部依赖：** `cli.py` 顶层加载v1模块，`pipeline.py`/`allocation/__init__.py` 提前加载冻结模块。执行路由没有误入旧算法，但导入层尚未隔离；建议下一次独立重构改为按路由延迟加载，并保留兼容入口及来源绑定。结构审计本轮PASS、六份冻结实现字节一致；该审计的依赖检查范围仍为58份文件，不能替代上述运行证据。

消费者应以 `run_manifest.json` 定位权威输出，以 `sizing_handoff.json.candidates` 作为正式下游集合，先调用 `validate_sizing_handoff`。`recommended_M2_supported` 才是正式推荐；旧 `recommended` 可能只有M1通过。CLI退出码0表示流程完成，仍须读取 `joint_status`、交付数量及停止原因，PARTIAL/空交付不会因此变成达标。

此前固定快照完整测试为 **958 passed / 10 skipped / 0 failures / 0 errors**，使用 `-W error`。本轮确认所有Python/C++/CMD/JSON与该全量测试快照一致，pyproject仅行尾不同且TOML语义相同；本轮未重复运行全套测试。10项跳过依赖未提供的历史档案。

## 远端与提交建议

对 [GitHub仓库](https://github.com/Jasperskkr/PLL_EVALAGENT) 实时执行 `git ls-remote --symref origin HEAD refs/heads/main` 和 `git fetch --no-tags origin main`，最终均成功：

| 项目 | 核对结果 |
| --- | --- |
| 远端默认分支 | main |
| 远端main / 本地origin/main | `e2d4dfa2d1d68247df11ede477a5d28df693078e` |
| 本地main HEAD | `70e9ddace4e3046fc8ef2fe0c9ee26fee13b06b4` |
| 本地相对远端 | ahead 1 / behind 0，无分叉 |
| 尚未推送的既有提交 | `feat(vco): add hardened sizing guidance and revalidation contract`；9文件、1481行新增 |
| 工作区 | 暂存区为空；当前集成改动尚未提交，具体清单见CODE_STATE |

远端还留有master、历史研究分支和标签，本次更新无需调整它们。GitHub网页/API曾返回403，未核实PR、Actions、保护规则或写权限；最终Git只读访问及fetch成功，不把它当成CI通过或可推送证明。

建议**从当前HEAD建功能分支，保留既有VCO提交，再新增一个完整集成提交，通过PR合入main**。条件物理、整数N和交接清洗在候选池、反馈与输出文件中交叉修改，机械按文件拆开容易产生中间不可运行状态。该PR应包含现有VCO提交和新的集成提交。

建议主题：`feat: integrate physics guidance, integer-N verification and clean handoffs`。

提交范围包括维护源码、新配置和provenance、新测试、安装清单及维护文档；`learn/physics-inverse-walkthrough.md` 可一并提交。`learn/n10-spec-trace-20261124/` 保留在本地：其中walkthrough记录的是修复前“N10被M2拒绝”的旧状态，trace_summary和旧源码哈希也是一次性实验记录；若后续发布这组学习材料，应先明确历史标记、筛出可复用输入。

以下是建议命令，**本轮未执行**：

```powershell
Set-Location -LiteralPath 'F:\LJP\概伦AI\PLL_EVALAGENT-main\PLL_EVALAGENT-main'
git fetch origin main
git switch -c feat/spec-allocation-integration
git add -- PROJECT_CHARTER.md README.md pyproject.toml configs docs pll_allocation tests tools learn/physics-inverse-walkthrough.md
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "feat: integrate physics guidance, integer-N verification and clean handoffs"
git push -u origin feat/spec-allocation-integration
```

检查暂存差异后执行commit/push，再向main建立PR。若届时远端main已前进，先合入远端变更并重验受影响部分；无需force push。实验、源码快照、outputs、handoff_exports、DLL/build和凭据均不提交。

本机证据位于 `experiments/spec_matrix_20261124_01/`：`case_manifest.json`、每组`command.json`/输入/完整产物、`inspection.json`、`traces/`、`final_audit.json`、`remote_final.json`、`fetch_final.json`。目录受Git忽略，保留本地；前次完整测试证据仍在 `experiments/structure_audit_20261124_01/`。
