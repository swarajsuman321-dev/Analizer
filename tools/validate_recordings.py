"""Validate established PD/RD alignment and source-preserving workbook export."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from app_data import DataEngine,smart_read_file
from app_analysis_service import compare_recordings


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--power',required=True);parser.add_argument('--machine',required=True);parser.add_argument('--simulation');parser.add_argument('--strategy',default='Intelligent');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    engine=DataEngine(args.power,args.machine,args.strategy);aligned=engine.get_data()
    if aligned.empty:raise ValueError('Alignment produced no rows')
    power,machine=smart_read_file(args.power),smart_read_file(args.machine)
    report={'aligned_rows':len(aligned),'power_source_rows':len(power),'machine_source_rows':len(machine),'synchronization':engine.sync_report}
    book=args.output/'engineering.xlsx'
    with pd.ExcelWriter(book) as writer:
        power.to_excel(writer,sheet_name='Original_Power',index=False);machine.to_excel(writer,sheet_name='Original_Machine',index=False)
        aligned.to_excel(writer,sheet_name='Aligned',index=False)
        if args.simulation:
            store,score=compare_recordings(args.machine,args.simulation);score.to_excel(writer,sheet_name='Scorecard',index=False)
            reference=next(ds for ds in store.datasets.values() if ds.source==args.simulation)
            reference.frame.to_excel(writer,sheet_name='Original_Simulation',index=False);report['simulation_source_rows']=len(reference.frame);report['comparison_counts']=score['status'].value_counts().to_dict()
    if len(pd.read_excel(book,sheet_name='Original_Power'))!=len(power) or len(pd.read_excel(book,sheet_name='Original_Machine'))!=len(machine):raise AssertionError('Original workbook rows were lost')
    (args.output/'report.json').write_text(json.dumps(report,indent=2,default=str));print(json.dumps(report,indent=2,default=str))

if __name__=='__main__':main()
