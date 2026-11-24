# 当前代码状态与后续推送交接（2026-11-24）

发布阶段说明：本文保留提交前工作区盘点。用户随后明确授权提交并更新远端main；当前发布执行及提交后的独立检出审核以 [提交版本审核](PUBLISH_AUDIT_20261124.md) 为准，下列“未提交”“本轮未push”和分支建议描述的是前次审核时点。

## 结论

当前工作区已把条件物理增强、正整数N的连续域M2、输入/输出/交接清洗集成到同一主线，完成固定源码快照的完整回归，以及N=4/8/10/16等12组新输入矩阵验收。仍有未提交代码。本轮没有执行commit或push，后续推送应包含既有未推送提交及本次经验证的全部维护源码。

项目结构分类、已修复问题和兼容代码处理依据见 [结构审核](STRUCTURE_AUDIT_20261124.md)。本文用于后续继续工作，避免把尚未提交的开发能力或本地实验目录遗漏/混入发布。

最新矩阵、动态调用轨迹及功能分支/PR提交命令见 [多规格验收与远端更新建议](SPEC_MATRIX_AND_REMOTE_20261124.md)。流程与边界验收通过，不表示所有Spec都达到交付数量；N4/N10本轮均为1/2部分交付，严格锁定时间例为空交付。

## Git与远端

| 项目 | 已核对状态 |
| --- | --- |
| 实际Git根目录 | `F:/LJP/概伦AI/PLL_EVALAGENT-main/PLL_EVALAGENT-main`，外层同名目录不是Git仓库 |
| 当前分支 | `main`，跟踪 `origin/main` |
| 远端默认分支 | `main`，通过实时 `git ls-remote --symref origin HEAD` 核对 |
| 本地HEAD | `70e9ddace4e3046fc8ef2fe0c9ee26fee13b06b4` |
| HEAD主题 | `feat(vco): add hardened sizing guidance and revalidation contract` |
| origin | `https://github.com/Jasperskkr/PLL_EVALAGENT.git`，fetch/push使用同一地址 |
| 实时远端main | `e2d4dfa2d1d68247df11ede477a5d28df693078e`，通过 `git ls-remote` 核对，等于本地origin/main |
| 相对远端 | ahead 1 / behind 0；已提交的VCO改动尚未推送 |
| 暂存区 | 空；工作区有未提交修改和新文件 |

添加最新矩阵报告后，工作区清单为30个已跟踪文件修改、28个新文件；以后以 `git status --porcelain=v1 -uall` 为准。该清单包含本轮开始前已有开发内容及审核期间并行加入的频率规划，不能当成仅有接口清洗这一个补丁。

## 未提交改动的三个部分

| 部分 | 主要代码/输入 | 当前状态 |
| --- | --- | --- |
| 条件物理增强与LLM工具证据 | `physics_mapping/analytic_features.py`、`predictors.py`；`exploration/conditional_physics.py`、`physics_region_builder.py`；`agent/conditional_observation.py`、`physics_ranking.py` 及候选池/Policy/执行器修改；`configs/agent/noise_aware.json`、`physics_enhanced.json`；`tools/run_physics_comparison.py`、`learn/` | 保留既有开发能力，四开关默认关闭；条件预测不取得正式M2 PASS权 |
| 当前问题的正整数N频率规划 | `verification/simulator.py`、`measure.py`、`experiments.py`、`run_suite.py`、`continuous.py`；`configs/provenance/integer_n_m2.json`、`physics_registry.json`；`tests/verification/test_frequency_plan.py` | 标准连续域读当前N，目标N×f_ref；参考仍为10MHz、电压轨0–1.2V；旧冻结/可选扩展保持各自范围 |
| 输入输出与交接清洗 | 新 `io_contracts.py`、`delivery.py`、`tests/test_io_boundaries.py`；`pipeline.py`、`exploration/contracts.py`、`agent/handoff.py`、`feedback.py`、`search_loop.py`、`spec_allocation.py`、`vco_sizing/contract.py`；相关说明文档 | 严格外部JSON、统一错误出口、权威产物索引、READY与多点摘要一致性、可迁移M1交接、新旧M2协议消费门禁 |

部分文件同时包含多个部分的改动，尤其 `agent/spec_allocation.py`、`handoff.py`、`feedback.py` 和共享文档。后续若拆提交，应按可运行的完整功能组织；不能只挑新增文件而漏掉调用端、配置安装清单或来源收据。

## 当前主线与权威输入输出

```text
problem + allocator
  → pipeline → spec_allocation → initial allocation / PoolSearchLoop
  → 原物理反解 + RegionExplorer + 正式M1 + 独立复核
  → M1 verification_handoff → feedback → continuous M2
  → delivery校验 → sizing_handoff → run_manifest
```

- 用户问题：`ResearchProblemV2`，包含SystemSpec、六个变量域、当前固定N等条件；策略预算由allocator控制。
- 权威结果入口：新运行的 `run_manifest.json`，用相对路径和SHA256指向已解析输入、结果、候选、成本、报告与交付。
- 下游交付：`sizing_handoff.json.candidates`，用 `pll_allocation.delivery.validate_sizing_handoff` 检查；`recommended_M2_supported` 是正式推荐，旧 `recommended` 可能只有M1通过。
- M2接续输入：`initial/verification_handoff.json` 及其绑定context/证据；新输出可随完整运行目录迁移，旧绝对路径输入继续支持。
- 原协议记录按旧N=8适配校验，新整数N协议按候选频率计划校验；历史请求身份不用于冒充新执行。

## 验收状态

| 检查 | 结果 |
| --- | --- |
| 固定快照完整回归 | **958 passed / 10 skipped / 0 failures / 0 errors**，968项，`-W error` |
| 跳过原因 | 6项历史重放、2项历史M2、1项旧pilot、1项历史数值扫描未随源码提供 |
| 结构/职责命名审计 | PASS；六份原分配实现仍字节相同 |
| 默认N=8完整原生运行 | 联合交付3点；M1=15、M2验证=5、LLM=0 |
| N=10完整原生运行 | 联合交付1点；M1=9、M2验证=3、LLM=0 |
| N=8清洗前与集成后数值对照 | 候选参数、M1/M2指标与判决、交付哈希及实际调用计数逐项相同 |
| 新旧交付读取 | 均通过共享门禁；PM/jitter继续UNKNOWN，未声称全SystemSpec/管级/PVT认证 |
| 当前代码与验收快照 | Python/C++/CMD/JSON一致；pyproject仅行尾字节差异，TOML语义一致 |
| 新增多规格矩阵 | 12组、211项独立检查通过；146次M1、35次M2、3738个原生子运行，无LLM/TEST |
| 新增动态函数轨迹 | 正式N8端到端及3个原生M2子进程；旧业务函数无调用，旧模块仍有提前导入债务 |

此前全量测试曾在并行修改期间混用源码版本，另一次收集暴露私有兼容辅助入口缺失；已修复并改用固定快照，以上最终结果覆盖当前集成状态。没有执行真实付费API效益实验。

本地证据目录：`experiments/structure_audit_20261124_01/`。主要文件为 `snapshot_pytest.xml/log`、`snapshot_receipt.json`、`final_architecture.json`、`delivery_acceptance.json`、`integrated_comparison.json`、`module_inventory_final.json` 和 `final_code_state.json`。该目录及源码/后端快照受Git忽略，作为本机验收证据保留。

## 后续提交与推送边界

建议从当前HEAD建立功能分支，把当前三部分作为一个集成提交收口，连同已有VCO提交推送该分支，再向main建立PR。建议主题：`feat: integrate physics guidance, integer-N verification and clean handoffs`。本轮没有执行分支创建、commit或push。

应包含所有维护源码、新配置及来源收据、新测试、维护文档、`learn/physics-inverse-walkthrough.md`、pyproject安装清单。`learn/n10-spec-trace-20261124/` 含修复前的教学状态及一次性实验摘录，先保留本地；如需发布应补历史标记并筛选。实验输出、审核快照、outputs、handoff_exports、原生DLL/build目录和凭据不属于源码提交；现有忽略规则已排除这些本地产物。

实际推送前重新核对当前工作区与实时远端；如果代码或协议再有改动，应补对应验证。最终实时远端查询与fetch成功；只读访问不表示写权限已经验收，GitHub网页/API受403限制，PR/CI及分支保护未核实。
