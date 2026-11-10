# Physics Mapping Stage 1 数值验收

数值验收：PASS。仅 Python M1；MATLAB Runtime=0、M2 TB=0、LLM=0。

|点|Vreq / V|UGF / Hz|BW / Hz|PM / deg|草案 M1 规格|
|---|---:|---:|---:|---:|---|
|default|0.400000000|138176.441132|222379.183493|56.44269021|M1_SPEC_PASS|
|Icp_up_20pct|0.400000000|161504.173103|263205.355734|56.12227020|M1_SPEC_PASS|
|Rz_up_to_4500|0.400000000|155083.740792|254940.763657|55.41954449|M1_SPEC_PASS|
|Kvco_up_25pct|0.320000000|167216.999974|273227.368744|55.96392022|M1_SPEC_PASS|
|Icp_Kvco_product_invariant|0.560000000|138176.441132|222379.183493|56.44269021|M1_SPEC_PASS|

默认点对照为历史 Python 交叉校验记录；扰动点对照为本次独立幅度多项式求根。
参数、电压点、公式对照来源、逐指标误差、失败状态、传播检查见相邻 JSON。
参考误差要求：BW/UGF≤0.5%，PM≤0.2°，Vreq≤1e-6 V。

所有异常均无系统指标且草案判决为 UNKNOWN；M1_SPEC_PASS 不等于完整行为 TB PASS。
M0/M2 接口尚未实现；未产生 Verified JointBlockSpec。
