"""Locate saved wall-clock anomalies; retain all raw durations, no re-evaluation."""
from pathlib import Path
import json
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'experiments/spec_allocation_ablation'


def main():
    all_m1=[];runs=[];long=[]
    for task in ('task1','task2','task3'):
        for path in (OUT/task).glob('*/result.json'):
            result=json.loads(path.read_text(encoding='utf-8'));runs.append(result)
            samples=path.parent/'all_candidates.jsonl'
            if not samples.exists():continue
            for text in samples.read_text(encoding='utf-8').splitlines():
                row=json.loads(text)
                if not row['formal_M1_called']:continue
                wall=row['cost']['evaluation_timing']['wall_time_s'];all_m1.append(wall)
                if wall>60:
                    long.append({'task':task,'run_id':result['run_id'],'M1_index':row['global_M1_call_index'],
                        'region_id':row['region_id'],'source':row['source'],'M1_wall_s':wall,
                        'M1_return_elapsed_s':row['M1_return_elapsed_s'],'first_PASS_elapsed_s':result['time_to_first_PASS_s'],
                        'run_wall_s':result['total_wall_s'],'API_latency_s':result['API_latency_s'],
                        'metrics':row['metrics'],'observed_status':row['M1_status']})
    data={'scope':'READ_ONLY_SAVED_CLOCK_AUDIT_NO_API_M1',
        'long_event_threshold_s':60,'long_formal_M1_events':long,
        'all_raw_M1_wall_s':sum(all_m1),'formal_M1_count':len(all_m1),
        'median_formal_M1_s':statistics.median(all_m1),
        'raw_run_wall_s':sum(r['total_wall_s'] for r in runs),
        'raw_API_latency_s':sum(r['API_latency_s'] for r in runs),
        'cause':'Unidentified wall-clock interruption during an in-flight formal M1 call. Logs alone do not prove sleep, manual pause, or evaluator CPU runtime.',
        'pause_resume_request':'User requested pause then continue; controller has no saved process interruption receipt. Original process completed once; no restart or replay occurred.',
        'no_active_compute_estimate':True,
        'exclude_from_normal_latency_claims':True,
        'raw_durations_not_removed':True,
        'new_API_M1_M2':0}
    with (OUT/'CLOCK_ANOMALY_AUDIT.json').open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)
    lines=['# 墙钟异常与暂停/继续记录','',
        '主批次按同一原进程执行完一次，没有重启或补跑。用户在执行期间提出暂停后又明确继续；没有保存进程中断回执，因此不能声称实验实际暂停后恢复。',
        '', f"正式M1共{len(all_m1)}次，原始累计M1墙钟{sum(all_m1):.6f}秒，其中超过60秒的调用{len(long)}次。所有原始耗时保留。"]
    for e in long:
        lines += ['',f"{e['run_id']}第{e['M1_index']}次正式M1耗时{e['M1_wall_s']:.6f}秒，落在{e['region_id']}的SLSQP路径；该轮API延迟{e['API_latency_s']:.6f}秒，首PASS已在{e['first_PASS_elapsed_s']:.6f}秒取得。长间隔出现在首点之后，不改变首点耗时。"]
    lines += ['', '日志只能把长间隔定位到正在执行的M1调用，不能证明是机器休眠、用户暂停、操作系统调度还是计算耗时。故原始总墙钟及M1累计值作为实际记录呈现，同时将该调用单独标记；不从总时长偷偷扣除，不把长间隔归为LLM Provider延迟，也不估造“净活跃计算时间”。',
        '', 'p50/p95不代表没有这个离群点；必须连同累计值、最长调用和本说明阅读。失败/未命中仍保留全分母与实际删失时刻。分析新增M1/API/M2均0。']
    with (OUT/'CLOCK_ANOMALY_NOTE.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps({'formal_M1':len(all_m1),'long_events':len(long),'raw_M1_wall_s':sum(all_m1),'new_API_M1_M2':0}))


if __name__=='__main__':main()
