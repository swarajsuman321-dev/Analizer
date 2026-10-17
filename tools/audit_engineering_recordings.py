"""Audit alignment and comparison using supplied private bench recordings."""
import json,time,sys,gc
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app_analysis_service import align_recordings,compare_recordings
from app_alignment_merge import merge_alignment
from app_channel_store import ChannelStore
from app_data import BUILTIN_SYNC_STRATEGIES
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--power',type=Path,required=True);parser.add_argument('--machine',type=Path,required=True);parser.add_argument('--tdms',type=Path,required=True);parser.add_argument('--simulation',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
power,machine,tdms,simulation=args.power,args.machine,args.tdms,args.simulation
args.output.parent.mkdir(parents=True,exist_ok=True)
report=[]
def save():args.output.write_text(json.dumps(report,indent=2,default=str))
for target in (machine,tdms):
 for strategy in BUILTIN_SYNC_STRATEGIES:
  start=time.monotonic();r={'machine':target.name,'strategy':strategy}
  try:
   result=align_recordings(str(power),str(target),strategy,3.5);store,score=result[:2];combined=ChannelStore();new,updated,remap=merge_alignment(combined,store);count=len(combined.channels);ids=set(combined.channels)
   new,updated,remap=merge_alignment(combined,store);assert not new and set(combined.channels)==ids and len(combined.channels)==count
   r.update(status='passed',channels=count,datasets=len(store.datasets),duplicate_new_channels=len(new),seconds=round(time.monotonic()-start,3))
   del store,combined,result;gc.collect()
  except Exception as e:
   expected=target==tdms and ('do not overlap' in str(e) or 'needs a drum speed/feedback' in str(e))
   r.update(status='expected_rejection' if expected else 'failed',reason=str(e),seconds=round(time.monotonic()-start,3))
  report.append(r);save();print(json.dumps(r),flush=True)
for target in (machine,tdms):
 start=time.monotonic();r={'machine':target.name,'scenario':'Comparison against supplied simulation'}
 try:
  store,score=compare_recordings(str(target),str(simulation));r.update(status='passed',channels=len(store.channels),metrics=len(score),classifications=score['status'].value_counts().to_dict(),seconds=round(time.monotonic()-start,3));del store,score;gc.collect()
 except Exception as e:r.update(status='failed',error=str(e))
 report.append(r);save();print(json.dumps(r),flush=True)

raise SystemExit(1 if any(r["status"]=="failed" for r in report) else 0)
