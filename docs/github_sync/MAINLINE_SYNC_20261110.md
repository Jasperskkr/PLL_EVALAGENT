# F盘主线归并同步（2026-11-10）

本轮用户要求：清理C盘旧PLL副本后，将F:/LJP/概伦AI/PLL_allocation中已集中Stage6A/6B的项目主干同步到Jasperskkr/PLL_EVALAGENT。F盘已经同时包含显式可选Stage6C；不退回历史6B快照，不新增平行Pipeline。

同步前身份：F盘master=e11a4b028ba052c6ce55eb227c4bb18397576c91；实现归并提交eb8cd11e4986554ed49085f8756841ea01fed9c3。GitHub默认main=8142930d16e01693cc031f1b7d957d90b5975028，master=86f83092474ff0dec425d201f3f598976e1735a2。此前Stage6A/B仅在独立研究分支，不代表默认main已经集成。

合并规则：以F盘已验收的所有共同路径原字节为准，保留远端独有的阅读文档/历史记录，保留main与F盘master两个父历史。远端没有独有的pll_allocation/configs/tests/tools/examples/data正式文件，故不引入第二套实现。README、状态/决策及首次阅读指南以当前F盘边界为准；历史快照和Release报告保留其当时语义。所有remote-only路径及冲突预览另记本地audit。

传输保留Git身份和父历史，不force-push；同时快进远端main/master到整合版本，保留旧Stage6A/B研究分支及Release。连接不稳定时，读取既有F盘Git对象缓存，并通过校验证书的Git HTTPS智能协议或GitHub API传输；不改系统DNS、不关闭TLS校验、不输出凭据。普通Git使用现有Git Credential Manager认证。

发布前检查：清理保护340文件零差异；理想/Stage6C Build Identity与pipeline --help通过。此前F盘/干净导出478项测试及真实默认/修复/扩展链验收见docs/mainline_integration_20261110_01/FINAL_REPORT.md，本轮不冒充重跑。合并后必须核对全部正式源码/配置/测试Git blob身份，确认默认pipeline和冻结资产不变，并检查待传输文件没有凭据或超限对象。

状态：实现归并与首次发布已完成，以下为实际验收；其后仅补交本验收记录。最终远端SHA由本地独立回执绑定，避免文档自引用。

## 实际发布与核验

- 整合实现提交：fe3c247731ba9be86794f78a8c0686b1bee5851d；父历史保留F盘与原GitHub main，原远端master亦是其祖先。旧Stage6A/B分支和Release未删除。
- 远端main/master已原子快进到该实现提交，未强推；传输251对象/175blob，Git pack为666,192字节，TLS证书校验保持，凭据只在内存中从Git Credential Manager获取。扫描未发现实际令牌/私钥形态或100MiB超限对象。
- GitHub API重新读取全量递归树，14,867个文件的mode/blob身份与本地提交逐项相同，差异0；332个正式源码/配置/测试/工具/必要数据文件在其中。Stage6A文档、Stage6B配置/搜索、Stage6C可选实现均存在默认主干。
- 合并后全tests：478 passed in 44.88s。清理前保护的340个源码/配置/DLL身份文件SHA仍无差异；理想/Stage6C Build Identity和冻结pipeline输入加载通过。历史实验不是本轮重跑；无新研究M2/真实LLM调用，测试内后端活动另列。
- 远端独有的历史文档/记录保留。8,892个F盘同名既存文件在导入前与远端原blob字节一致；41个非忽略文件按原blob身份接入索引，避免换行规范化覆盖。保留原两份ZIP未暂存删除，未reset/clean/stash。

原始合并/冲突预览、预审、完整远端树核验和发布回执在F盘experiments/storage_cleanup_20261110_01/github_audit。轻量测试证据见../storage_cleanup_20261110_01/TEST_SUMMARY.json。后续以F盘master开发，并沿用唯一pipeline入口。
