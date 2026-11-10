"""Stage6B source/evidence ZIP with byte manifest. No builds or simulations."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import read,write_new


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def selected():
    directories=('pll_allocation','configs','data','docs','tools','tests','examples','learn')
    found={p for name in directories for p in (ROOT/name).rglob('*') if p.is_file()}
    found.update(p for p in ROOT.iterdir() if p.is_file() and (p.suffix in ('.md','.toml') or p.name in ('.gitattributes','.gitignore')))
    found.update(p for p in (ROOT/'experiments/stage6b').rglob('*') if p.is_file())
    historical=[
        'experiments/stage4_2/readiness_05/summary.json',
        'experiments/stage4_2/readiness_05/coupling_and_sensitivity.json',
        'experiments/stage6a/study.py',
        'experiments/stage6a/summary_01/summary.json',
        'experiments/stage6a/summary_01/experiments.csv']
    for name in historical:
        p=ROOT/name
        if p.is_file():found.add(p)
    # Full-process trace references the candidate archive's receipt, never the large earlier ZIP.
    p=ROOT/'delivery/stage6b_20261109_01/stage6b_candidate_01.zip.receipt.json'
    if p.is_file():found.add(p)
    for name in ('experiments/stage5/scenarios',
        'experiments/stage5/repair_01/runs/S3__random__11/attempt_001',
        'experiments/stage5/firstshot_01/runs/S0__analytical/attempt_001',
        'experiments/stage6a/m2_01/runs/E0_analytical/attempt_001',
        'experiments/stage6a/m2_01/runs/E1_upper_shape/attempt_001'):
        found.update(p for p in (ROOT/name).rglob('*') if p.is_file())
    skip_parts={'__pycache__','.pytest_cache','tmp','.git','build','build_stage4','build_stage4_1','build_stage4_1_r2'}
    for p in sorted(found):
        relative=p.relative_to(ROOT)
        if relative.as_posix().startswith('experiments/stage6b/package_validation_01/reproduced/'):continue
        if set(relative.parts)&skip_parts or p.suffix.lower() in ('.zip','.dll','.obj','.lib','.exp','.pyc','.key'):continue
        if p.name=='.env' or p.name.startswith('.env.'):continue
        yield p


README='''# Stage6B 可复现交付

本目录包含可运行源码、原始冻结输入、B1/B2 A/B/C 配置、完整 Stage6B 正式运行原始数据、失败开发记录、独立解包复现结果、逐事件 trace、报告和必要历史回归 fixtures。历史其他阶段的完整运行目录不在本包范围；safety_01 保留精确继承清单和原工作树差异。主分支未合并。package_validation_01/reproduced 的嵌套重复副本不重复装包，使用同SHA的规范 reproduction_01 路径。

先读 docs/stage6b/FINAL_REPORT.md、ARCHITECTURE_AND_ALGORITHM.md。结果表在 experiments/stage6b/summary_01/；运行原始数据在 experiments/stage6b/study_01/runs/*/candidate_*/full_pipeline/raw/。每方法 allocation_trace.jsonl 是实时哈希链。覆盖全程的单文件 trace 是 experiments/stage6b/trace_01/complete_trace.jsonl，其中展开原始运行事件，并索引安全隔离/设计/构建/失败测试/保护/封包回执；每条记录声明实时事件或后建索引来源，原始时间保持。summary_01/full_process_trace.jsonl 保留初次汇总索引。最终交付 CRC/SHA 回执在压缩包同目录。

## 环境

验证环境 Windows11 x64、Python3.12.10、NumPy2.5.3、SciPy1.18.1、pytest9.2.0；MSVC19.37.32824 / toolset14.37.32822。运行确定性结果依赖数值版本；时间成本按机器变化。无 ngspice/PDK/LLM 服务依赖。原生库从源重建，包中不包含本机 DLL。

在此根目录 PowerShell 执行（使用全新输出路径）：

```powershell
python -m pip install numpy==2.5.3 scipy==1.18.1 pytest==9.2.0
cmd /c pll_allocation\\verification\\build_kernel.cmd
cmd /c pll_allocation\\verification\\build_return_ratio.cmd
cmd /c pll_allocation\\verification\\build_closed_loop.cmd
python -B -m pytest -q tests -p no:cacheprovider --basetemp=reproduction_checks_01/tmp --junitxml=reproduction_checks_01/tests.xml
python -B tools/run_stage6b.py --frozen experiments/stage6b/frozen_02 --out experiments/stage6b/reproduction_new_01
python -B tools/audit_stage6b.py --study experiments/stage6b/reproduction_new_01 --out experiments/stage6b/reproduction_new_summary_01
```

构建脚本默认 VS2022 Community 的 vcvars64.bat。未安装该位置时，保留原脚本并在另一个版本化环境配置适配路径/记录编译器身份，不伪装同一二进制。三个构建目标若存在会拒绝覆盖。pytest 输出父目录需先 `New-Item -ItemType Directory reproduction_checks_01`。

单个正式研究运行仍只有此入口：

```powershell
python -B -m pll_allocation pipeline --multispec experiments/stage6b/frozen_02/B1.json --method C --out experiments/stage6b/single_repeat_01 --evaluation-cache experiments/stage6b/new_repeat_cache_01
```

不要使用历史 study_01/evaluation_cache 写入新实验。它引用已保存的原证据与当时本机构建哈希；新构建/路径身份可能不同。新实验使用新缓存，研究指标应可重现，时间/绝对路径/库身份/trace哈希会变化。

BUNDLE_MANIFEST.json 逐文件 SHA256。`python tools/package_stage6b.py verify --root .` 可离线验证原包内容（解包重建后会生成额外文件，原 manifest 列出的文件仍应不变）。source/plan 绑定的算法文件不可编辑后声称同一实验。

全部 PASS 仅指声明的混合研究约束。严格周期 PM 和1µHz频率未认证；FULL_SYSTEMSPEC_CERTIFIED=false。Stage6B真实 LLM 调用为0。
'''


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);bundle=out/'PLL_allocation';bundle.mkdir()
    count=0
    for path in selected():
        destination=bundle/path.relative_to(ROOT);destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,destination);count+=1
    (bundle/'README_STAGE6B.md').write_text(README,encoding='utf-8')
    write_new(out/'prepare_receipt.json',{'created_at':datetime.now(timezone.utc).isoformat(),
        'copied_files':count,'source_root':str(ROOT),'bundle_root':str(bundle),
        'selection':'full runnable source/config/data/docs/tests/tools plus full Stage6B evidence excluding native builds/test temp; historical test fixtures only',
        'excluded':'git metadata, local credentials, native binaries/build cache, nested archives, synthetic test temp',
        'source_stage5_stage6a':'reference fixtures and snapshot manifests; not all historical raw runs'})
    return bundle


def archive(bundle,path):
    if path.exists():raise FileExistsError(path)
    manifest_path=bundle/'BUNDLE_MANIFEST.json'
    entries=[{'path':p.relative_to(bundle).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
        for p in sorted(bundle.rglob('*')) if p.is_file() and p!=manifest_path]
    if manifest_path.exists():raise FileExistsError(manifest_path)
    write_new(manifest_path,{'schema_version':'stage6b-bundle-manifest-1.0','files':entries,
        'scope':'every packaged file except this manifest; archive integrity checked separately'})
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():archive.write(p,'PLL_allocation/'+p.relative_to(bundle).as_posix())
    with zipfile.ZipFile(path) as archive:
        bad=archive.testzip()
        if bad:raise ValueError('CRC_FAILED:'+bad)
        files=len(archive.infolist())
    digest=sha(path)
    (path.parent/(path.name+'.sha256')).write_text(digest+'  '+path.name+'\n',encoding='ascii')
    receipt={'archive':str(path),'sha256':digest,'bytes':path.stat().st_size,'files':files,'CRC':'PASS',
        'uncompressed_bytes':sum(r['bytes'] for r in entries),'created_at':datetime.now(timezone.utc).isoformat()}
    write_new(path.parent/(path.name+'.receipt.json'),receipt)
    return receipt


def verify(bundle):
    manifest=read(bundle/'BUNDLE_MANIFEST.json')
    for row in manifest['files']:
        path=(bundle/row['path']).resolve()
        assert path.is_relative_to(bundle.resolve()) and path.is_file() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],row['path']
    return {'status':'PASS','files_verified':len(manifest['files'])}


if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('--out',required=True)
    p=sub.add_parser('archive');p.add_argument('--root',required=True);p.add_argument('--zip',required=True)
    p=sub.add_parser('verify');p.add_argument('--root',required=True)
    a=parser.parse_args()
    result=prepare(Path(a.out).resolve()) if a.action=='prepare' else archive(Path(a.root).resolve(),Path(a.zip).resolve()) if a.action=='archive' else verify(Path(a.root).resolve())
    print(json.dumps(str(result) if isinstance(result,Path) else result,ensure_ascii=False,indent=2))
