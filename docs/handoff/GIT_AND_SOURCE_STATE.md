# Git、工作树及来源实况

只读审查日期2026-11-09，Asia/Shanghai。三个现有工作树HEAD都是 **cd70cf445d2ac6789550b7df2da6736221262045**；分支分别为master、codex/stage6a-multispec-feasibility、codex/stage6b-sensitivity-allocation。Git日志/原始完整status、tracked与非忽略文件SHA在provenance。交接操作只写handoff_exports新目录，未stash/checkout/reset/clean/提交/合并或覆盖旧结果。

## 提交关系

```text
acf49b8  既有基线快照（包含此前Stage1/1.5等）
  └ e5bf67a  Track A physics allocation
     └ 47afcb7  Stage3A.1 formal ownership/freeze
        └ 66c4ddb  Stage4.2 readiness/Registry
           └ 7270f31  checkpoint Stage4 local return-ratio
              └ 3a6a6e1  Stage4.1 phase-step protocol
                 └ 6f93a5f  retained waveforms separation
                    └ c71798c  fixed-candidate validation
                       └ cd70cf4  review/release receipt
                          master / stage6a branch / stage6b branch HEAD
```

Stage4.2在提交历史上先于Stage4 checkpoint和Stage4.1，文档中的研究编号不表示时间先后。所有这些提交已从master可达。**没有单独Stage5/6A/6B提交**；三个分支同HEAD不意味着三个工作树内容相同。

## 未提交成果与快照选择

master工作树：tracked修改为pipeline.py、pipeline_contracts.py、docs/PROJECT_STATUS.md、docs/DECISIONS.md；两份历史ZIP已有删除（physics_mapping_stage1.zip、stage1_5.zip）保留。未跟踪新增scenarios.py、verification/scenario.py、场景测试/实验、Stage5文档和变量关系图谱等。真实源/实验不只在HEAD中。

Stage6A工作树继承原master的Stage5脏快照，加docs/stage6a、experiments/stage6a、test_stage6a_joint.py及状态/决策追加。Git raw status列出162个tracked修改，其中大量只是CRLF/LF，不能说162个算法改动。忽略行尾后的tracked语义修改限于两个状态文档、两个历史ZIP删除和pipeline/contracts两处Stage5适配。原正式算法/物理核没有Stage6A算法修改。

本包 **repo/** 以Stage6A为主快照：它包含Stage5适配及Stage6A真实研究文件。其运行核心与原master脏工作树按SHA核对；master补充历史证据在historical_support.tar.xz，具有完整成员SHA与安全展开脚本。Stage6B源码/实验另列source_variants/stage6b，不覆写repo。

Stage6B已实际添加multispec_constraints.py、multispec_search.py、pipeline研究路由、test_multispec_stage6b.py、运行/审计工具和B1/B2结果。另有tools/run_stage41.py将Git身份视为导出源码中的可选元数据，不修改其原M1/M2方程；变体中原样保存。其余大量raw .M仍是行尾差异。精确文件关系以module_origins和semantic_diff_summary为准。

## 每个核心模块的来源

|模块|实际来源/状态|
|---|---|
|physics_mapping/model.py|Stage1基础并入基线；本包按Stage6A实际字节保存，M1方程未因Stage5/6A改写|
|block_space/contracts.py、三份正式JSON|Stage1/1.5，固定合同与人工声明域；内容/版本SHA绑定|
|allocation/六算法模块|TrackA实现、Stage3A.1归正式所有权；兼容层track_a保留|
|verification/kernel.cpp/测量|TrackB提取，Stage3A.1正式归属；Protocol1.1维持；Stage4端口/4.1阶跃核另列|
|physics_mapping/registry.py|Stage4.2只读索引，已提交|
|pipeline.py/pipeline_contracts.py|HEAD版本叠加Stage5未提交场景/反馈适配；正式入口仍pipeline|
|scenarios.py、verification/scenario.py|Stage5未提交新增，不能丢弃后只打git archive|
|experiments/stage6a与联合测试|独立Stage6A未提交新增，研究判决/冻结计划/数据完整保留|
|Stage6B扩展|独立工作树未提交，完全单列，物化时记录每个覆盖/新增文件|

`provenance/module_origins.json`逐项保存原路径、实际SHA、相对HEAD的原字节/行尾等价/语义改动关系、三个工作树同名文件SHA、用途和适用域。`source_copy_manifest.json`记录全部原始复制来源；`raw_and_visual_copy_manifest.json`记录原始波形/图表；`historical_storage_index.json`将固实压缩的历史成员映射回原包路径，原字节可恢复。不可把原始绝对路径当成新环境必需路径。

## 缺失、未携带与保护

原树已删除的两个历史ZIP当前不存在，Git中有旧对象但本次未恢复/重新引入；它们不是运行依赖，对应源码与文本报告可访问。旧PLL_AGENT2/PLL_BASELINE字面目录并非实际来源，P0核对的实际目录名和原始SHA保留；不要求用户在新环境安装旧工程。

原版Git对象库、旧工程全仓、PDK/器件/大型早期RAW不在本包；必要的已提取源码、当前模型/配置/测试及阶段报告保留。Stage5/Stage6A原始数据的精确携带范围见EVIDENCE_COVERAGE；未携带不等于当前磁盘缺失。

最终保护检查对初始清单中的原文件逐SHA复查、对HEAD/branch/Git状态比较；主工作树仅过滤本次新增handoff_exports路径。结果见provenance/protection_after.json。任何外部并发修改也会如实列出，不静默宣称无变化。

## 打包期间的并发变化（已记录，不混合）

保护审计对master的14709份、Stage6A的15058份原文件复核，字节和Git状态均不变。Stage6B初始16776份保护文件中发现7份小文本被另一项并发工作更新，HEAD和分支不变：两个状态文件、两份Stage6B报告及package_stage6b.py/protect_stage6b.py/run_stage41.py。原快照保留；晚到字节单列source_variants/stage6b_late_observation，逐项SHA见provenance/stage6b_late_observation_manifest.json。Git新增交付/重现目录也在protection_after中完整列示，未冒充本次交接执行。

本包Stage6B冻结变体已有归档兼容测试，实际物化407项通过；同期晚到报告还描述其自己的六arm独立重现。这些是不同来源和执行事件，不将外部并发实验并入本次M2调用计数，不用晚到打包脚本静默替换早先版本。

最终补充存储索引evidence_metadata_storage_index.json将部分原相对路径映射到evidence_metadata.tar.xz成员；module/source清单中的原路径仍保留来源含义，不能假设每个历史侧文件均以散文件形态存在。
