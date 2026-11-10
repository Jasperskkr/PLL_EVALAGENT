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

发布准备：`python outputs/github_sync_20261110_01/prepare.py`。原树读取使用 `git ls-files -z --cached --others --exclude-standard`；逐文件 SHA256 检查与敏感模式扫描；对象使用 `git hash-object -w --no-filters --stdin-paths`；通过临时 index、write-tree、commit-tree 建立发布快照。初始 CLI push 使用带旧 main SHA 的 force-with-lease，但大包传输未完成；最终 Git 引用更新同样核对远端旧 SHA，并以校验后的对象分批传输。

上传后另行核对 GitHub refs、关键文档/源码、Release 附件大小及服务器 SHA256。最终发布回执作为 Release 的 FINAL_SYNC_RECEIPT.json 提供，只有该回执能证明上传验证已完成。本次不重跑研究仿真、测试或 LLM，不改变历史验收结论。

## 大附件传输适配

长连接上传曾出现 HTTP 408 / TLS EOF，未改变原始文件。其余大附件改为 8–32 MiB 分片；实际片段与 SHA256 对应见 [TRANSFER_MANIFEST.json](TRANSFER_MANIFEST.json)，恢复方法见 [README_ASSET_TRANSFER.md](README_ASSET_TRANSFER.md)。先重组原始附件，再使用 restore_evidence.py 恢复研究目录。Git 历史对象分批传输后发布原始快照提交，临时传输分支在最终验证后删除。

## 实际传输与恢复核验

最终执行 git_api_batch.py --data-only、transfer_small_blobs.py、publish_final_git.py、release_transfer_v2.py 与 finalize_sync_v2.py。网络 HTTP 408、TLS EOF、DNS 和 GitHub 临时 unpack 失败均按已确认远端状态重试；完整上传后才发布 Release 回执。大对象通过 GitHub Git Data API 验证原 Git blob SHA，小对象使用原生 Git pack 协议传输，最终发布保留原始历史与三个工作树快照，不改写研究源码。

verify_transfer.py 已验证全部18份原始附件、473个实际传输片段的本地逐片 SHA256 和重组原文件 SHA256；总原始附件字节为6318771435。Release 中 TRANSFER_REASSEMBLY_VERIFICATION.json 保存本地结果，FINAL_SYNC_RECEIPT.json 保存实际远端结果。此次为一次快照同步；以后新增进展需要再次提交和推送。
