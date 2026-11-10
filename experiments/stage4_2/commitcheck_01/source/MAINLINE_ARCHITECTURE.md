# Stage 3A.1 正式主线架构

本阶段只做迁移、回归与发布冻结。PROJECT_CHARTER.md保留研究原文；阶段授权见docs/stage3a1/TASK_REQUEST.md和D010。

```text
configs/pipeline_stage3a.json        唯一正式配置入口及版本/Hash绑定
  BLOCK_SPACE_MODEL_V1.json         冻结Stage1.5域、拓扑、模型语义
  SYSTEM_SPEC_STAGE1_5.json         model.experiment.system_spec的同内容投影
  PLL_EQUATION_REGISTRY_V1.json     冻结方程注册
  verification/protocol_v1_1.json   原测量协议1.1
pll_allocation/
  block_space/                     加载、声明域与模型有效域检查
  physics_mapping/                 冻结正向物理方程与M1计算
  allocation/
    core.py                        Proposal、M1适配、预算和计数
    physics.py                     原解析物理关系与反解
    allocate.py                    原解析/敏感度/SLSQP/随机策略
    agent.py                       原工具型Agent、提示词、真实Messages接口
    repair.py, feedback_agent.py    原确定性修复及反馈解释工具
    __init__.py                    Policy协议及策略适配
  verification/                    独立接收Proposal，事件核、测量、判决
  pipeline_contracts.py             输入、结果、协议/Hash绑定及反馈投影
  pipeline.py                       正式Runner：约束、TB、预算、判决与写盘
  cli.py, __main__.py                CLI分流
  track_a/                          六模块向allocation转发；历史研究CLI保留
  runner.py, policies.py, behavioral.py  Legacy v1及原协议
tests/verification/, tests/fixtures/ 不依赖整个Track B的28项正式回归及小型参考
experiments/<new_run>/              新建运行、拒绝覆盖；raw轨迹与代码分离
track_b/, outputs/                  只读历史证据/嵌套Git；非正式运行依赖
```

调用链：`load_inputs()`核对冻结绑定 → `AllocationStrategyPolicy.propose()`返回完整JointBlockSpec → Runner先保存`initial_joint_block_spec.json` → 域检查 → `assess_m1()` → `AllocationProposal` → `verification.verify()`真实捕获及四组频响扫描 → `BehavioralVerificationResult` → `make_feedback()` → `receive_feedback()`实际进入原反馈解释层。允许修复时原repair返回完整新候选，重新执行完整TB。

Policy不拥有判决权；Verification不调用分配器或Agent测量。M1仅作为显式posthoc对照，不作M2实测值。FIRST_SHOT、FEEDBACK_REPAIR、M1_VALIDATED/M1_PASS、M2_PARTIAL_PASS、M2_FAIL、M2_UNKNOWN分别记录。BW PASS时PM、UGF、微Hz频率认证仍UNKNOWN，整体不是Verified JointBlockSpec。

## 执行与接口

Python≥3.11；实测Windows/Python3.12.10/NumPy2.5.3/SciPy1.18.1/pytest9.2.0，原生后端需MSVC2022 x64 C++17。跨平台及wheel安装NOT_VERIFIED。

```powershell
# 新源码目录已具备上述Python依赖，构建目录必须尚不存在
& .\pll_allocation\verification\build_kernel.cmd
python -m pll_allocation pipeline --strategy analytical --out experiments/new_analytical
python -m pll_allocation pipeline --strategy sensitivity_optimization --out experiments/new_optimized
python -m pll_allocation pipeline --strategy random --out experiments/new_random
python -m pll_allocation pipeline --strategy nominal --out experiments/new_nominal
python -m pll_allocation pipeline --strategy llm_agent --out experiments/new_llm
python -m pll_allocation pipeline --strategy random --m2-budget 2 --repair-budget 1 --out experiments/new_repair
```

LLM配置仅存环境变量名、调用次数/超时，默认读取ANTHROPIC_MODEL、ANTHROPIC_BASE_URL、ANTHROPIC_AUTH_TOKEN。提示词/工具原字节保留，其中M2 deferred是原Agent边界：提交后外层Runner真实执行M2，不为本阶段成绩改提示词。真实LLM自动反馈修复未实现，会明确停止；确定性修复已实跑。

Python入口`run_pipeline(out, strategy, config_path=None, proposal_path=None, m2_budget=None, repair_budget=None, llm_config=None, policy=None)`；Policy实现`propose(model, system_spec, meter, out, history)`及`receive_feedback(candidate, feedback)`。proposal_path仅为既有Proposal复验，记录EXISTING_PROPOSAL_REVERIFICATION，不能算新LLM。`verify(proposal, out)`可独立调用，拒绝版本混用/不支持条件。

每次运行包含输入/配置/源码清单、第一次候选、各次M1/M2/差值/状态、决策/工具日志、反馈回执、搜索/仿真/失败成本；raw/轨迹留本地不入代码提交。构建记录绑定kernel.cpp及DLL的SHA，加载前核查。构建脚本拒绝覆盖已有目录，可指定全新构建目录用于审计；正式加载位置仍为verification/build/。

Legacy `python -m pll_allocation run/suite`和`python -m pll_allocation.track_a`只维持原测试/历史协议兼容。新研究只使用pipeline，历史默认目标不能与Stage1.5混称正式输入。迁移来源/语义/适用域见docs/stage3a1，历史处理见ARCHIVE_PLAN.md。
