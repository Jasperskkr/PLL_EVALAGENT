# Stage 7 Implementation Design — 2026-11-10，正式实验前

## 请求与安全边界

收到附件实际9789 bytes/5465字符，正文在4.3第4条“明确去除的名义载”处截断。已请求补全。先实施已明确P0–P3以及顶层要求的可选统一pipeline接入；缺失后半部分的实验/验收要求不虚构为用户指定。

隔离managed worktree `stage7-noise-nonideal`，分支`codex/stage7-noise-nonideal`，master/HEAD基底cd70cf4。Stage5/6A/6B尚未提交，完整基线不能用HEAD表示。原ZIP03已不存在于原路径；保留失败记录，验证仍存在ZIP02 SHA c22e37c83b6308c638d9dbaa9c543f50f18bbab439b89a5f03ac6cb3b5d60733，恢复12491文件/984477647bytes，再精确覆盖当前源码/config/tests/tools。源Stage6B只读、未提交/清理/stash/merge。receipt/current-source复用路径/SHA见experiments/stage7/safety_02。

## 实现位置与兼容

保持physics_mapping/model.py、Registry、原Block Space合同、allocation/allocate.py/Stage6B搜索、kernel.cpp/closed_loop_kernel.cpp、simulator.py/verify.py和protocol1.1原字节。新增block_space/extensions.py定义外置版本化NoiseProfile/NonidealProfile；不把非理想量塞入旧完整候选。新增physics_mapping/noise.py复用原_response/evaluate，返回来源分量/方差/显式频带jitter/敏感度。

在verification/新增可选原事件核扩展：stage7_kernel.cpp包含原kernel.cpp，扩展函数由原源码确定性变换生成，记录变换与源SHA，不独立维护第二套PLL方程。所有非理想和噪声关闭时直接调用原simulate，逐点完全兼容。阶段扩展使用新build_stage7目录和显式模型版本，不覆盖旧DLL。新增stage7_native.py、noise.py作为既有verification包中的可选adapter/measurement；不调用M1噪声传递函数生成波形。

pipeline.py增加显式stage7配置路由，唯一正式CLI仍`python -m pll_allocation pipeline`。原路径默认不变；扩展Runner仍独立负责完整候选/旧域、预算、首次落盘、仿真、逐指标判决与trace。先完成验证机制，再决定顶层分配比较，不声称补全附件未给出的噪声系数/门限。

## M1公式、源合同与验证

采用任务给定L/Z/H_ref/H_vco/H_cp/H_R/D_R，Hz/V与rad/s/V转换显式。四个独立源按单边PSD传播和方差相加，jitter=sqrt(phase variance)/(2π80MHz)。LF电阻热噪声4kTR，KCL独立检查串联R噪声源，branch=(v-u-e_R)/R；该支路对两个电容注入等量反向电荷。输入支持white、power_law、多项幂律/表格loglog内插；禁止无授权外推、零频、负/非有限PSD、相关源和不匹配单位。dBc/Hz使用2*10^(L/10)，双边密度转换单边时乘2。

敏感度A：固定参考/VCO/CP NoiseProfile，变化原BlockSpec后重算传递；B：不凭空建立Icp/Kvco源噪声依赖。R热噪声已知4kTR单独报告其随R变化的物理贡献。C离散枚举。区分固定源PSD的传递敏感度和包含已知R热噪声变化的总敏感度。

## 非理想机制

外置Kvco2/CP mismatch/leakage。原上下管符号与分段脉冲电荷保持；Iup/I down各自计脉冲。VCO在实际相位积分使用f0+KvcoV+Kvco2V²；检查全电压域正频率/正局部斜率，求唯一内部调谐根并保存局部Kvco。非单调多根先UNSUPPORTED。记录限幅损失、注入电荷、相位/边缘连续性；验证正负单项及双步长。未实现PFD reset或门控噪声不伪称支持。

## 随机过程与独立测量

Reference第一版在10MHz参考相位采样点生成独立白相位序列并连续线性插值，低于参考采样率0.1倍频带内作为白相位近似，保留sinc整形/采样适用限制。拒绝非单调/重复边缘，不静默修补。VCO白频率噪声Snu的每步频率σ=sqrt(Snu/(2dt))，相位增量方差=(2π)^2Snu dt/2。CP是连续有效输出端白电流，非导通PSD；R热源为series voltage，按实际LF状态更新。独立可复现随机流/种子，零源不消费噪声路径、不改变原核。M2仅支持white Reference/CP、1/f² VCO和热R；1/f³/table仅M1可算，M2显式UNSUPPORTED。

新Noise Protocol预声明：原160us配对冷捕获先作lock gate；独立噪声运行用确定性200us启动预热，预热结束前重新确认lock，然后新4ms稳态观测。输出相位误差是实际VCO相位减名义2π80MHz*t，常数均值移除；不去线性斜率隐藏频差。存等效时间误差与原波形、Welch单边PSD、显式10kHz–1MHz积分；20ns记录，nperseg16384，Hann/50%overlap、constant detrend。频率/采样/窗口与初态全部绑定，频带端点插值，seed11/23/47。比较PSD/方差分量、多个seed统计CI和dt .4/.2ns，不要求独立随机轨迹点对点相同。短窗口/不锁/滑周/限幅/数值或统计未收敛返回UNKNOWN，不用M1代替M2。

这些观测时长/频带/seed是当前实现预声明研究协议，非缺失附件的既定指令。先用零噪声/自由运行VCO/单源校验验证单位与离散化，再冻结研究NoiseProfile与约束，任何变更另记版本和独立目录。谱估计置信区间是声明高斯平稳假设下近似，不是跨PVT保证。

## 验证与推进

使用analog-pipeline要求的独立verifier执行所有仿真。第一步重新构建原三核及407历史测试，核对Stage6B默认首发/反馈结果。新增M1极限/独立KCL/单位/积分/方差加和/敏感度测试；非理想逐机制、零扩展逐点、随机幅度/diffusion/seed/边缘/步长/独立Welch测试。开发失败保留。每阶段先落盘设计/config/schema/测试再推进正式实验。完整trace保存真实成本、拒绝和UNKNOWN，最终报告区分已完成、部分完成、等待缺失正文的要求；不把M1PM或有限轨迹稳定性升级严格周期稳定性认证。
