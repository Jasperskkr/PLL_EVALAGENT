"""Read-only source/evidence audit; writes only a fresh child directory."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pll_allocation.pipeline_contracts import load_inputs, check_result, m2_label
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.verification.build_identity import check_build

SOURCES = {
    'PROJECT_CHARTER.md': '用户原始主线',
    'AGENTS.md': '工作区约束',
    'docs/PROJECT_STATUS.md': '当前阶段状态',
    'configs/pipeline_stage3a.json': '主入口及绑定',
    'configs/BLOCK_SPACE_MODEL_V1.json': '参数域/变量语义/证据合同',
    'configs/physics_mapping_stage1_v2.json': '人工声明域原输入',
    'configs/SYSTEM_SPEC_STAGE1_5.json': '当前正式运行三项规格',
    'configs/PLL_EQUATION_REGISTRY_V1.json': '原公式/上游来源',
    'configs/verification/protocol_v1_1.json': '正式测量与判决协议',
    'tools/prepare_block_space_v1.py': 'Block Space构建过程',
    'pll_allocation/block_space/contracts.py': '模型加载/域检查/完整候选',
    'pll_allocation/block_space/calibration.py': '偏差记录但无残差学习',
    'pll_allocation/block_space/event_reference.py': '早期稀疏事件交叉校验',
    'pll_allocation/block_space/validation.py': '早期域与事件验证',
    'data/behavioral_space_v1/reference/provenance.json': '事件原函数来源与限制',
    'data/behavioral_space_v1/reference/python_crosscheck.py': '保留原Python边沿/Euler函数',
    'pll_allocation/physics_mapping/model.py': 'M1解析正向与求根',
    'pll_allocation/physics_mapping/validation.py': '同方程独立数值根',
    'pll_allocation/physics_mapping/registry.py': '研究只读映射查询',
    'pll_allocation/allocation/physics.py': '实际Agent使用的关系、约束传播和逆解',
    'pll_allocation/allocation/allocate.py': '解析/敏感度/SLSQP/随机',
    'pll_allocation/allocation/agent.py': '真实LLM权限与工具选择',
    'pll_allocation/allocation/__init__.py': '策略边界及真实LLM修复缺口',
    'pll_allocation/allocation/repair.py': '已执行确定性设计修复',
    'pll_allocation/allocation/feedback_agent.py': '独立可插拔修复接口/模拟策略',
    'pll_allocation/pipeline.py': '写盘、预算、完整TB调用与反馈',
    'pll_allocation/pipeline_contracts.py': '版本与结果绑定/反馈投影',
    'pll_allocation/scenarios.py': '研究目标变体授权边界',
    'pll_allocation/verification/verify.py': '验证入口/判决/成本',
    'pll_allocation/verification/simulator.py': '参数、步长、编译核适配',
    'pll_allocation/verification/kernel.cpp': 'PFD边沿/CP面积/LF Euler/VCO相位',
    'pll_allocation/verification/build_identity.py': '源码与二进制绑定',
    'pll_allocation/verification/experiments.py': '冷/暖实验计划与自适应实测细化',
    'pll_allocation/verification/measure.py': '原始波形指标提取',
    'pll_allocation/verification/run_suite.py': '幅度/步长/窗口收敛，M1事后比较',
    'pll_allocation/verification/scenario.py': '同实测数据按场景阈值独立重判',
    'pll_allocation/verification/return_ratio_validity.py': '局部PM研究与正式认证隔离',
    'pll_allocation/verification/closed_loop.py': '相位阶跃局部工程证据',
    'docs/stage1_5/DOMAIN_VALIDATION_REPORT.md': '早期范围构建及124/32点证据',
    'docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json': '映射能力矩阵与源绑定',
    'docs/stage4_2/SYSTEM_SPEC_MAPPING_MATRIX.md': '逐指标支持/逆解能力',
    'docs/stage4_1/ENGINEERING_MAPPING_CONFIDENCE.json': '十个具体点的局部支持',
    'docs/stage4_1/M1_M2_MAPPING_VALIDATION_REPORT.md': '局部验证方法与解释限制',
    'docs/stage5/END_TO_END_FEASIBILITY_REPORT.md': '最新场景/误差/策略结论',
    'experiments/stage5/summary_02/summary.json': '最新正式实验汇总',
    'experiments/mainline_consolidation_20261105_01/postmerge_baseline/AllocationProposal.json': '真实解析候选实例',
    'experiments/mainline_consolidation_20261105_01/postmerge_baseline/attempt_001/BehavioralVerificationResult.json': '真实106native测量/判决实例',
    'tools/build_block_relation_atlas.py': '上一轮只读关系图谱；非Agent自动依赖',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def write(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def main():
    out = Path(__file__).parent/'snapshot_01'
    out.mkdir(exist_ok=False)
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0')
    write(out/'protected_before.json',[{'path':name,'sha256':sha(ROOT/name) if (ROOT/name).is_file() else None}
                                      for name in tracked if name])
    (out/'git_before.txt').write_text(subprocess.check_output(['git','status','--short'],cwd=ROOT).decode('utf-8'),encoding='utf-8')
    source_manifest=[{'path':name,'absolute_path':str(ROOT/name),'sha256':sha(ROOT/name),
                     'semantics':purpose,'applicable_domain':'current frozen ideal behavioral PLL; source audit only'}
                     for name,purpose in SOURCES.items()]
    write(out/'source_manifest.json',source_manifest)
    config, model, spec, protocol=load_inputs()
    eq=read('configs/PLL_EQUATION_REGISTRY_V1.json')
    upstream={x['path']:x for r in eq['equations'] for x in r['source_files']}
    upstream_checks=[{'path':name,'registered_sha256':r['sha256'],'actual_sha256':sha(name) if Path(name).is_file() else None,
                      'match':Path(name).is_file() and sha(name)==r['sha256']} for name,r in upstream.items()]
    provenance=read('data/behavioral_space_v1/reference/provenance.json')
    reference_checks={name:Path(name).is_file() and sha(name)==provenance['sha256']
                      for name in [provenance['source'],str(ROOT/'data/behavioral_space_v1/reference/python_crosscheck.py')]}
    proposal=read('experiments/mainline_consolidation_20261105_01/postmerge_baseline/AllocationProposal.json')
    measured=read('experiments/mainline_consolidation_20261105_01/postmerge_baseline/attempt_001/BehavioralVerificationResult.json')
    check_result(measured,proposal,protocol)
    stage5=read('experiments/stage5/summary_02/summary.json')
    symbols={}
    for name in SOURCES:
        if name.endswith('.py'):
            tree=ast.parse((ROOT/name).read_text(encoding='utf-8'))
            symbols[name]=[{'name':n.name,'line':n.lineno,'end_line':n.end_lineno}
                           for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
    write(out/'symbols.json',symbols)
    lines=['# 关键源码索引\n','本轮读取当前工作树；函数位置由AST提取。\n',
           '|源文件 / 职责|符号与位置|','|---|---|']
    for name,syms in symbols.items():
        if name.startswith('pll_allocation/') or name.startswith('tools/'):
            links=', '.join(f'[{s["name"]}]({(ROOT/name).as_posix()}:{s["line"]})' for s in syms[:12])
            lines.append(f'|{name} · {SOURCES[name]}|{links}|')
    (out/'SOURCE_INDEX.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    snapshot={'status':'SOURCE_AND_BINDING_AUDIT_PASS','date':'2026-11-06 Asia/Shanghai',
        'source_count':len(source_manifest),'upstream_matlab_source_checks':upstream_checks,
        'historical_python_event_reference_checks':reference_checks,'native_binary_identity':check_build(),
        'model':{'semantic_sha256':fingerprint(model),'versions':model['versions'],'scope':model['scope'],
                 'input_counts_by_kind':dict(Counter(v['kind'] for v in model['variables'].values())),
                 'catalog_count':len(model['variable_catalog']),'equation_count':len(eq['equations']),
                 'calibration_policy':model['calibration_policy']},
        'frozen_system_spec':spec,'protocol_id':protocol['protocol_id'],
        'historical_baseline':{'parameter_sha256':proposal['parameter_sha256'],
             'six_free_values':{k:v for k,v in proposal['joint_block_spec']['values'].items() if k in ('Icp','Rz','C1','C2','f0','Kvco')},
             'M1_metrics':proposal['M1']['prediction']['metrics'],'M2_metrics':measured['metrics'],
             'constraints':measured['constraints'],'overall_status':measured['overall_status'],
             'pipeline_label':m2_label(measured),'cost':measured['execution_cost'],
             'recounted_as_new_run':False},
        'historical_stage5':{'main_strategy_totals':stage5['totals'],
                            'full_verified_pass_count':stage5['full_verified_pass_count'],
                            'recounted_as_new_run':False},
        'new_full_M2_runs':0,'new_LLM_calls':0,'MATLAB_runtime_calls':0}
    write(out/'audit_snapshot.json',snapshot)
    print(json.dumps({'source_count':len(source_manifest),'upstream_matches':sum(x['match'] for x in upstream_checks),
                      'upstream_count':len(upstream_checks),'reference_checks':reference_checks,
                      'baseline_result_binding':'PASS','new_M2':0,'new_LLM':0},ensure_ascii=False))


if __name__=='__main__':
    main()
