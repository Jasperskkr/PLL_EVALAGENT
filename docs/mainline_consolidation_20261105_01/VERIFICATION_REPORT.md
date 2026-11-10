# Stage 4 / 4.1 / 4.2 主分支归并验证

2026-11-05。用户明确暂停 Stage 5，要求先确认提交归属、唯一正式实现和合并后的 Baseline。目标分支经用户确认为 `master`。本次不继续 Stage 5，不扩展场景接口、策略、模型或测量协议。

## Git 结论

检查前，当前分支 `codex/stage4-1-engineering-validation` 位于 `cd70cf445d2ac6789550b7df2da6736221262045`，已包含三阶段成果；`master` 仍位于 `acf49b881d3e2d22eed879fbc6eca5a3a9a61ccc`。没有配置远程仓库，没有 `main` 分支。

|阶段|成果提交|归并后可从 master 到达|
|---|---|---|
|Stage 4|`7270f3104f5facc89d498f47e8439bcbe02156ce`，保留并正式收录局部返回比研究|是|
|Stage 4.2|`66c4ddb3a2cf075a03c21e19a1a0eccbf69462e3`，Mapping Registry 与能力审查|是|
|Stage 4.1|`3a6a6e1`、`6f93a5f`、`c71798c`、`cd70cf4`，扰动验证及最终回执|是|

归并方式为快进：先验证旧 `master` 是源提交祖先，再以旧 SHA 为比较条件原子更新未检出的 `master` 引用，最后切换至相同文件树的 `master`。没有重写提交、创建合并提交或执行 reset/clean。

```powershell
git merge-base --is-ancestor acf49b881d3e2d22eed879fbc6eca5a3a9a61ccc cd70cf445d2ac6789550b7df2da6736221262045
git update-ref -m "merge codex/stage4-1-engineering-validation: Fast-forward" refs/heads/master cd70cf445d2ac6789550b7df2da6736221262045 acf49b881d3e2d22eed879fbc6eca5a3a9a61ccc
git switch master
git merge-base --is-ancestor 7270f31 master
git merge-base --is-ancestor 66c4ddb master
git merge-base --is-ancestor cd70cf4 master
```

当前本地 `master = cd70cf4`。历史分支保留；其中 `codex/stage4-ugf-pm` 名称仍指向旧的 `47afcb7`，判断成果是否进入主线应依据实际提交与源码，而非该分支名称。未执行远程推送。

## 功能归属及入口

|职责|唯一正式实现|核验方式|
|---|---|---|
|M1 正向评价|`pll_allocation/physics_mapping/model.py` 的 `M1Evaluator` / `evaluate`|对象所属模块、依赖审计|
|分配、反解、Agent、修复|`pll_allocation/allocation/`|六份实现与原迁移清单逐字节一致|
|M2 事件 TB、测量和判决|`pll_allocation/verification/`|正式导入依赖与实际完整 TB|
|统一 Runner|`pll_allocation/pipeline.py`|CLI 分流及合并后实际执行|

`allocation/core.py::assess_m1` 调用上述正式 M1；`allocation/physics.py` 的反解和廉价筛选用于策略工具，不替代正式 M1 或 M2 判决。六个 `track_a` 核心旧模块均为指向正式 `allocation` 模块的同一对象别名。禁止导入历史 `track_a/track_b` 后，正式模块仍可加载；正式 Verification 不导入分配器执行测量。

唯一正式研究运行入口保持 `python -m pll_allocation pipeline`。旧 `run/suite`、Track A CLI 和独立研究工具为历史兼容或专项诊断入口，不构成第二套正式 Pipeline。Stage 5 后续如获恢复授权，只在该入口基础上扩展；本次尚未实现 `--scenario`。

## 合并后 Baseline

在 `master@cd70cf4` 上重新真实执行：

```powershell
python -B -m pll_allocation pipeline --strategy analytical --out experiments/mainline_consolidation_20261105_01/postmerge_baseline
```

固定 10 MHz × 8、80 MHz，BW 150–300 kHz，PM≥50°，原频率容差 1 µHz 与 Protocol 1.1 保持。

|指标|本次结果|与既有结果比较|
|---|---:|---|
|M1 BW|225000.0000001216 Hz|一致|
|M1 UGF|167166.52042501146 Hz|一致|
|M1 PM|72.24720983805331°|一致|
|M2 BW|226403.93447205875 Hz|一致，测量收敛|
|M2 BW 数值包络|[226283.00933770544, 226503.68228813985] Hz|一致，BW PASS|
|冷启动捕获|0.15 V 初值、160 µs 窗口内捕获|一致|
|M2 输出频率观测|79999999.99990459 Hz|一致；严格精度认证 UNKNOWN|
|严格 M2 PM|UNKNOWN|保持 UNKNOWN|
|整体|`M2_PARTIAL_PASS` / UNKNOWN|未签发完整 SystemSpec PASS|

候选、完整 M1 assessment、完整 M2 语义结果分别与合并前实跑及正式 analytical fixtures 精确比较，共六项比较、零差异；仅排除候选运行 ID 和执行成本等运行元数据。本次重新计算，没有复制历史数值作为运行结果。

独立 Baseline 成本：1 次完整 M2，106 次原生仿真，95,090,315 积分点；原生 2.9994542 s，Pipeline 9.5372198 s，完整进程 10.4554538 s；LLM 调用 0。测试内仿真属于回归成本，另存测试日志，不混为该单次 Baseline 成本。

## 回归和保护记录

合并前所有权专项 7 项通过，完整既有套件 328 项通过。合并后完整既有套件再次 **328 项全部通过**，pytest 24.04 s，完整进程 25.2825645 s，失败/错误/跳过均为 0。实际命令如下，解释器绝对路径、日志和 JUnit 见 `experiments/mainline_consolidation_20261105_01/postmerge_tests/`，最终摘要另见本目录 `FINAL_RECEIPT.json`。

```powershell
python -B -m pytest -q tests -p no:cacheprovider --basetemp=experiments/mainline_consolidation_20261105_01/postmerge_tests/tmp --junitxml=experiments/mainline_consolidation_20261105_01/postmerge_tests/tests.xml
```

归并前后 158 份源码、配置、测试及工具逐文件 SHA 一致；原有 4,522 条完整 Git 状态条目无丢失，两份既有 ZIP 删除原样保留。新增内容仅为本次审查/运行输出与阶段状态文档，没有修改正式源码、冻结输入、历史结果或模型。大规模原始波形未重新哈希，保护结论不超出所列范围。

证据位于 `experiments/mainline_consolidation_20261105_01/`：`git_audit/before.json`、`merge_receipt/`、`worktree_protection.json`、`premerge_verifier/`、`postmerge_baseline/`、`postmerge_baseline_receipt/`、`postmerge_tests/`。实际命令、返回码、标准输出、JUnit、版本和成本分别保留；源码运行已验收，本次未做 wheel 安装或跨平台验证。

Stage 5 保持暂停，等待用户进一步指示。
