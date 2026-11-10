# Stage6C Phase A — M1 noise model independent validation

2026-11-10，独立 verifier 执行。结论：**Phase A 连续理想 M1 噪声公式、单位、数值积分与已声明输入合同通过，可进入 Phase B 实现/验证**。本结论不包含噪声瞬态、非理想动态、采样环路噪声或严格周期稳定性认证；Phase B 原生扩展尚未构建或运行。

## 实际执行与版本

工作区 `C:/Users/Lenovo/.codex/worktrees/stage7-noise-nonideal/PLL_allocation`，目录名为此前审计标识；实施内容遵循完整 Stage6C 请求。环境 Python3.12.10、NumPy2.5.3、SciPy1.18.1、pytest9.2.0。

正式输入为 `configs/stage6c/frozen_01` 的17份预声明JSON。manifest文件SHA256为 `d58f5b1df1a99bd5a9e95c7443c4b64cf4a2068b4fa19d4aa03f3c7101c4d2cb`；两轮逐文件核验均匹配，未修改冻结配置。实际测试/source/config SHA、argv、stdout/stderr、JUnit在 `experiments/stage6c/phaseA_01` 和 `phaseA_02`。

实际命令：

```powershell
python -B -m pytest -q tests/test_noise_stage6c.py -p no:cacheprovider --basetemp=experiments/stage6c/phaseA_01/tmp --junitxml=experiments/stage6c/phaseA_01/tests.xml
python -B experiments/stage6c/phaseA_01/independent_physics_checks.py
python -B -m pytest -q tests/test_noise_stage6c.py -p no:cacheprovider --basetemp=experiments/stage6c/phaseA_02/tmp --junitxml=experiments/stage6c/phaseA_02/tests.xml
python -B experiments/stage6c/phaseA_02/independent_physics_checks.py
```

首轮20项通过，3.34s；独立审查发现两个有效输入合同盲点：表格频率中域外负锚点被接受并在log时警告，Nonideal的非字符串profile_id被接受。作者补全正频率与字符串metadata校验，并新增回归用例。第二轮 **21项通过，3.55s**；独立恶意输入探针现均明确拒绝。两轮旧记录保留。第二轮所测源/测试/配置运行前后SHA完全相同；verifier未修改模型、配置或测试。

## 独立物理与单位核验

独立参考直接求解两个电容节点与输出相位的闭环KCL线性系统，对 reference、free VCO phase、effective CP current和Rz串联电压分别注入单位源。没有调用生产transfer函数生成参考。覆盖9个原声明电容组合、每组29个1Hz–100MHz频率及4源，共1044次复数线性求解，最大相对复数差 `8.25e-12`。

单位检查：`Kpfd=Icp/(2π)` 为A/rad，`K0=2πKvco` 为rad/s/V；Href/Hvco是rad/rad、Hcp是rad/A、HR是rad/V。源单边PSD经模平方传递后为rad²/Hz；对Hz积分得rad²，然后 `sqrt(variance)/(2πfout)` 得秒。固定80MHz下使用N·fref，不混用反馈频率和输出频率。

R噪声为 `4kBTR` V²/Hz 串联电压源，在两个节点注入等量反向支路电荷，不能直接加为控制节点电压PSD。VCO相位谱 `100/f²` rad²/Hz对应 `Snu=100 Hz²/Hz`，后续随机频率离散化仍需独立原生验证。

使用独立nodal响应及自适应log-frequency积分核对四源10kHz–1MHz方差；生产2049点log梯形积分的最大单源相对差 `8.41e-7`。独立总jitter为 **77.684454927ps**，生产积分为 **77.684482648ps**。四源方差先相加再开根，支持线性独立源假设。已有测试验证源PSD乘4则jitter乘2、零噪声与原名义指标逐值相同、两边转单边乘2、SSB dBc/Hz转相位PSD的因子2、mesh收敛和BW噪声折中。

独立积分有限差分核对Rz敏感度：冻结所有源PSD时，jitter对Rz对数弹性 `−0.2864127540`；包含已知4kTR变化时 `−0.2863274910`；与生产敏感度的绝对差均小于 `4.11e-8`。这一区分保留，不能把其他源对Icp/Kvco的内禀噪声依赖解释为已建模。f0在当前理想传递模型中的动态零敏感度也已测试。

## 范围与后续门

所有17份实际冻结JSON均经独立验证，包括主测试静态参数表未单列的正/负leakage与compliance配置。锚定二次VCO静态模型在工作点保持目标频率，检查rails端点的正频率/正斜率，且对CP gain/reset参数作合法性约束。此处仅静态合同通过，不能证明波形、PFD reset/mismatch机制或捕获表现。

C1/C2是离散变量，敏感度接口明确要求枚举；Phase A没有进行离散噪声最优性搜索。旧Block Space的声明域仍须由未来Runner独立检查，M1噪声结果不是器件能力认证。当前参考源相互独立，相关噪声、未声明外推、零频积分、非法单位/非有限/负PSD不能通过。

本阶段原生M2调用0、LLM调用0。独立数值脚本只执行连续M1、线性系统与积分。Phase B/C须继续验证零扩展逐点兼容、非理想动态、噪声幅度/离散化、源独立性、锁定与滑周/限幅、统计置信及dt收敛；未经这些后续门，不得把M1的jitter结果改标为实测或Verified JointBlockSpec。
