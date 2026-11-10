# Stage7 GitHub 发布记录

2026-11-10：用户在Stage7交付后明确要求“请你把stage7的推进提交到GitHub仓库中”。该指令授权本次Stage7本地提交和推送，替代此前对本阶段不自动Push的限制；不授权启动Stage8。

发布前本地master与远端main/master均为 `e395f24859cdd81e3deb5ea83ba3f9598a27cd16`，GitHub默认分支为main。原Stage7源码、配置、测试和交付物的SHA256与验收清单一致，7份PhysicsContext通过公开loader和证据绑定核查。沿用已实际执行的513项全通过回归，不把发布前指纹复核称为重新运行测试。

本次提交包括Stage7代码、配置、测试、审计、接口说明、实验摘要及轻量代表证据，同时保存已被D024引用的开发前检查文档。大型实验、完整本地Diff和完整原始样本继续留在F盘experiments新目录，不将忽略目录整体加入Git。两份原有历史ZIP的未暂存删除不纳入提交。

发布增加.gitattributes的Stage7配置/证据保字节规则，防止Windows自动换行转换破坏已导出的SHA256绑定；不修改物理公式、模型、求解或测量代码。暂存后核对Git blob与验收字节一致，再普通提交，并向main/master执行原子快进推送，不强推、不合并。

`FINAL_RECEIPT.json`、`CHANGE_MANIFEST.json`、`PHYSICS_EXPLORATION_REPORT.md`保存的是Stage7验收时刻快照，其中“未Commit/Push/待用户验收”是当时状态，原字节和证据哈希保持。后续发布结果以 `experiments/stage7_github_publish_20261110_01/PUBLISH_RECEIPT.json` 的提交SHA和实际远端核验为准；本文件不嵌入自身提交SHA。
