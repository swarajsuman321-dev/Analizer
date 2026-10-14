"""Actual-recording checks and an isolated, painted dense-data benchmark."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import resource
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from PySide6 import QtWidgets,QtCore
from app_channel_store import ChannelStore,Channel
from app_ingestion import ingest
from app_signal_processing import transform,formula,IntervalSummary
from app_workspace_io import save_workspace,load_workspace,export_processed,render_report
from app_plot_workspace import PlotWorkspace


def timing(values):
    return {'median_ms':float(np.median(values)), 'p95_ms':float(np.percentile(values,95))}


def benchmark(app,output,channels,samples):
    store=ChannelStore();x=np.linspace(0,1000,samples);start=time.perf_counter()
    for i in range(channels):store.add(Channel(f'Trace {i+1}',x,np.sin(x/(1+i/20))+i*.02,unit='V'))
    workspace=PlotWorkspace(store);workspace.resize(1400,900);workspace.set_layout('2×2');workspace.show()
    ids=list(store.channels)
    for i,pane in enumerate(workspace.visible_panes()):pane.bind(ids[i::4])
    workspace.link();app.processEvents();workspace.grab()
    preparation=(time.perf_counter()-start)*1000
    pan=[];cursor=[];interval=[]
    for i in range(40):
        start=time.perf_counter();workspace.panes[0].setXRange(100+i,500+i,padding=0);app.processEvents();workspace.grab();pan.append((time.perf_counter()-start)*1000)
        start=time.perf_counter();workspace.panes[0].cursor_lines[0].setValue(150+i);workspace.panes[0].cursor_lines[1].setValue(350+i);app.processEvents();workspace.grab();cursor.append((time.perf_counter()-start)*1000)
        start=time.perf_counter()
        for pane in workspace.visible_panes():pane.measurements()
        interval.append((time.perf_counter()-start)*1000)
    result={'channels':channels,'samples_per_channel':samples,'source_points':channels*samples,'binding_and_first_paint_ms':preparation,
            'painted_pan':timing(pan),'painted_dual_cursor':timing(cursor),'interval_queries':timing(interval),
            'displayed_points':sum(len(curve.xData) for pane in workspace.visible_panes() for vb,curve in pane.curves.values()),
            'peak_memory_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            'method':'Qt event processing followed by QWidget.grab forces raster painting; no sustained frame-rate claim'}
    output.mkdir(parents=True,exist_ok=True);(output/'benchmark.json').write_text(json.dumps(result,indent=2));workspace.close()
    return result


def validate(app,output,paths):
    output.mkdir(parents=True,exist_ok=True);store=ChannelStore();counts=[]
    for path in paths:
        ids=ingest(store,path);counts.append({'path':str(path),'channels':len(ids),'rows':sum(len(d.frame) for d in store.datasets.values() if d.source==str(path))})
    if not store.channels:raise ValueError('No channels imported')
    first=next(iter(store.channels.values()));derived=transform(first,'Offset and scale',scale=2);store.add(derived)
    workspace=PlotWorkspace(store);workspace.assign([first.id,derived.id]);workspace.show();app.processEvents()
    path=save_workspace(output/'workspace.json',store,[workspace.state()]);restored,views,ui=load_workspace(path)
    for id,c in store.channels.items():
        np.testing.assert_array_equal(c.x,restored.channels[id].x);np.testing.assert_array_equal(c.y,restored.channels[id].y)
    for id,d in store.datasets.items():pd.testing.assert_frame_equal(d.frame,restored.datasets[id].frame)
    exported=export_processed(output/'processed.csv',[derived]);readback=pd.read_csv(output/'processed.csv')
    np.testing.assert_allclose(readback['value'],exported['value'],equal_nan=True,rtol=1e-12)
    for suffix in ('png','svg','pdf','html','md'):render_report(output/('presentation.'+suffix),store,workspace.state())
    result={'imports':counts,'channels_restored':len(restored.channels),'datasets_restored':len(restored.datasets),'processed_rows':len(readback),'exact_snapshot_roundtrip':True,'presentation_formats':['png','svg','pdf','html','md']}
    (output/'report.json').write_text(json.dumps(result,indent=2));workspace.close();return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--benchmark-only',action='store_true');parser.add_argument('--channels',type=int,default=100);parser.add_argument('--samples',type=int,default=100001)
    for name in ('power','machine','simulation'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.channels<1 or args.samples<3:parser.error('Use positive channels and at least three samples')
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    result=benchmark(app,args.output,args.channels,args.samples) if args.benchmark_only else validate(app,args.output,[p for p in (args.power,args.machine,args.simulation) if p])
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
