# Stage 3A.1 结构审计与实施前方案

2026-11-04。依据用户Stage3A.1原文，本轮只迁移、适配、验证、提交和发布冻结，不新增模型/算法/测量。

初始父分支track-a/physics-guided-allocation，HEAD=e5bf67a032831d431819bce24177930179e431fc；Stage3A生产代码/配置/测试/报告未提交。Track B独立分支track-b/behavioral-verification，HEAD=dc661f6f7694562444438410f39190571b51a398，状态干净。只有一个父worktree。初始状态另存git_before.json。

与上轮已知状态相比，新增docs/stage3a.zip及stage3a_source_review.zip，可能来自共享工作区外部审查。保留两份既有ZIP删除及所有未跟踪发布包，不恢复、不删除、不混入提交；提交前再次比较指纹和状态，发现非授权变更则隔离报告。嵌套.git和历史outputs始终原地保留。

|模块|当前路径|最终路径|是否迁移|理由|
|---|---|---|---|---|
|解析/优化/敏感度|track_a/allocate.py、physics.py|allocation/allocate.py、physics.py|是，原代码移动|避免为目录命名拆分和重写数值算法|
|Proposal/Meter/M1适配|track_a/core.py|allocation/core.py|是|正式Pipeline不再导入旧路径|
|Agent/反馈|track_a/agent.py、repair.py、feedback_agent.py|allocation/同名文件|是|保持工具、提示词、transport及决策语义|
|旧Track A API|上述旧模块|旧路径薄兼容转发→allocation|替换为适配|旧脚本与测试继续可用，反向依赖禁止|
|Track A研究套件/报告|track_a/runner、benchmark、experiments、audit、report、__main__|保持历史工具位置|否|正式Pipeline不依赖；改为消费新正式算法，历史输出不动|
|事件模型/测量/验证|verification/|保持正式包|否|确认没有历史track_b依赖；数值代码和1.1协议不改|
|原Track B测试|track_b/tests|tests/verification|复制测试并仅改导入/资源定位|正式测试独立；原嵌套仓库只读|
|小型Track B参考|baseline/python_crosscheck.py、protocol1.0等|tests/fixtures/verification|逐字节或有SHA的投影|保留测试原阈值/协议差异，波形不迁移|
|Stage3A测试历史绑定|tests/test_pipeline_stage3a.py引用track_b|统一测试夹具及冻结hash|必要适配|不再要求整个研发目录|
|Pipeline/旧v1 Runner|pipeline.py / runner.py|同路径，明确主线/Legacy|仅改主线导入与身份记录|保留旧合同兼容，不让两套默认输入均称正式|
|配置|configs/pipeline_stage3a.json及其锁定资源|原路径权威配置|不变|保留模型/域/SystemSpec/协议和LLM环境配置|
|原生核/DLL|verification/kernel.cpp、build/|同路径|物理方程不变|检查构建及源码/二进制身份；仅Windows实测|

实施前先保存重要工作树备份ZIP与逐文件SHA，并保存完整旧树保护清单。再实际执行原四策略的M1基线及273项测试。迁移后自动审查AST/依赖、四策略候选及M1，执行名义/解析/优化/明确BW失败的真实M2及真实LLM首发；测试不得改阈值。正式测试读取小夹具而非历史输出作计算真值，历史记录仅用于显式数值比较。

最终新建codex/stage3a1-mainline-freeze分支，仅显式暂存审计过的源码/配置/测试/文档和精简证据。原始波形、构建缓存、嵌套Git、密钥与外部ZIP不进入提交。通过后提交代码冻结版本；RELEASE_MANIFEST.json及review ZIP为由冻结Commit生成的外部发布资产，避免Commit自引用问题。包内逐文件校验SHA，并确认与冻结Git对象相同。

最终交付根目录MAINLINE_ARCHITECTURE.md、INTEGRATION_VALIDATION.md、ARCHIVE_PLAN.md、RELEASE_MANIFEST.json及stage3a1_review_bundle.zip。根目录原架构文档保留于备份及Git父提交。阶段结果写docs/stage3a1与experiments/stage3a1*新目录；旧报告和数据不覆盖。完成后停止等待Leader。
