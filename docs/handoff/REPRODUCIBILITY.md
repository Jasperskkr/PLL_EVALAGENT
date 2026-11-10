# 从上传包独立复现

所有示例路径相对包根。需要先解压；Windows建议较短路径如F:/PLL_HANDOFF，避免解压器的传统260字符限制。正式源码位于repo，依赖不读取旧工作树。原始文件/输出不可覆盖，下面NEW路径必须不存在。

## 0. 完整性与不依赖仿真的证据审查

```powershell
python -B scripts/check_bundle.py
python -B scripts/inspect_evidence.py --out evidence_review_NEW.json
```

第一条只验证包内逐文件SHA（允许解压后额外新增build/output）；第二条用Python标准库重查Stage6A候选/原始判决/包络及Stage5联合反例，不产生M1/M2/LLM调用。它不是“重新跑了历史仿真”。如需原master补充证据：

```powershell
python -B scripts/expand_historical_support.py --out F:/PLL_HISTORY_NEW
```

historical_support.tar.xz是**无损**历史小文件归档，展开逐项校验SHA；主要源码、Stage5/6A关键结构化证据和波形已在repo中，无需先展开它才运行最小复现。

## 1. 最小M1：不需要DLL、MATLAB或外部服务

Python>=3.11。M1/analytical纯标准库；Sensitivity本身调用完整M1，SLSQP另需NumPy/SciPy。

```powershell
python -B scripts/m1_smoke.py --out F:/PLL_M1_NEW
```

预期解析候选M1 BW225000Hz、PM72.247209838°、Vreq.6V、M1_SPEC_PASS。输出完整首次候选、M1、cost_events，M2/LLM均0。需要优化对照时：

```powershell
python -m pip install "numpy>=2,<3" "scipy>=1.14,<2" "pytest>=8"
python -B scripts/m1_smoke.py --with-slsqp --out F:/PLL_M1_SLSQP_NEW
```

只在你要准备新Python环境时执行安装。精确已测版本为Python3.12.10、NumPy2.5.3、SciPy1.18.1、pytest9.2.0；reference/requirements-reproduced.txt给出本次版本，不附wheel缓存，不声称其它版本/平台已验收。pyproject的基础dependencies为空，不能据此认为完整M2/SLSQP不需要NumPy/SciPy。原wheel数据文件清单不覆盖全部阶段研究资产，建议源码方式运行。

## 2. Windows原生M2与完整关键复现

需要Windows x64、MSVC2022 C++工具（原脚本固定VS2022 Community安装路径）、Python/NumPy/SciPy；`--tests`另需pytest。不需要PDK、ngspice、MATLAB运行时或LLM密钥。

```powershell
python -B scripts/reproduce_native.py --out F:/PLL_NATIVE_REPRO_NEW
```

脚本创建独立源码副本、核对SHA、从原C++重建3个核，然后执行5个完整M2：新Analytical首发、E1边界、E1修复、E2近轨/高Kvco。它从**本次新边界M2**调用原repair再生候选并重查M1，要求与冻结repair精确相等，再执行对应完整M2。记录命令/stdout/stderr、环境、cost、原始波形、研究重判、与历史逐字段比较；从不调用真实LLM。推荐上述不带--tests的命令：它已在严格无Git环境完成五点复现。可选--tests会先执行完整回归；原Stage6A有一项Git依赖失败，会中止脚本而不会继续五点M2，因此应按下段分别理解回归与最小复现。

原生build目录都要求不存在，不能把另一个commit的DLL拷来绕过身份检查；原脚本默认目录是build、build_stage4、build_stage4_1_r2。缺MSVC或目录冲突将保存真实失败，不能自动伪造fallback。若安装位置不同，在新副本明确适配原构建命令并记录编译器/source/binary身份；这种移植不属于本次已验收范围。

**本次实际执行分三组**：前两个无缓存独立副本各376测试通过、各5完整M2/534native，但可发现祖先.git，只能称新副本回归。随后设置GIT_CEILING_DIRECTORIES，并对输入与新副本实跑git探针均返回128；严格无Git下不带--tests的脚本又完成5完整M2/534native，候选/M1/全部M2指标/判决和新反馈再生repair全部与冻结记录精确相等。该环境独立全套pytest为**375通过、1失败**：tests/verification/test_closed_loop_stage41.py::test_holdout_rejects_wrong_source_lock_before_simulation，历史tools/run_stage41.py:141无条件读取Git HEAD，先于预期的source lock检查抛出CalledProcessError。冻结源码未改；详见reproduction_validation/strict_no_git_01/INTERPRETATION.md。

三组非测试合计15完整M2/1602native；严格一组native14.900346秒、pipeline内部48.107486秒、含复制/三次构建总脚本114.385086秒。真实LLM0、完整SystemSpec认证0。测试内部native未全面插桩，另列。完整本次分组与范围见reproduction_validation/FINAL_VALIDATION_REPORT.md，不能把原376通过概括为严格无Git全通过。

E1边界原正式FAIL，修复研究可行但原正式UNKNOWN；E2两点38/36µs。严格周期PM和±1µHz频率仍UNKNOWN。源/环境变化后末位或运行时间差异须如实报告，不能更换历史阈值追求精确数值。

## 3. 直接使用正式入口（已准备好新副本的构建后）

从新的repo副本根运行：

```powershell
python -B -m pll_allocation pipeline --strategy analytical --m2-budget 1 --repair-budget 0 --out outputs/baseline_NEW
python -B -m pll_allocation pipeline --strategy analytical --scenario experiments/stage5/scenarios/S1.json --m2-budget 1 --repair-budget 0 --out outputs/S1_NEW
python -B -m pll_allocation pipeline --strategy random --scenario experiments/stage5/scenarios/S3.json --seed 11 --m2-budget 1 --repair-budget 0 --out outputs/S3_random11_NEW
python -B -m pll_allocation pipeline --strategy analytical --scenario experiments/stage5/scenarios/S3.json --feedback-from outputs/S3_random11_NEW/attempt_001 --m2-budget 2 --repair-budget 1 --out outputs/S3_repair_NEW
```

最后一个例子用本次真实父失败反馈继续确定性修复，父调用不重复计新成本；预期BW能通过而PM仍不满足，要联合重查。wrapper CLI退出0代表正常执行，不代表PASS，请读result.json和每项constraints。

Stage6A冻结proposal仍嵌入基准正式SystemSpec，E1的窄BW/高PM与E2 deadline由study.joint_judgment施加。直接 `--proposal` 的正式结果不能自动当成窄研究判决；通用reproduce_native.py正确处理此区别。

重新生成M2前网格：

```powershell
python -B experiments/stage6a/study.py --analyze outputs/stage6a_analysis_NEW
```

它运行4725廉价公式点/条件shape/现有求解器与M1，不调用M2/LLM。历史collect.py/audit.py读取固定历史位置，适合原证据审查，不自动扫描任意NEW目录；不要盲目重启原driver覆盖历史路径。

## 4. Stage6B独立恢复

```powershell
python -B scripts/materialize_stage6b.py --out F:/PLL_STAGE6B_NEW
```

它复制repo，再把source_variants/stage6b叠加到这个**新目录**；每个同名文件的两侧SHA和显式覆盖动作记STAGE6B_MATERIALIZATION.json，两个源目录不变。随后按同一原build脚本构建，在该树跑tests；历史404测试。本次确实完成物化：279份核心源/配置/测试等逐字节一致，三个原始默认构建脚本成功，407测试全通过，源码变化0。权威回执为reproduction_validation/stage6b_materialization_02/SUMMARY.json与REPORT.md；_01保留早先的缓存/并发脚本差异失败证据。历史404是正式研究时的测试数，另3项归档兼容测试已在本次物化源码中。

Stage6B正式B1/B2重跑命令见独立docs/stage6b，原冻结计划/历史cache必须按原合同处理，输出和cache均用新目录；本次交接不启动新6B研究实验。不能混用6B pipeline与6A source hash后说“同一版本”。

## 5. LLM复现边界与常见问题

历史真实request/response/usage和JSON失败已保留；本包没有key/Authorization头或默认联网动作。新LLM首发须用户另行配置外部Messages服务环境，不能保证同候选或同token成本。保存proposal的 `--proposal` 重验属于EXISTING_PROPOSAL_REVERIFICATION，0新LLM；mock只能做接口测试。

原生缺失→按原脚本构建；hash mismatch→核对原字节和版本，不改冻结hash；目录已存在→选择NEW路径；pytest basetemp→先创建父目录；UNKNOWN→先读unsupported/包络/协议，不改门限；Registry行尾校验明确支持CRLF/LF，但native核心绑定仍按原byte SHA。部分旧打包/图表工具有Git/绝对路径假设；不带--tests的最小独立M2链已验证不依赖Git发现。

本次没有wheel安装、Linux/macOS M2、跨编译器、MATLAB新运行或真实LLM重请求验收；历史器件成果仅溯源，不是运行前置。

## 6. 历史测量侧文件的无损存储

为满足上传硬上限，早期阶段的结构化实验细节、全部raw测量JSON/CSV侧文件及若干大型保护清单，原字节合并存入evidence_metadata.tar.xz。没有删除核心源码、配置、测试或任何被选证据；原Stage5/6A候选、判决、汇总和全部已携带NPZ仍直接可读。逐成员原路径/长度/SHA见provenance/evidence_metadata_storage_index.json。

```powershell
python -B scripts/expand_evidence_metadata.py --verify-only
python -B scripts/expand_evidence_metadata.py --out F:/PLL_MEASUREMENT_METADATA_NEW
```

第二条仅恢复归档的侧文件，保持repo/与source_variants/原相对路径；输出是元数据补充树，与已解压主包对照阅读。它不是另一份完整源码工作树。最小M1/M2复现无需先展开；逐文件历史raw审计和依赖完整历史缓存的复用须结合该补充树，不可把侧文件缺少的直接路径误判为原证据丢失。
