"""Publish Stage4.1 review documents from saved evidence, no simulations."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
import shutil
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.verification.experiments import read, write


def text(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(value)


def main():
    docs = ROOT/'docs/stage4_1'; summary = ROOT/'experiments/stage4_1/final_summary_01'
    records = read(summary/'full_results.json'); costs = read(ROOT/'experiments/stage4_1/execution_audit/execution_costs.json')
    holdout = read(ROOT/'experiments/stage4_1/verifier_holdout_receipt.json')
    protection = read(ROOT/'experiments/stage4_1/protection_after/protection.json')
    if not protection['passed'] or not holdout['source_bindings_unchanged_at_end']:
        raise ValueError('protection/holdout source audit failed')
    for name in ('ENGINEERING_MAPPING_CONFIDENCE.json', 'candidate_validation_results.csv', 'closed_loop_response_metrics.csv'):
        target = docs/name
        if target.exists():
            raise FileExistsError(target)
        shutil.copyfile(summary/name, target)
    rows = []
    for r in records:
        m1 = r['M1']['metrics']; f = r['frequency_runs']; z = r['steps']['results']['plus']['M2']
        rows.append('|'+r['candidate_id']+'|'+f"{m1['BW_Hz']/1000:.3f} / {r['BW']['metrics']['BW_Hz']['value']/1000:.3f}"+'|'
                    +f"{m1['UGF_Hz']/1000:.3f} / {f['base']['crossing']['UGF_Hz']/1000:.3f} / {f['independent_clamp']['crossing']['UGF_Hz']/1000:.3f}"+'|'
                    +f"{m1['PM_deg']:.5f} / {f['base']['crossing']['PM_deg']:.5f} / {f['independent_clamp']['crossing']['PM_deg']:.5f}"+'|'
                    +f"{z['overshoot_relative']*100:.3f}% / {z['settling_s']*1e6:.2f}"+'|'+r['BW']['overall_status']+'|')
    report = '''# Stage 4.1 M1/M2 Engineering Mapping Validation

2026-11-05。**10个预声明合法候选全部获得局部频响及独立闭环阶跃的工程支持；未获得完整周期PM认证，也没有完整SystemSpec Behavioral PASS。** 原M1、六变量域、SystemSpec（含draft）、M2更新、Protocol1.1、Stage4方法和正式Agent保持。

## WHAT

新增隔离的平滑参考相位阶跃事件入口、PFD/CP/电压/相位/频率/滑移/rail观测、周期平均及保守振铃拟合、量化M1对照和机器可读研究可信度合同。不是新的Allocation系统。Native路径不计算M1频响；M1只用于静态工作点初始化及事后对照，未填入M2测量值。

## HOW

先运行独立零扰动M2，初始化v=u=Vreq，phi=0，检查20–40µs。40µs施加0.5µs raised-cosine相位坡，正负0.01/0.02rad；步长0.4/0.2ns，后观测80/160µs，真实相位/边沿与累计电荷保存。共每点3个零基线+8个阶跃。M1使用现有T系数、相同实际参考轨迹、FOH输入、同一100ns参考周期积分平均；不做相位/时间拟合对齐。瞬时输出频率由原线性VCO逐步实际状态记录。

基线原始有效性、正负/幅度/步长/窗口、log振铃包络/删峰稳定性和M1误差门限均在首次Stage4.1 M2前写盘。开发纠正段内积分近似后读取已有轨迹到analysis_02；不改阈值、不新增M2、不覆盖旧结果。完整预声明门限见协议。C01/C02先新跑Stage4六组扫频，随后其余候选同样完成Series/Clamp、半幅/半步/双窗/错位网格。没有借M1设置交越或制造M2数据。

## RESULT

下表时域列为+0.01rad常规窗口；恢复时间从平滑坡结束算起，误差带为输入幅度的2%，不是冷启动locking time。UGF/PM三列依次为M1 / Series Local / Direct Port Local。

|Candidate|BW M1 / M2 (kHz)|UGF (kHz)|PM (deg)|Overshoot / recovery (µs)|正式整体|
|---|---:|---:|---:|---:|---|
'''+ '\n'.join(rows)+'''

研究标签10/10均为LOCAL_MAPPING_SUPPORTED、CLOSED_LOOP_STABLE_OBSERVED、FULL_PERIODIC_PM_NOT_CERTIFIED；无本轮局部异常反例。这是对固定理想模型有限点的结果，不是整个六维域证明。

- C04/C05/C06：UGF同约140kHz，PM55/60/65°；超调16.765/13.397/13.460%，恢复18.35/17.55/14.05µs。超调不是严格随PM单调。LF零点11.386/15.077/25.336kHz、极点239.096/316.627/532.050kHz同时改变；不能将全部形状差异归因于PM。完整M1 T能解释三条响应，比单独PM数值更有用。
- C07：PM约35°，超调44.124%，更明显的交替衰减振铃；约13.05µs恢复，未失锁。低于PM规格不等于动态发散。可辨识包络约2.8330e5/s、同号峰周期约8.467µs；这是包络测量，不是PM反解。
- C01/C08：Icp/Kvco拆分变化、乘积/RC相同；两点Vreq0.4/0.64V。正阶跃归一化M2全窗最大差4.7284e-8，频域和BW也近似一致，支持指定理想增益拆分等价。不能推广为具有CP非理想/噪声/rail机制的电路不变量。
- C03：Series50.02371454°、Clamp49.99733540°分居门限两侧；保留测量定义差异和边界歧义。正式PM UNKNOWN。
- C09/C10固定holdout后才使用结果；C10实测BW364.649kHz而正式FAIL，仍是正确物理预测的例子。C07/C09的M1 PM失败与M2正式UNKNOWN分别记录，不能将“稳定观测”当作PM满足。

## ACCURACY

对10点base Series/Clamp，最大绝对BW相对误差0.623971%；Series UGF误差0.552584%、Direct Port0.00791414%；对应PM绝对差0.0486353° / 0.0100285°。所有base/Clamp实际点对M1复数返回比最大相对差0.676837%、相位差0.0653588°。Series/Clamp的可重复系统差异单独记录，不解释为M1已被证明错误。

80个阶跃变体中，M1/M2归一化RMSE最大0.0418654%、最大逐点差0.268116%、超调绝对差0.0450526个百分点、恢复差0.1µs。误差分母是实际输入幅度；恢复的周期平均分辨率为0.1µs。80/160µs长尾RMSE不是初期峰值误差的替代，因此同时报告最大逐点差和超调。

正负/双幅/半步/双窗之间，归一化RMSE最大0.00165578%、最大差0.0169592%、超调差0.00552216个百分点、恢复差0个周期bin。频域数值复核（不含独立Clamp定义差异）最大UGF变化0.00248837%、PM0.00450482°。这些是确定性有限复核的观测差异，不是统计置信区间或认证误差界。

## RELIABILITY

共1000个局部返回比频点（含全部refinement、错位网格）有效，未裁掉失败频点；最大侧带RSS2.29502%、THD0.00551285%、残差0.279288%、半窗复差0.0375301%，最大均值控制偏差11.4203µV、漂移6.43670µV、频差3.47735ppm。110次新闭环零基线/扰动中无滑移/rail事件，工作点和恢复门全部通过。原Protocol1.1十点均在既定初值/窗口内捕获；其结论仍只对该窗口成立。

标称+0.01rad包络仅C03/C07可稳定拟合；其余8点峰数不足/包络不适用，衰减率null/UNKNOWN。无振铃不是零衰减率；未以二阶超调公式回推PM。其它符号/幅度/步长/窗口拟合信息全部保留。

支持范围是JSON列出的10个完整参数组合，不能把边际范围拼成整个可验证超矩形。覆盖Icp61.0525–163µA、Rz2211.724–6989.359Ω、C1三选、C2三选、f0 61.9–72MHz、Kvco12.5–33.2MHz/V；Vreq0.4–0.74269V，UGF104.265–219.228kHz，M1 PM35–72.2472°。未测原轴所有边界、近rail、其它载波相位、非理想/PVT/噪声、大信号扰动、多初值全局捕获或严格周期稳定性。相位wrap分支事件只服务此局部小误差条件，不宣称建立通用cycle-slip认证器。

原正式BW：C01–C09 PASS，C10 FAIL；原正式PM/UGF及微Hz频率精度全部UNKNOWN；整体9 UNKNOWN、1 FAIL。局部稳定研究标签没有接管正式Pipeline。Stage4已发现的反向谐波转换障碍仍成立，本轮没有完整谐波矩阵截断界/Floquet证明。

## ALLOCATION VALUE

现有M1足以支持在已验证理想邻域内快速寻找和排序候选；应联合使用调谐域、完整T/L动态和原BW/PM约束。M1条件可行不等于已验证BlockSpec；最终Runner继续完整TB。PM/BW边界、接近rail、明显不同RC形状或冷启动风险应让M2更早参与。不能根据10点最大差自动设全域安全裕量，不能以单个PM或1/BW预测恢复/捕获时间。

Registry和新Confidence为只读研究知识，不替换M1/Block Space/正式Agent。RUR未定义，静态偏置/Locking Time未新增硬约束，Jitter/Power仍缺机制，本轮不解决这些能力缺口。

## EVIDENCE / 版本 / 测试与失败

Stage3A.1=47afcb7；Stage4.2=66c4ddb；原未提交Stage4明确范围checkpoint=7270f31；Stage4.1开发及协议=3a6a6e1；轨迹分离后的holdout执行Commit=6f93a5fc9247a3094a5b294346959c92f2b242bd。Holdout锁SHA256 `eda03d7aa9cc6220ecd07a01016df129d92f8c95b014f504185ed8cf691d0b42`；执行末源码绑定再次一致。最终交付Commit/包SHA见最终回执，不回写历史源版本。

主线最终328通过（原283+Stage4 17+Stage4.2 13+本阶段15），原TrackB单独28通过；28是重复回归，不能加作新独立测试数。四组零扰动三路径逐元素相同。新锚点UGF/PM/BW数值重现历史。普通解析Pipeline实际M2_PARTIAL_PASS、106native/11.0696s，反馈到Agent层，不新增LLM请求/策略学习。无DLL源码副本重新编译三套核后328项再通过，25.93s；仅同机Windows/MSVC，不宣称跨平台或wheel验收。

45,167份既有文件保护无意外改变/缺失，TrackB HEAD/status不变。只追加阶段记录/忽略规则；已有两ZIP删除原样保留，未吞入本阶段提交。主实验实际3632native，含340次DC pilot，2,745,661,472积分点，111.750622原生秒；开发主程序墙钟157.950s、holdout84.903s，Pipeline11.070s。原生时间不含写盘/拟合/画图；测试/重建内部调用另列，不伪称总研究墙钟或总仿真成本。新LLM0，货币成本未知。

失败/修正原地保留：首次生成器编译错误（M2=0）；开发周期平均段内积分修正（只重分析）；首次绘图源码审查无法识别动态扩展名导出，改为显式PDF/SVG/PNG后新目录重渲染，数据/布局不变；重建回执初次相对路径定位XML错误后只修正元数据读取。初阶段提交误纳860个原Protocol波形，后续仅移出Git索引并补忽略规则，本地和Git历史保留，未改写历史；审查包不含NPZ。实验测量无失败文件，不将编译/后处理问题隐藏为通过。

## LIMITATIONS / NEXT

当前结论为“局部PM/UGF映射在列出的理想工作点具有工程预测价值，尚不构成完整周期系统稳定性认证”。下一步建议先定义并审核M2-Fast（本次暖启动短扰动+域/边界检查）及与完整TB的预算/误判合同；其次扩展载波相位、rail邻域、RC极端和冷启动域，继续使用现有M1多保真核验；若要签发正式PM，再研究有截断误差控制的谐波返回矩阵/Floquet桥接。暂不训练黑盒，不修改Agent、规格或域。本阶段在此停止等待Leader。
'''
    text(docs/'M1_M2_MAPPING_VALIDATION_REPORT.md', report)
    holdrows = '\n'.join(rows[8:])
    text(docs/'holdout_validation_report.md', '''# Fixed holdout validation

C09/C10在C01–C08开发完成、analysis_02段内积分修正和固定源码/协议/结果锁落盘后才运行。锁SHA256 `eda03d7aa9cc6220ecd07a01016df129d92f8c95b014f504185ed8cf691d0b42`；实际源Commit6f93a5f，运行末binding逐项相同。一次完整预声明套件含数值复核，不是看到结果后重复择优。

|Candidate|BW M1 / M2(kHz)|UGF M1/Series/Clamp(kHz)|PM M1/Series/Clamp(deg)|Overshoot / recovery(µs)|正式整体|
|---|---:|---:|---:|---:|---|
'''+holdrows+'''

两个点局部频响/时域/收敛支持映射，均局部稳定恢复；未发现新的动态反例，未据此改方法/门限。C10 BW超300kHz正式FAIL；两点原M1 PM均低于50°，不能因局部稳定改判规格满足。正式PM/UGF继续null/UNKNOWN。两点不是随机总体样本，不提供统计成功率或全域误差上界。

706次实际native、68 pilots、20.6848275原生秒、84.902663墙钟秒；无失败/调参/重跑。全部请求、运行版本、原轨迹及SHA本地保留，见holdout_01、verifier_holdout_receipt及execution_audit。未参加新方法训练。
''')
    text(docs/'RUN_AND_REPRODUCE.md', '''# Source checkout reproduction and interfaces

Windows x64/MSVC2022 Community、Python3.12.10，NumPy/SciPy/pytest；matplotlib用于图。精简包是源码快照，不是wheel；原pyproject二进制资源合同未扩展。跨平台未验收。所有输出/构建目录必须不存在，工具拒绝覆盖。命令从项目根执行。

```powershell
& .\\pll_allocation\\verification\\build_kernel.cmd
& .\\pll_allocation\\verification\\build_return_ratio.cmd
& .\\pll_allocation\\verification\\build_closed_loop.cmd
python -m pytest -q tests -p no:cacheprovider
python tools/run_stage41.py --mode anchors --out experiments/stage4_1/new_anchors
python tools/run_stage41.py --mode development --anchors experiments/stage4_1/new_anchors --out experiments/stage4_1/new_development
python tools/collect_stage41_frequency.py --development experiments/stage4_1/new_development --out experiments/stage4_1/new_frequency_checks
python tools/reanalyze_stage41_steps.py --development experiments/stage4_1/new_development --out experiments/stage4_1/new_analysis
python tools/summarize_stage41.py --anchors experiments/stage4_1/new_anchors --development experiments/stage4_1/new_development --refinements experiments/stage4_1/new_frequency_checks --analysis experiments/stage4_1/new_analysis --out experiments/stage4_1/new_development_summary --freeze experiments/stage4_1/new_holdout_lock.json
# 仅在固定开发结果/源码/协议审查后执行；不能据holdout调本轮方法。
python tools/run_stage41.py --mode holdout --lock experiments/stage4_1/new_holdout_lock.json --out experiments/stage4_1/new_holdout
python tools/summarize_stage41.py --anchors experiments/stage4_1/new_anchors --development experiments/stage4_1/new_development --refinements experiments/stage4_1/new_frequency_checks --analysis experiments/stage4_1/new_analysis --holdout experiments/stage4_1/new_holdout --out experiments/stage4_1/new_summary
python -m pll_allocation pipeline --strategy analytical --out experiments/stage4_1/new_pipeline
```

最终版本development直接跑完整六扫频；`collect`只转换已执行六扫回执，M2调用0。`refine`保留用于原开发series/clamp二扫历史补四扫，不能对新六扫重复调用。两种流程成本分别记录。历史原始命令在verifier_*receipt；不将新复现误称本轮新首次或独立holdout。

接口：`closed_loop_native.simulate_step(full_SI_envelope, **settings)`返回18列实际trace、reference/divider edges、事件表、实际dt、源/DLL SHA。`closed_loop.analyze(parameters, run, zero, protocol)`返回独立M2指标、M1事后指标、误差和统一周期曲线；无效工作点返回UNKNOWN且无动态数值。`compare_refinements`不合成PM认证。`summarize_stage41`产生研究合同及CSV，不接管Runner判决；Registry仍只读。

实际权威结果final_summary_01；开发时域analysis_02；holdout时域holdout_01/*/steps；raw请求/NPZ/source/DLL摘要另存，raw路径/字节/SHA在execution_audit/raw_and_artifact_hashes.json。C02读取既有真实Agent Proposal，本阶段LLM0，不能把复验称为新Agent调用。精简包包含完整SI、测试、方法、结果及SHA，不含原始波形/编译件/缓存/密钥。图表采用英文，PDF/SVG矢量+300dpi PNG审查预览。
''')
    text(docs/'FIGURE_QA.md', '''# Figure review

Python/matplotlib，最终figures_02。六个PDF/SVG/PNG分别覆盖全部10点频域（2页）、配对PM三点、低PM、增益拆分、误差/风险。全部基准Series/Clamp频点和实测refinement点保留，全部6组1000点源数据在frequency_response.csv；时域代表图预声明前40µs，完整80/160µs CSV保留。无随机置信区间、无经验滤点或隐藏失败。

6图最终panel alignment、PDF最小7pt字号及collision审查全部exit0；18项源码检查通过，3WARN已人工审阅：仅提供300dpi PNG预览、无TIFF投稿图、频域宽299.7mm为Leader审查用途。PDF/SVG是矢量，未宣称期刊投稿验收。初轮源码审查不能识别循环扩展名而报缺导出；改为显式savefig后重新输出figures_02，初版与失败记录保留。所有panel和整图已逐一查看；无文本重叠、裁切或误差编码歧义。
''')
    versions = {'python': platform.python_version(), 'platform': platform.platform(),
                'packages': {name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'matplotlib', 'pytest')},
                'compiler': 'MSVC2022 x64 C++17 /O2 /EHsc /LD', 'baseline': '47afcb72011636e838b03d81cf91bcec49744a77',
                'stage4_checkpoint': '7270f31', 'holdout_source_commit': '6f93a5fc9247a3094a5b294346959c92f2b242bd'}
    write(docs/'VERSIONS.json', versions)
    write(docs/'ACCEPTANCE.json', {'status': 'COMPLETE_PENDING_LEADER_REVIEW',
          'candidates': 10, 'mapping_supported': 10, 'local_stable_observed': 10,
          'formal_overall': {'UNKNOWN': 9, 'FAIL': 1, 'PASS': 0},
          'mainline_tests_passed': 328, 'original_TrackB_tests_passed': 28, 'fresh_source_tests_passed': 328,
          'full_periodic_PM_certified': False, 'new_LLM_calls': 0, 'protected_files': 45167,
          'main_native_costs': costs['totals'], 'thresholds_changed_after_holdout': False,
          'next_stage_started': False})
    print('Stage4.1 research reports written from saved evidence')


if __name__ == '__main__':
    main()
