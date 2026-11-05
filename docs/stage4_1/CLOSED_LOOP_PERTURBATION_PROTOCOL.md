# Closed-loop Phase Perturbation Protocol 0.1

首次Stage4.1 M2调用前预声明；机器权威配置 `configs/verification/closed_loop_stage4_1_v0_1.json`，原Protocol1.1及Stage4协议不变。

- 初值：v=u=(N fref−f0)/Kvco，phi=0，PFD清零。先独立零扰动运行，检查20–40µs工作点，再执行同初值闭环阶跃。不是冷启动/频率阶跃。
- 输入：40µs起，0.5µs raised-cosine相位坡，r=A[1−cos(pi(t−onset)/rise)]/2，之后A。A=±.01、±.02rad，dt=.4ns；±.01rad另跑dt=.2ns和160µs后观测；常规后观测80µs。输出间隔请求10ns，实际时间网格记录。
- 观测：连续未wrap的reference/divided VCO相位、ref−div误差、两LF电压、瞬时VCO频率、PFD UP/DN、累计CP电荷、±pi unwrap分支事件及全部rail事件。相位单位为已除N的参考速率rad。边沿时间另外保存。稀疏UP/DN采样不能充当精确脉宽；累计CP电荷及边沿保留实际面积信息。滑移定义为误差跨wrap分支，不以边沿计数差直接充当滑移。
- 分析：用实际记录轨迹的分段线性积分，平均至从onset开始的100ns参考周期区间；M1用现有T的多项式系数和实际记录的参考输入，经FOH连续系统响应，同法平均。不进行相位或时间对齐拟合。零扰动相位响应单独扣除以消除数值基线，原轨迹仍需独立通过有效性门。
- 定义：符号归一化z=(y−y0)/A，e=r−y（连续展开）。peak deviation=max|e−e0|；overshoot=max(0,max(z)−1)，undershoot=min(z)；ringing amplitude为第一次z>1局部峰以后的peak-to-trough。settling为坡结束后首次且此后全窗|z−1|≤.02（rad地板1e-6）；这是局部相位阶跃恢复时间，不叫cold-start locking time。residual为尾20µs原始展开误差均值，lock retention/recovery由原始有效性和settling共同确定。
- 衰减拟合：对|z−1|局部峰，坡后、幅度≥1e-4、参考周期最小间距3bins；至少4峰、幅度跨度≥3、log包络线性R²≥.95，丢首/丢尾所得速率变化≤25%。否则衰减率null/UNKNOWN；正负、幅度、步长、窗口间可拟合速率变化≤25%才可信。周期仅至少2个同号峰且间距变异≤20%时输出；不能从超调反推PM。
- 工作点门：预段平均v偏差≤1mV、线性v漂移≤.1mV、相位峰≤.03rad、频率误差≤100ppm、零限幅/rail接近/滑移。扰动后相位峰≤.3rad；尾20µs频率≤100ppm、v漂移≤.1mV、残差≤max(.02|A|,1e-6rad)、无滑移/rail。无有效工作点不提取稳定性数值。
- 收敛：符号/幅度/dt/窗口各归一化曲线相同前80µsRMSE≤2%、最大差≤5%；overshoot变化≤2个百分点；settling差≤max(10%,.3µs)。零扰动与原核前6列和边沿逐元素相等。无稳定拟合时保留UNKNOWN，不用固定零代替。
- 映射比较及研究标签：门限见计划与JSON；UNKNOWN不能充当PASS或失稳。稳定观测不认证PM≥50°；完整周期PM始终未认证。幅度/dt/窗口检查在全部10候选同样执行。

C01–C08为开发；C09/C10在开发报告与分析源码/协议哈希锁写盘后才运行，一次完整固定套件（含预声明数值复核），不重调本轮门限。后续改进只能另立下一轮。
