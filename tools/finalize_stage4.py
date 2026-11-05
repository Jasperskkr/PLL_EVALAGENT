"""Summarize actual Stage4 measurements and raw-signal diagnostics; never overwrite."""
from pathlib import Path
import argparse,csv,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.verification.experiments import read,write
from pll_allocation.verification.return_ratio_validity import raw_diagnostics,make_extension

def main(study,harmonics,out):
 study,out=Path(study),Path(out);out.mkdir(parents=True,exist_ok=False)
 harmonic=read(Path(harmonics)/"harmonic_diagnostics.json")
 comparisons=[];responses=[];extensions={}
 for case in ("nominal","real_agent","pm_boundary"):
  folder=study/case;doc=read(folder/"protocol.json");raw=raw_diagnostics(folder,doc)
  write(out/(case+"_raw_diagnostics.json"),raw)
  item=make_extension(folder,harmonic[case],raw);write(out/(case+"_extension.json"),item);extensions[case]=item
  m1=read(folder/"M1_posthoc.json")["metrics"];rr=read(folder/"return_ratio_result.json");bw=read(folder/"BW_result.json")
  for name in ("BW_Hz","UGF_Hz","PM_deg"):
   metric=item["metrics"][name];local=metric.get("diagnostic_series_value");direct=metric.get("diagnostic_direct_clamp_value")
   value=metric["value"];pred=m1[name]
   comparisons.append({"case":case,"metric":name,"M1_prediction":pred,"M2_certified_measurement":value,"diagnostic_series_value":local,"diagnostic_direct_port_value":direct,"error_absolute":value-pred if value is not None else None,"error_relative":value/pred-1 if value is not None else None,"diagnostic_error_absolute":local-pred if local is not None else None,"diagnostic_error_relative":local/pred-1 if local is not None else None,"status":next((c["status"] for c in bw["constraints"] if c["metric"]==name),"UNKNOWN"),"reliability":metric["status"],"unit":metric["unit"],"overall_status":item["overall_status"]})
  for variant,run in rr["runs"].items():
   for point in run["points"]:
    re,im=point["L_complex"]
    responses.append({"case":case,"variant":variant,"frequency_Hz":point["frequency_Hz"],"L_real":re,"L_imag":im,"magnitude":point["magnitude"],"phase_deg":point["phase_deg"],"point_numerical_status":point["status"],"point_reasons":";".join(point["reasons"]),"periodic_PM_certified":False,**point["quality"],**{k+"_"+part:v[i] for k,v in point["phasors"].items() for i,part in enumerate(("real","imag"))}})
 for name,rows in [("m1_m2_ugf_pm_comparison.csv",comparisons),("frequency_response.csv",responses)]:
  with (out/name).open("x",encoding="utf-8",newline="") as s:
   writer=csv.DictWriter(s,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 write(out/"summary.json",{"cases":{k:{"scientific_status":v["scientific_status"],"local_measurement_status":v["local_measurement_status"],"metrics":v["metrics"],"raw_signal_checks":v["evidence"]["raw_signal_checks"]} for k,v in extensions.items()},"response_rows":len(responses)})
 print(json.dumps({k:v["local_measurement_status"] for k,v in extensions.items()}))
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--study",required=True);p.add_argument("--harmonics",required=True);p.add_argument("--out",required=True);a=p.parse_args();main(a.study,a.harmonics,a.out)
