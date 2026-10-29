"""Regression contracts for the real recording behind the 4,049-page audit."""
import copy
import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from app_appliance_profiles import load_profile
from app_channel_store import Channel,ChannelStore,Dataset
from app_engineering_analytics import analyze_run
from app_engineering_reports import export_engineering,report_preview,report_tables
from app_engineering_report_summary import summarize_events,union_duration
from app_engineering_report_pdf import plot_samples,cursor_trace_values


class AuditReportUsabilityTests(unittest.TestCase):
    def small(self):
        store=ChannelStore();dataset=Dataset('Known power',pd.DataFrame(),'')
        store.datasets[dataset.id]=dataset
        store.add(Channel('Power',np.arange(0,601,60),np.arange(11)*100.,unit='W',coordinate_unit='s',dataset_id=dataset.id))
        return store,analyze_run(store,load_profile(),dataset_id=dataset.id)

    def test_interval_union_is_not_naive_event_duration_sum(self):
        self.assertEqual(union_duration([(0,4),(2,6),(10,12)]),8)
        rows=[{'Run':'Analysis','Scope':'Whole recording','event_id':str(i),'name':'gap','type':'dropout','status':'Detected','start_s':a,'end_s':b,'duration_s':b-a,'gap_threshold_s':.447,'evidence':{'channel':'speed'}} for i,(a,b) in enumerate([(0,4),(2,6),(10,12)])]
        grouped=summarize_events(rows)[0]
        self.assertEqual(grouped['count'],3);self.assertEqual(grouped['affected_time_union_s'],8)
        self.assertEqual(grouped['longest_interval_s'],4);self.assertEqual(grouped['first_s'],0)
        self.assertEqual(grouped['last_s'],12);self.assertEqual(set(grouped['event_ids']),{'0','1','2'})

    def test_event_growth_never_changes_default_page_budget(self):
        _,run=self.small();first=report_preview([run])
        larger={**run,'anomalies':[{'name':'gap'}]*100000}
        self.assertEqual(first['expected_pages'],report_preview([larger])['expected_pages'])
        self.assertEqual(first['expected_pages'],10)
        self.assertEqual(report_preview([larger],detailed_appendix=True)['appendix_pages'],5000)

    def test_required_results_continue_readably_beyond_default_page_budget(self):
        store,run=self.small()
        for result in run['kpis']:result['definition']['mandatory']=True
        plan=report_preview([run])
        self.assertEqual(plan['required_result_records'],31)
        self.assertEqual(plan['result_continuation_pages'],2)
        self.assertEqual(plan['expected_pages'],12)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'Required-results.pdf';export_engineering(path,store,[run])
            self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',path.read_bytes())),12)
            self.assertEqual(json.loads(path.with_suffix('.evidence.json').read_text())['page_plan']['expected_pages'],12)

    def test_gap_plot_never_connects_unobserved_time(self):
        from app_engineering_trace import Trace
        trace=Trace(Channel('Pressure',[0,1,20,21],[1,2,3,4],unit='Pa'),max_gap_seconds=3)
        x,y=plot_samples(trace)
        self.assertTrue(np.isnan(y).any());self.assertEqual(trace.raw_y.tolist(),[1,2,3,4])

    def test_report_locked_cursor_retains_exact_duplicate_source_observation(self):
        from app_engineering_trace import Trace
        channel=Channel('Measured power',[0,1,1,2],[2,8,11,4],unit='W')
        trace=Trace(channel)
        values=cursor_trace_values(trace,[1/60,2/60],[{'channel':channel.id,'index':1},None])
        self.assertEqual(values.tolist(),[8,4])
        scoped=trace.scoped(1,2)
        values=cursor_trace_values(scoped,[1/60,2/60],[{'channel':channel.id,'index':1},None])
        self.assertEqual(values.tolist(),[8,4])

    def test_interval_cursor_readouts_follow_ui_snap_policy_using_original_clock(self):
        from app_engineering_trace import Trace
        trace=Trace(Channel('Power',[0,10,20],[0,100,0],unit='W')).scoped(4,15)
        self.assertEqual(cursor_trace_values(trace,[4/60,15/60],snap=True).tolist(),[0,0])
        self.assertEqual(cursor_trace_values(trace,[4/60,15/60],snap=False).tolist(),[40,50])

    def test_reduced_gap_plot_preserves_observed_peak_without_gap_connections(self):
        from app_engineering_trace import Trace
        t=np.arange(2000.);t[1000:]+=100
        y=np.sin(t);y[1000]=1200
        trace=Trace(Channel('Speed',t,y,unit='RPM'),max_gap_seconds=3)
        x,values=plot_samples(trace,budget=100)
        self.assertEqual(np.nanmax(values),1200)
        self.assertTrue(np.isnan(values).any())

    def test_pdf_companions_share_id_and_preserve_full_event_records(self):
        store,run=self.small()
        run['anomalies']=[{'name':'Acquisition gap','type':'dropout','status':'Detected','start_s':float(i),'end_s':float(i+2),'duration_s':2.,'evidence':{'channel':'speed','threshold':'configured'}} for i in range(25)]
        run['warnings']=[]
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'Summary.pdf';tables=export_engineering(path,store,[run])
            document=path.read_bytes()
            self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',document)),10)
            data=json.loads(path.with_suffix('.evidence.json').read_text())
            self.assertEqual(len(data['tables']['Fault & Anomaly Log']),25)
            self.assertEqual(len(pd.read_csv(path.with_suffix('.events.csv'))),25)
            workbook=pd.read_excel(path.with_suffix('.evidence.xlsx'),sheet_name=None)
            self.assertEqual(len(workbook['Fault & Anomaly Log']),25)
            self.assertEqual(workbook['Fault & Anomaly Log']['report_id'].nunique(),1)
            self.assertEqual(workbook['Fault & Anomaly Log']['report_id'].iloc[0],data['report_id'])
            self.assertEqual(data['event_groups'][0]['affected_time_union_s'],26)
            self.assertEqual(tables['Fault & Anomaly Log']['event_id'].nunique(),25)

    def test_interval_and_both_scopes_recalculate_the_same_pdf_workbook_kpis(self):
        store,run=self.small()
        with tempfile.TemporaryDirectory() as root:
            interval=Path(root)/'Interval.xlsx'
            tables=export_engineering(interval,store,[run],scope='cursor_interval',view={'cursors':[2,4]})
            kpis=tables['KPI Results'];duration=kpis[kpis.id=='cycle_duration'].iloc[0]
            self.assertEqual(duration.value,2)
            self.assertTrue((kpis.Scope=='Active cursor interval').all())
            both=export_engineering(Path(root)/'Both.xlsx',store,[run],scope='both',view={'cursors':[4,2]})
            values=both['KPI Results'];durations=values[values.id=='cycle_duration']
            self.assertEqual(set(durations.value),{2.,10.})
            self.assertEqual(set(durations.Scope),{'Whole recording','Active cursor interval'})

    def test_comparison_with_missing_results_keeps_nullable_colors_and_both_scopes(self):
        from app_engineering_compare import compare_runs
        store,reference=self.small();reference['role']='reference'
        dataset=Dataset('Candidate',pd.DataFrame(),'');store.datasets[dataset.id]=dataset
        source=next(iter(store.channels.values()))
        store.add(Channel('Power',source.x,source.y*1.2,unit='W',coordinate_unit='s',dataset_id=dataset.id))
        candidate=analyze_run(store,reference['profile'],dataset_id=dataset.id);candidate['role']='candidate'
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'Comparison.pdf'
            tables=export_engineering(path,store,[reference,candidate],compare_runs(reference,candidate,reference['profile']),view={'cursors':[2,4]},scope='both')
            self.assertEqual(set(tables['Comparison Results'].Scope),{'Whole recording','Active cursor interval'})
            evidence=json.loads(path.with_suffix('.evidence.json').read_text())
            self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',path.read_bytes())),evidence['page_plan']['expected_pages'])
            self.assertEqual(evidence['page_plan']['comparison_records'],len(tables['Comparison Results']))
            self.assertGreater(evidence['page_plan']['comparison_continuation_pages'],0)
            from openpyxl import load_workbook
            workbook=load_workbook(path.with_suffix('.evidence.xlsx'))
            self.assertTrue(any(dim.hidden for dim in workbook['Comparison Results'].column_dimensions.values()))

    def test_cancel_does_not_publish_any_partial_companion_or_replace_report(self):
        store,run=self.small();token=threading.Event()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'Summary.pdf';path.write_bytes(b'previous report')
            with patch('app_engineering_reports.write_pdf',side_effect=InterruptedError('cancelled')):
                with self.assertRaises(InterruptedError):export_engineering(path,store,[run],cancel=token)
            self.assertEqual(path.read_bytes(),b'previous report')
            self.assertFalse(path.with_suffix('.evidence.xlsx').exists())
            self.assertFalse(path.with_suffix('.evidence.json').exists())
            self.assertFalse(path.with_suffix('.events.csv').exists())

    def test_bundle_commit_failure_restores_the_entire_previous_evidence_set(self):
        from app_engineering_reports import staged_report_bundle
        import os
        replace=os.replace
        with tempfile.TemporaryDirectory() as root:
            paths=[Path(root)/name for name in ('Summary.pdf','Summary.evidence.json','Summary.events.csv')]
            for index,path in enumerate(paths):path.write_bytes(b'previous '+str(index).encode())
            def fail_one_publish(source,destination):
                if Path(destination)==paths[1] and Path(source).read_bytes()==b'new':raise OSError('Simulated full disk')
                return replace(source,destination)
            with patch('app_engineering_reports.os.replace',side_effect=fail_one_publish):
                with self.assertRaisesRegex(OSError,'full disk'):
                    with staged_report_bundle(paths) as staged:
                        for temporary in staged.values():temporary.write_bytes(b'new')
            for index,path in enumerate(paths):self.assertEqual(path.read_bytes(),b'previous '+str(index).encode())

    def test_engineering_projection_lock_and_selection_resolve_to_source_identity(self):
        from app_engineering_reports import source_view_identity
        store,run=self.small();source=next(iter(store.channels.values()))
        projected=store.add(Channel('Power · Reference',source.x/60,source.y,unit='W',coordinate_unit='min',dataset_id=source.dataset_id,parents=[source.id],attributes={'engineering_projection':True}))
        original_view={'cursors':[2,4],'cursor_locks':[{'channel':projected.id,'index':2},None]}
        view,selected=source_view_identity(store,original_view,[projected.id])
        self.assertEqual(view['cursor_locks'][0]['channel'],source.id)
        self.assertEqual(view['cursor_locks'][0]['projected_channel'],projected.id)
        self.assertEqual(selected,[source.id])
        self.assertEqual(original_view['cursor_locks'][0]['channel'],projected.id)

    def test_hash_matched_audit_recording_bounded_pdf_complete_log(self):
        from app_ingestion import ingest
        source=Path(__file__).parent/'samples/recordings/Cotton 60 label with 4kg IEC load RD T-3 (1).csv'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),'a235a5917c7f01484fb328fd1986cb7298140e7068cd24151518e5f96ee75558')
        store=ChannelStore();ingest(store,source)
        # Reproduce the audited mapping explicitly. Acknowledging this source in
        # a test does not declare its physical role correct for the end user.
        mappings={channel.id:('speed' if channel.name=='Drump Speed' else None) for channel in store.channels.values()}
        run=analyze_run(store,load_profile(),mappings,dataset_id=next(iter(store.datasets)))
        drops=[event for event in run['anomalies'] if event['type']=='dropout' and event['status']=='Detected']
        self.assertEqual(len(drops),10195)
        # Audit original 10,231 records included legacy warning multiplicity.
        # Rendering that preserved legacy evidence must remain bounded even if
        # current interpretation adds more actionable warnings.
        run['warnings']=[]
        run['anomalies']=drops+[{'name':'Legacy unevaluated rule '+str(i),'type':'condition','status':'Not evaluated','start_s':None,'end_s':None,'duration_s':None,'evidence':{'legacy_audit_record':i}} for i in range(36)]
        before=copy.deepcopy(run['anomalies'])
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'Audited-fixture.pdf';tables=export_engineering(path,store,[run])
            self.assertEqual(len(tables['Fault & Anomaly Log']),10231)
            self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',path.read_bytes())),10)
            data=json.loads(path.with_suffix('.evidence.json').read_text())
            self.assertEqual(len(data['tables']['Fault & Anomaly Log']),10231)
            self.assertEqual(data['event_groups'][0]['count'],10195)
            self.assertGreater(data['event_groups'][0]['affected_time_union_s'],0)
            self.assertEqual(len(pd.read_csv(path.with_suffix('.events.csv'))),10231)
            workbook=pd.read_excel(path.with_suffix('.evidence.xlsx'),sheet_name='Fault & Anomaly Log')
            self.assertEqual(len(workbook),10231);self.assertEqual(workbook.event_id.nunique(),10231)
            self.assertEqual(run['anomalies'],before)


if __name__=='__main__':unittest.main()
