# 历史工程保留计划

本轮归档采用原地只读索引，没有移动或删除历史文件。

- PLL_SPEC_ALLOC_BASELINE：保留冻结80/84MHz规格、Legacy Phase2、fixtures、MATLAB对照、正式runs与G1/G1.1历史；新代码不写入。
- M05主仓库及M05/M06/M07 worktree：保留分支与提交；不合并、不清理、不复位。新主线参考其有用架构，M06/M07不成为运行依赖。
- PLL_AGENTV2/PLL_AGENT：保留Formulator、模型卡、CP/VCO数据、MATLAB和实验；继承数据均记录真实路径及SHA。不得将其工作副本当成某个未经核实的提交。
- PLL_AGENT：保留其原有dirty状态，不能为整理项目而清理用户修改。
- PLLngspice_vs_matlab：保留CP、VCO、PFD/Divider电路、stage3–8模型/脚本及原始RAW。后续可以查阅模型来源，但本轮不新增晶体管实验。
- FactorGraph MATLAB：保留平均相位模型/扫参/图导出研究，数值协议与本主线不同，单独索引。

新目录仅复制小型必要代码/模型与验证参考，清单在data/legacy/legacy_manifest.json和data/verification_reference/manifest.json。旧大型RAW不复制；不以节省空间为由删除。以后若要打包归档，先生成包含路径、大小、SHA、角色和恢复方法的清单，再按用户要求处理，不能把隔离等同删除。
