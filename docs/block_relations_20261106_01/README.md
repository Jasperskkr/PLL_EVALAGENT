# 当前 PLL Block 变量—关系—范围图谱

2026-11-06。依据用户表格参考请求完成；最新可审阅版本为 **atlas_03**。

- [打开排版总表（HTML，可离线阅读/打印）](atlas_03/VARIABLES_AND_RELATIONS.html)
- [完整说明与推导（Markdown）](atlas_03/VARIABLES_AND_RELATIONS.md)
- [表格预览（PNG）](atlas_03/TABLE_PREVIEW.png)
- [机器关系目录（JSON）](atlas_03/relation_atlas.json) / [41项变量（CSV）](atlas_03/variables.csv)
- [九个电容组合（CSV）](atlas_03/capacitor_domains.csv) / [条件域和完整示例（JSON）](atlas_03/conditional_domains.json)
- [核验结果](atlas_03/validation.json) / [复用源路径、SHA及语义](atlas_03/source_manifest.json)

## 已完成

按 System / 假设 / PFD / CP / LF / VCO / Divider / 环路 / 联合域 / TB 的层级建立18组关系，覆盖全部41项原变量。保留17项输入中6自由变量、4固定条件、7零非理想假设的区别。每项有原ID、单位、正向关系、条件反解、范围/域条件和证据边界；P/K/C_sum/q等辅助量只作为派生符号。

原轴范围完整保留：Icp 50–200µA，Rz 2–8kΩ，C1为50/100/200pF三选，C2为0.5/1/2nF三选，f0 60–76MHz，Kvco 10–40MHz/V。新增派生量边际极值/离散集合，明确不得将边际端点重组为联合可行点。

条件域落实为可计算的相交关系：

1. **VCO 调谐**：严格内部电压，给定Kvco后求f0开闭端点；Kvco=10MHz/V时必须f0>68MHz，等号在rail而无效。
2. **PM 与电容比**：PM≥50°要求C2/C1≥6.548632；原九对中(100pF,0.5nF)、(200pF,0.5nF)、(200pF,1nF)三对无满足此PM的形状，原声明输入仍保留。
3. **动态联合域**：给定电容对及x，先解原β数值根，再交BW目标、Rz范围和Icp·Kvco乘积范围，避免只满足一项公式就宣布可行。
4. **CP/VCO 分摊**：按产品P求Kvco/Icp交集，再交f0与控制电压；固定产品保持理想动态并不自动保证给定f0可调谐。

给出各电容对在PM峰值x=√q处的BW联合切片。例如50pF/0.5nF为212.382–300kHz，100pF/2nF为150–269.483kHz，200pF/2nF为150–212.382kHz。这些是指定形状切片，**不是该电容对所有形状的全局BW边界**。

## 实际核验

按预声明的规则，对6个PM可达电容对各取log-x区间15%、50%、85%处，共18例。6例联合交集为空，原样保存；其余12例从联合区间中点重建完整17量候选，原Constraint Checker和正式M1均通过。最大BW重建相对差8.54e-13；独立二节点KCL求解对BW/UGF交越的最大残差1.27e-12。该误差是数值实现一致性，非M1相对真实行为的误差界。

新增测试覆盖严格调谐端点、固定f0导致的空产品分摊、离散电容负对照、PM合法但联合域为空、不同带宽重建、独立KCL交越、拒绝电容插值/非法形状、拒绝覆盖和41项语义覆盖。与原Block Space、Mapping Registry、Allocation相关回归合计 **83项通过**。新工具不接入生产流程，故没有为本次表格变更重跑整套M2研究。

## 已完成、部分完成与待验收

**已完成**：当前输入域和已实现理想物理关系的块级总表、条件域参数化、派生范围、机器目录、有限M1重建核验、相关回归及HTML视觉检查。

**部分完成**：完整行为级可行域仍只有历史有限点/协议证据。Stage4.1十个局部完整参数点的支持已链接，不扩大成超矩形；本轮未开展新M2或新LLM。正式PM与1µHz频率认证仍UNKNOWN；不签发Verified JointBlockSpec。Jitter/Phase Noise/Power/RUR及非零非理想域仍需定义/模型/协议，未填入任意经验范围。

**待验收**：用户/技术Leader审阅本图谱的字段、符号及用途。此次授权不包含改变原范围/拓扑/目标、自动注入Agent提示词或继续Stage5.1/6。无需以这些后续事项作为本次文档交付的前置条件。

## 真实命令、成本与开发记录

三次生成均写入新的目录，旧结果无覆盖：

```powershell
python tools/build_block_relation_atlas.py --out docs/block_relations_20261106_01/atlas_01
python tools/build_block_relation_atlas.py --out docs/block_relations_20261106_01/atlas_02
python tools/build_block_relation_atlas.py --out docs/block_relations_20261106_01/atlas_03
python -m pytest -q tests/test_block_relation_atlas.py tests/test_block_space_v1.py tests/test_mapping_registry_stage4_2.py tests/track_a/test_allocation.py -p no:cacheprovider --basetemp=docs/block_relations_20261106_01/test_tmp_01 --junitxml=docs/block_relations_20261106_01/tests_01.xml
python -m pytest -q tests/test_block_relation_atlas.py tests/test_block_space_v1.py tests/test_mapping_registry_stage4_2.py tests/track_a/test_allocation.py -p no:cacheprovider --basetemp=docs/block_relations_20261106_01/test_tmp_02 --junitxml=docs/block_relations_20261106_01/tests_02.xml
```

三轮生成每轮12次正式M1及24次β数值根，合计36次M1/72次β；数值完全相同，是开发复验，不是36个独立样本。两轮测试分别81/83通过，第二轮增加边际离散集合与拒绝覆盖检查；测试内部M1另属于回归成本，未逐函数汇总，不计独立研究样本。生成器及所选回归均无新M2/真实LLM调用。

atlas_01候选生成计数字段最初为0，实际已重建12点；atlas_02修正计量字段，数值/候选不变。atlas_03补齐派生边际范围、上下标排版，澄清V0是旧上下文及verified域须全部指标PASS。每版保留当时源SHA，最新版以atlas_03为准。一次临时源码目录检查脚本把variables字典当列表迭代，TypeError后改为正确字典读取；此时无M1/M2/LLM。外部一级资料检索HTTP403，未读到文献，不引用其背书。

HTML由本机Edge headless离线渲染，两次退出码0；初版atlas_02和最终atlas_03截图分别保存。最终已目视检查公式上下标、列宽、换行、九对电容表及上下边界，无裁断/重叠。Edge一次记录后台task_provider错误日志但截图完成，未影响文件内容。

原tracked文件保护按本轮开始时SHA比较，允许的既有文件变化仅DECISIONS/PROJECT_STATUS追加记录；旧源码、冻结输入和历史tracked实验无变。原未提交Stage5、既存ZIP删除及其它未跟踪产物保持。最终检查见`protection.json`；保护范围是本轮开始的5768个tracked条目，不冒称对旧项目目录和所有ignored文件重做了全量审计。
