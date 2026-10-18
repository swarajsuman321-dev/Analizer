"""Reproducible recording audit. This tool does not copy input files into Git.

The four user-authorized repository fixtures can be selected explicitly; other
recordings and generated workspaces remain in the requested output directory.

Usage: QT_QPA_PLATFORM=offscreen python tools/audit_recordings.py \
 --input file.tdms --input machine.csv --input power.CSV --input simulation.csv \
 --output /path/to/private-audit
"""
import argparse
from itertools import combinations
import hashlib
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PySide6 import QtWidgets
from app_channel_store import ChannelStore
from app_ingestion import ingest
from app_workbench import AdvancedStudioWindow
from app_reporting import export_report,interval_tables
from app_tdms_templates import ParameterReview,ParameterTemplates,identity
from app_workspace_io import save_workspace,load_workspace


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,action='append',required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--full-workspace',action='store_true');args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);os.environ['ANALIZER_OUTPUT_DIR']=str(args.output/'app-output')
    report={'inputs':[],'scenarios':[],'limitations':['Automated desktop checks do not replace a human Windows visual review.','Finite scenario coverage; not every possible malformed file or interaction sequence.']}
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([]);window=AdvancedStudioWindow();window.resize(1440,960);window.show();app.processEvents()
    errors=[];original=sys.excepthook
    def hook(kind,value,tb):errors.append(str(value));original(kind,value,tb)
    sys.excepthook=hook
    def save():
        (args.output/'results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    def scenario(name,fn):
        start=time.monotonic()
        try:
            detail=fn();app.processEvents()
            if errors:raise AssertionError('Qt callback exceptions: '+repr(errors))
            row={'name':name,'status':'passed','seconds':round(time.monotonic()-start,3),'detail':detail}
        except Exception as exc:row={'name':name,'status':'failed','seconds':round(time.monotonic()-start,3),'error':str(exc)}
        report['scenarios'].append(row);save();print(json.dumps(row),flush=True)
    stores=[]
    try:
        for path in args.input:
            start=time.monotonic();store=ChannelStore();ingest(store,path);stores.append(store)
            channels=list(store.channels.values());assert channels
            for c in channels:
                assert np.isfinite(c.x).all() and np.all(np.diff(c.x)>=0)
                assert c.coordinate_unit=='min'
            report['inputs'].append({'name':path.name,'bytes':path.stat().st_size,'sha256':hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),'import_seconds':round(time.monotonic()-start,3),'source_rows':[len(d.frame) for d in store.datasets.values()],'channels':len(channels),'measurements':sum(len(c.y) for c in channels),'end_min':max(float(c.x[-1]) for c in channels if len(c.x)),'nonfinite_values':sum(int((~np.isfinite(c.y)).sum()) for c in channels)})
            save()
        for n in range(1,len(stores)+1):
            for indexes in combinations(range(len(stores)),n):
                def check(indexes=indexes):
                    window.drop_recordings(list(window.store.datasets),clear_all=True)
                    merged=ChannelStore()
                    for i in indexes:merged.datasets.update(stores[i].datasets);merged.channels.update(stores[i].channels)
                    window.merge_store(merged);window.dashboard.arrange_readable();app.processEvents()
                    count=sum(len(stores[i].channels) for i in indexes);assert len(window.store.channels)==count
                    selected={id for p in window.dashboard.visible_panes() for id in p.ids};assert selected==set(merged.channels)
                    for mode,enabled in [('x',(True,False)),('y',(False,True)),('xy',(True,True))]:
                        window.studio.navigation(mode);p=window.dashboard.active;before=[list(r) for r in p.getViewBox().viewRange()];p.zoom_all(.8);after=p.getViewBox().viewRange()
                        assert tuple(p.getViewBox().state['mouseEnabled'])==enabled
                        if not enabled[0]:np.testing.assert_allclose(before[0],after[0])
                        if not enabled[1]:np.testing.assert_allclose(before[1],after[1])
                    window.dashboard.active.fit()
                    p=next(p for p in window.dashboard.visible_panes() if p.ids);anchor=p.ids[0];p.lock_cursor(0,anchor);p.step_cursor(0,1);p.setXRange(-100,10000,padding=0);app.processEvents();assert p.cursor_locks[0]['channel']==anchor
                    stats=p.measurements();assert anchor in stats
                    window.set_channel_visibility(list(merged.channels),False);app.processEvents()
                    assert all(not p.ids and not p.axes for p in window.dashboard.panes)
                    window._readouts();assert window.readout.rowCount()==0
                    window.set_channel_visibility(list(merged.channels),True);window.dashboard.arrange_readable();app.processEvents()
                    ds=next(iter(merged.datasets));removed={c.id for c in merged.channels.values() if c.dataset_id==ds}
                    window.comparison.assign(list(removed)[:2]);window.drop_recordings([ds]);app.processEvents()
                    assert removed.isdisjoint(window.store.channels)
                    for w in window.workspaces:
                        for pane in w.panes:assert removed.isdisjoint(pane.ids)
                    return {'input_indexes':list(indexes),'channels':count,'checks':['all traces','zoom X/Y/XY','locked cursor stepping','out-of-bounds pan','deselect/reselect all','remove recording from both workspaces']}
                scenario('Input combination '+','.join(map(str,indexes)),check)
        def review():
            store=next(s for s in stores if any(c.attributes.get('format')=='TDMS' for c in s.channels.values()))
            template=ParameterTemplates(args.output/'template-test.json');dialog=ParameterReview(template.unknown(store),window);dialog.show();app.processEvents()
            count=dialog.table.rowCount();assert count==len(store.channels)
            entries=dialog.entries();template.save(entries);dialog.close()
            loaded=ParameterTemplates(args.output/'template-test.json');assert not loaded.unknown(store)
            copied=ChannelStore();copied.channels=dict(store.channels);loaded.apply(copied)
            for id,c in store.channels.items():
                assert copied.channels[id].name==entries[identity(c)]['name'];np.testing.assert_equal(c.x,copied.channels[id].x)
                np.testing.assert_equal(c.values()[1],copied.channels[id].values()[1])
            return {'reviewed':count,'saved_choices':len(entries),'unknown_after_restart':0}
        scenario('TDMS first review and template restart',review)
        window.drop_recordings(list(window.store.datasets),clear_all=True);merged=ChannelStore()
        for s in stores:merged.datasets.update(s.datasets);merged.channels.update(s.channels)
        window.merge_store(merged);window.dashboard.arrange_readable();app.processEvents()
        for pane in window.dashboard.visible_panes():
            pane.cursor_lines[0].setValue(.1);pane.cursor_lines[1].setValue(.3)
        def exports():
            data,summary=interval_tables(window.store,window.dashboard.state());assert len(summary)==len(merged.channels)
            for suffix in ('csv','xlsx','pdf','png'):
                path=args.output/('active-interval.'+suffix);export_report(path,window.store,window.dashboard.state());assert path.stat().st_size>100
            return {'summary_channels':len(summary),'interval_rows':len(data),'formats':['csv','xlsx','pdf','png']}
        scenario('Mixed input active interval exports',exports)
        def workspace():
            path=save_workspace(args.output/'full-workspace.json',window.store,[w.state() for w in window.workspaces],window.ui_state());restored,views,ui=load_workspace(path)
            assert len(restored.channels)==len(window.store.channels)
            for id,c in window.store.channels.items():
                np.testing.assert_equal(c.x,restored.channels[id].x);np.testing.assert_equal(c.y,restored.channels[id].y)
            for id,ds in window.store.datasets.items():
                import pandas as pd
                pd.testing.assert_frame_equal(ds.frame,restored.datasets[id].frame)
            return {'channels':len(restored.channels),'datasets':len(restored.datasets),'json_bytes':path.stat().st_size}
        if args.full_workspace:scenario('Full mixed workspace save and restore',workspace)
        report['passed']=all(r['status']=='passed' for r in report['scenarios']);save()
    finally:window.close();app.processEvents();sys.excepthook=original
    return 0 if report.get('passed') else 1


if __name__=='__main__':raise SystemExit(main())
