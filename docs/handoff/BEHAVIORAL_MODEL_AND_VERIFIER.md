# M2 行为模型、测量与认证边界

## 1. 当前M2是哪一个模型

正式M2是 `repo/pll_allocation/verification/kernel.cpp` 的 simulate，经simulator.py/ctypes调用。它从历史 `python_crosscheck.py::simulate` 提取边沿/Euler更新顺序，并加入相位激励和观测。它不是ngspice，也不是旧 `_legacy/evaluation/python_behavioral.py` 的逐参考周期精确RC传播；后者仍为早期案例/历史回归保留。

**是固定时间网格加步内事件插值，不是完全自适应事件求解器。** 两个LF状态v（控制节点）和u（串联C2节点）、VCO相位phi、PFD up/down及下一个ref/div边沿序号构成状态。默认冷启动v=u=.15V、phi=0、up/down=false；没有把M1稳态解作为冷捕获初态。

每步先用旧v得到f=f0+Kvco·v和相位预测；参考相位为2πfref t，加onset后的小相位正弦。反馈相位phi/N，理想Divider通过相位连续除N表示，而非计数器延迟模型。跨整周期时线性插值定位边沿；若同一dt多周期或参考相位不单调则失败。

PFD参考上升沿置UP，反馈沿置DOWN，两者都置位立即复位，无reset delay/死区。按插值事件顺序分段累积 `I*(up-down)` 的平均步内电流（代码变量area已按dt归一化，并非库仑）。CP理想等幅±I，非零失配/漏电/q0不支持。

LF branch=(v−u)/R，采用旧状态显式更新：

\[
v_{k+1}=clip\{v_k+dt(\bar i_{CP}-(v_k-u_k)/R)/C_1\},\quad
u_{k+1}=u_k+dt(v_k-u_k)/(RC_2).
\]

VCO相位 `phi += 2π f_old dt`。控制节点v限幅0–1.2V，u保留电容状态；clamp事件、near rail计数和终端相位诊断显式记录。记录轨迹列为时间、phi/N−2πfref t、参考调制相位、v、u、累积clamps，并保存ref/div边沿时间戳。

Python准入要求fref10MHz、N8及原rails；dt·LFpole_rate≤.05且dt·max(fref,fmax/N)≤.02，正频率/有限数/合法采样和单调激励。积分点≤2e8。模型超域、缺native或任何非零返回码都明确报异常，不存在伪造PASS后备。

## 2. C++与Python接口、构建身份

`simulator.simulate`组装17个原生参数/设置的double向量，分配trace/ref_edges/div_edges/summary NumPy数组，通过ctypes.CDLL调用导出simulate。编译目标为Windows/MSVC C++17 `/O2 /EHsc /LD`；源码使用`__declspec(dllexport)`，库路径固定verification/build/kernel.dll。

原 `build_kernel.cmd`使用本机VS2022 Community固定vcvars64路径，拒绝覆盖已有构建目录；build_identity.py保存源码和DLL SHA，simulate每次check_build。独立相位端口核和阶跃核也有原build_return_ratio.cmd/build_closed_loop.cmd与身份检查。包中保留源码和构建脚本，不依赖旧工程、PDK、ngspice；不把本机DLL视为跨平台可移植后端。MSVC路径变化需在副本/开发者环境单独适配并记日志；不能绕过hash检查。

## 3. 闭环BW测量：真正的激励与判据

`experiments.response_point/response_sweep`在**局部暖启动**Vreq处运行（仅用静态频率法则求Vreq）。50µs后参考相位注入0.01rad正弦。基础18点10kHz–1MHz，低频锚若不在1±3%内再测5kHz、2kHz；交越后仅在实测括区几何二分，最多16次，以括区相对宽度≤0.0005为细化停止目标。最多16次细化后返回，最终汇总器没有额外的宽度强制门；本阶段实测括区均达到该目标。不用M1预测BW来选交越答案。

丢弃max(40µs,8/f)后测12周期。measure.response_metrics以offset+trend及f、2f、3f的sin/cos最小二乘拟合。定义Tmeas为连续分频输出相位基波/实际参考相位基波；单位归一化后找唯一向下 |T|=1/√2 交越，log频率/幅度插值得BW。边沿时间戳拟合可能给不同采样响应，本可观测量与edge-only等价尚未建立。

质量门：至少100点、每周期≥20样本、注入前局部锁定；THD≤3%、两半窗复传递差≤2%、残差/基波≤5%、未包裹误差峰值≤.3rad、测窗无clamp。任何门未过，点或整体UNKNOWN。

完整BW包含四套独立 sweep：base(.01rad,.4ns,12周期)、半幅(.005rad)、半步(.2ns)、双测窗(24周期)。所有测点/括区须有效；变体BW差≤2%、同频复传递差≤3%、相位差≤1.5°，比较频点≥3。`comparison_after_measurement`在所有事件测量结束后才调用M1。

数值包络取所有变体括区的最小下端/最大上端，再向两侧各扩展各变体BW估计值的spread。它覆盖这些数值变体，**不覆盖跨可观测量定义差、全部模型误差或器件误差**。包络完全落在目标内才PASS；越界但有交叠是UNKNOWN。暖启动小信号BW不能证明冷捕获。

## 4. Conditional Capture / Lock Time

原Protocol1.1固定160µs冷启动窗口、.4/.2ns两步长、20ns记录；每10参考周期为1µs块。块要求输出频差≤100ppm、最近整数周参考下的包裹相位峰值≤5°、控制电压范围≤5mV、无clamp且cycle index不变。最终至少10个连续有效块（10µs），lock_time是这一终端持续序列最早起点。早期clamp/cycle slips不自动否定终端锁定；窗口后未知。

两步长须状态一致、频率差≤1ppm、控制均值差≤1e-4V、锁定时间差≤2µs。否则UNKNOWN_NUMERICAL_CONVERGENCE。NOT_CAPTURED_WITHIN_WINDOW、LOST_LOCK_WITHIN_WINDOW不是绝对不可锁证明。固定初态结果不代表多初态/多扰动捕获盆。

Stage6A额外40µs deadline在首个新M2前冻结，按coarse/fine时间hull加1µs块分辨率构造区间，再作区间判决。E2近轨点为[37,39]µs，满足deadline；没有捕获失败，因而未执行捕获repair。Stage6B使用fine±步长差±1µs保守区间，另有跨40µs的UNKNOWN实例；不要混改Stage6A原定义。

## 5. UGF/PM 局部工程测量与正式缺口

原BW闭环 `T/(1−T)` prototype只能给条件LTI反演诊断，正式PM=null/PM_M2_UNKNOWN。Stage4进一步在divider/PFD相位端口作Series/Clamp正负激励、差分拟合、pilot恢复DC初态，测局部复数返回比、交越及谐波转换。Stage4.1又加平滑参考相位阶跃并对固定10点核对恢复/振铃。

这些局部指标数值接近M1，幅度/步长/窗口诊断也收敛；但反向fref±f→f转换近1，完整谐波返回矩阵、广义Nyquist/Floquet稳定性还未建立。Series有效标量返回比与Clamp的L00并非天然同一周期稳定性指标。`return_ratio_validity.make_extension/load_extension`强制正式UGF/PM值为null、状态UNKNOWN，只保留diagnostic_series_value/direct_clamp_value，不准升级SystemSpec认证。

## 6. 输出频率、静态相位、噪声与功耗

频率用末端hold窗中分频相位斜率恢复 `80MHz+8·Δphase/(2πΔt)`。经验包络为±max(.01Hz,2·|f_fine−f_coarse|)；required_precision_validated=false。捕获100ppm阈值不是SystemSpec±1µHz精度的替代品。即使两组BW只差数µHz，也不能声称测量精度达到µHz。

严格频率通常UNKNOWN；若收敛末端频率明显偏离80MHz超过8000Hz，才可据代码的保守条件判可靠FAIL。存在偏差诊断或理想频率法则并不产生精度PASS。

Static Phase Error：内核/旧周期模型有相位均值/RMS/峰值诊断，旧q0模型也有电荷平衡初筛，但当前六轴理想域q0等全零，没有正式独立静态相位误差分配/认证协议。不能把终端5°capture门当静态精度规格。

Jitter/Power：无噪声注入/PSD积分、独立抖动测量或模块供电消耗模型。轨迹相位RMS是确定性捕获/跟踪诊断，不是时间抖动；Icp也不是整机电源电流。RUR未定义。以上均UNSUPPORTED。

|类别|当前支持证据|可否正式整机认证|
|---|---|---|
|M1预测|80MHz规划、Vreq、连续BW/UGF/PM|仅M1，不是M2|
|M2可测量|局部归一化BW及收敛包络，条件capture/lock、终端频率/Vctrl|BW可按协议判单项；capture仅声明条件|
|M2局部工程证据|Series/Clamp UGF/PM、谐波探针、阶跃恢复|不能正式周期PM/UGF PASS|
|未正式认证|严格周期PM、±1µHz频率、静态相位精度|UNKNOWN|
|未支持|Jitter、Power、RUR及非理想域|UNSUPPORTED|

## 7. 成本、重复性与共同理想化

一次完整M2不是一个C++调用：双步长capture加四套频响/自适应测点。Stage6A为8次完整M2/852 native，额外重复capture2次，总854次/23.279原生秒；完整pipeline内部77.276秒、进程84.348秒。M1正式扫描中位数约34.10ms，廉价代数约57.8µs；它们是该机该阶段的实测，不是跨平台保证。

确定性输入/相同编译器可以重现语义结果，时间和路径身份必然变化，浮点/库/编译器变化可能影响末位。真实LLM不是确定性可离线重现；保存proposal重验可复现M2，不能记作新请求。每次requests、summary、measurement、complete、trajectory与成本必须分层保存。

M1/M2共享理想CP/PFD、线性VCO、理想divider、两状态理想RC、零非理想参数及同一单位/拓扑。M2在时间/边沿测量上独立，不是高保真器件真值；二者一致只能支持这类理想模型内的实现/近似一致性。尚需独立高保真参考、适用域/误差边界、多初态和非理想建模来建立外部可信度。
