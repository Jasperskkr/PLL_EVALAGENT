# Fixed holdout validation

C09/C10在C01–C08开发完成、analysis_02段内积分修正和固定源码/协议/结果锁落盘后才运行。锁SHA256 `eda03d7aa9cc6220ecd07a01016df129d92f8c95b014f504185ed8cf691d0b42`；实际源Commit6f93a5f，运行末binding逐项相同。一次完整预声明套件含数值复核，不是看到结果后重复择优。

|Candidate|BW M1 / M2(kHz)|UGF M1/Series/Clamp(kHz)|PM M1/Series/Clamp(deg)|Overshoot / recovery(µs)|正式整体|
|---|---:|---:|---:|---:|---|
|C09_holdout|209.572 / 209.826|124.446 / 124.570 / 124.446|45.52389 / 45.52242 / 45.51952|33.030% / 7.65|UNKNOWN|
|C10_holdout|363.794 / 364.649|219.228 / 219.703 / 219.245|48.48784 / 48.43920 / 48.47781|24.929% / 9.15|FAIL|

两个点局部频响/时域/收敛支持映射，均局部稳定恢复；未发现新的动态反例，未据此改方法/门限。C10 BW超300kHz正式FAIL；两点原M1 PM均低于50°，不能因局部稳定改判规格满足。正式PM/UGF继续null/UNKNOWN。两点不是随机总体样本，不提供统计成功率或全域误差上界。

706次实际native、68 pilots、20.6848275原生秒、84.902663墙钟秒；无失败/调参/重跑。全部请求、运行版本、原轨迹及SHA本地保留，见holdout_01、verifier_holdout_receipt及execution_audit。未参加新方法训练。
