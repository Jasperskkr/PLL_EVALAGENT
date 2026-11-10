# GitHub 同步报告 · 2026-11-10

用户授权将整个项目同步到 Jasperskkr/PLL_EVALAGENT，并明确保持私有。原目标 main 在 archive/github-main-before-20261110 保存；旧 phase1-schema-graph 保留。

## 已完成的准备

- 三个实际工作树分别建立快照；包含 Git 已跟踪和未忽略的未提交源码、报告、测试及结构化实验。逐文件 SHA256 与原 HEAD 见 FILE_MANIFEST_0/1/2.json。
- Git 对象使用 --no-filters 写入，保留源文件原字节；未做换行归一化。原目录仅被读取，原 Git HEAD/index/status 及冻结研究文件未改。
- main 基于原主工作树快照添加首页、阅读入口、知识交接文档与本同步记录；Stage6A/6B 独立发布，不合并算法。
- 常见 Token/私钥模式检查通过后才能提交。密钥、环境凭据未纳入发布。

## 数据覆盖

Git 保存可直接阅读的源码、配置、原研究报告、JSON/CSV/JSONL/测试记录。原 .gitignore 下的原始波形、历史 outputs 与 Track B 支持材料通过 Release 的去重证据对象和路径清单补充。编译产物、Python/pytest 缓存及 .git 内部文件不作为研究内容归档；Git 历史通过远端分支保留。

handoff_exports 中的重复解压/验证副本不逐个放入 Git；最终便携交接包作为 Release 附件。Stage6B delivery 和 experiments/stage6b.zip 为重复大包，最终通过已验收的 Stage6B 交付包附件提供。各附件 SHA256 由 Release 的 ASSET_MANIFEST.json 绑定。

## 验证与实际命令

发布准备：`python outputs/github_sync_20261110_01/prepare.py`。原树读取使用 `git ls-files -z --cached --others --exclude-standard`；逐文件 SHA256 检查与敏感模式扫描；对象使用 `git hash-object -w --no-filters --stdin-paths`；通过临时 index、write-tree、commit-tree 建立发布快照。远端覆盖使用带旧 main SHA 的 force-with-lease；其余分支正常更新。

上传后另行核对 GitHub refs、关键文档/源码、Release 附件大小及服务器 SHA256。最终发布回执作为 Release 的 FINAL_SYNC_RECEIPT.json 提供，只有该回执能证明上传验证已完成。本次不重跑研究仿真、测试或 LLM，不改变历史验收结论。
