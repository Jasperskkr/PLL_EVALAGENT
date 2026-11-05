# Development record before holdout

起始45,167份既有文件保护指纹与未提交Stage4源码备份保存于 `experiments/stage4_1/protection_before`。备份ZIP SHA256 `449378b7f24aaab3d672a5ac9041b0627639a6263a3a5518a99622dc2044de1d`。清单计算期间只有新Stage4.1文件及.gitignore忽略项增加；原Stage4源码、冻结输入、历史输出不修改。

Stage4明确范围checkpoint `7270f31`；原Stage4.2 `66c4ddb` 与Stage3A.1 `47afcb7` 均为祖先。既有两ZIP删除、旧未跟踪实验和外来ZIP不提交。Stage4报告中的“未提交工作树”是历史状态，不改写其原证据。

首次编译失败：生成器匹配`eventcount++`子串而非观测计数语句，C2065。原失败目录build_stage4_1保留，锚定完整语句后build_stage4_1_r2成功，M2尚未执行时已修正。见failures/build_01.json。

首次新入口测试13通过，包括四组零扰动三路径（旧DLL/新DLL原导出/新入口）逐元素相等、真实参考边沿/CP电荷/电压变化、M1实际输入对照、无振铃UNKNOWN和域拒绝。全套326通过。新Stage4锚点C01/C02六组扫频及原BW/Capture重跑，与历史UGF/PM/BW数值一致；新调用与旧数据复用不混记。

C01–C08执行相位正负/双幅/半步/双窗/零基线共88次新闭环调用，原Protocol1.1与Stage4频响同时保留。开发检查发现周期平均在边界处线性插值累计积分只近似原始分段线性轨迹积分；修正为严格的段内二次积分，新增非网格对齐线性信号测试。仅读取已保存轨迹重新分析到analysis_02，M2新调用0，原结果不覆盖，设置/阈值未改变。C03–C08补齐与Stage4完全相同的半幅/半步/双窗/错位频网；base/clamp引用开发初轮的新运行，不重复计成本。

开发结论用于固定分析，不使用C09/C10 M2。最终holdout锁包括协议、分析/执行源码、候选及Registry绑定和开发完整结果SHA。只在锁落盘并阶段提交后才开始C09/C10。同一固定套件中的数值复核属于预声明holdout检验；本轮不根据holdout结果调门限或算法。
