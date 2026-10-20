"""Audit regressions for reviewed engineering roles and timing disclosures."""
import copy
import tempfile
import os
import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
import pandas as pd
from app_channel_store import Channel,ChannelStore,Dataset
from app_appliance_profiles import load_profile,channel_key
from app_engineering_analytics import analyze_run,scoped_run
from app_engineering_session import default_session,analyze_session,validate_session
from app_engineering_templates import MappingTemplates
from app_engineering_trace import Trace


class EngineeringTrustAuditTests(unittest.TestCase):
    def setUp(self):
        self.store=ChannelStore();self.profile=load_profile();ds=Dataset('Reviewed fixture',pd.DataFrame(),'')
        self.store.datasets[ds.id]=ds;self.dataset=ds.id

    def add(self,name,y,unit='',t=None,**attributes):
        return self.store.add(Channel(name,np.asarray(t if t is not None else range(len(y)),float),np.asarray(y,float),unit=unit,coordinate_unit='s',dataset_id=self.dataset,attributes=attributes))

    def kpi(self,run,key):return next(row for row in run['kpis'] if row['id']==key)

    def test_command_and_feedback_require_explicit_review_and_override_survives_identity_change(self):
        command=self.add('Drump Speed',[0,1200,0],'RPM')
        feedback=self.add('Drump speed feedback',[0,1175,0],'RPM')
        run=analyze_run(self.store,self.profile)
        self.assertIsNone(self.kpi(run,'peak_speed')['value'])
        self.assertIn('confirm',self.kpi(run,'peak_speed')['next_action'].lower())
        mapping={channel_key(command):'target_speed',channel_key(feedback):'speed'}
        with tempfile.TemporaryDirectory() as root:
            templates=MappingTemplates(Path(root)/'mappings.json');templates.save(self.profile,mapping)
            restored=MappingTemplates(templates.path).get(self.profile)
            run=analyze_run(self.store,self.profile,restored)
        self.assertEqual(self.kpi(run,'peak_speed')['value'],1175)
        self.assertEqual(self.kpi(run,'target_speed')['value'],600)
        source=self.kpi(run,'peak_speed')['source_details'][0]
        self.assertEqual(source['source_name'],feedback.name);self.assertEqual(source['review_status'],'Confirmed')
        self.assertEqual(command.unit,'RPM')

    def test_direct_pressure_and_pulse_time_conflict_cannot_silently_become_pressure(self):
        direct=self.add('water pressure',[1,2,3],'Pa')
        pulse=self.add('Water Pressure pulse time',[100,200,300],'us')
        # Reproduce the audit's two different sensor dimensions claiming one role.
        mappings={direct.id:'water_pressure',pulse.id:'water_pressure'}
        run=analyze_run(self.store,self.profile,mappings)
        self.assertNotIn('water_pressure',run['traces'])
        self.assertTrue(any('conversion' in row['review_reason'].lower() for row in run['mapping']))
        run=analyze_run(self.store,self.profile,{direct.id:'water_pressure',pulse.id:None})
        self.assertIn('water_pressure',run['traces'])
        run=analyze_run(self.store,self.profile,{direct.id:None,pulse.id:'water_pressure'})
        self.assertNotIn('water_pressure',run['traces'])
        spec=next(c for c in self.profile['channels'] if c['id']=='water_pressure');spec['calibration']='pulse_pressure'
        self.profile['calibrations']['pulse_pressure']={'id':'LOGGER-SPEC-1','verified':True,'input_unit':'us','output_unit':'Pa','x':[100,300],'y':[1,3]}
        run=analyze_run(self.store,self.profile,{direct.id:None,pulse.id:'water_pressure'})
        np.testing.assert_allclose(run['traces']['water_pressure'].y,[1,2,3])
        np.testing.assert_allclose(pulse.y,[100,200,300])

    def test_readiness_distinguishes_missing_unit_phase_and_acceptance(self):
        self.add('Current Temperature',[20,30,40],'')
        run=analyze_run(self.store,self.profile)
        self.assertEqual(self.kpi(run,'peak_temperature')['blocker'],'Unverified unit / calibration')
        self.assertEqual(self.kpi(run,'total_energy')['blocker'],'Missing source')
        states={row['state'] for row in run['readiness']}
        self.assertIn('Unsupported phase',states);self.assertIn('Unconfigured acceptance',states)
        self.assertTrue(all(row['next_action'] for row in run['readiness'] if not row['usable']))
        self.assertEqual(run['readiness_summary']['calculation'],'Complete')
        self.assertEqual(run['readiness_summary']['acceptance'],'Not Evaluated')

    def test_inferred_unit_needs_confirmation_without_rewriting_original_metadata(self):
        channel=self.add('Water temperature',[20,21,22],'°C',unit_detection='signal name')
        run=analyze_run(self.store,self.profile)
        self.assertIsNone(self.kpi(run,'peak_temperature')['value'])
        run=analyze_run(self.store,self.profile,source_units={channel.id:'°C'})
        self.assertEqual(self.kpi(run,'peak_temperature')['value'],22)
        self.assertEqual(channel.attributes['unit_detection'],'signal name')

    def test_quality_flags_are_independent_and_supported_totals_are_explicit(self):
        self.add('Power',[0,900,100,np.nan,100,100],'W',t=[0,0,1,2,3,20])
        self.profile['extensions']['max_gap_seconds']=2
        run=analyze_run(self.store,self.profile);result=self.kpi(run,'total_energy');quality=result['quality']
        self.assertEqual(quality['duplicate_timestamps'],1);self.assertEqual(quality['missing_readings'],1)
        self.assertAlmostEqual(quality['supported_duration_s'],1);self.assertAlmostEqual(quality['coverage'],.05)
        self.assertEqual(quality['gap_count'],1);self.assertEqual(quality['gap_threshold_s'],2)
        self.assertTrue({'Partial coverage','Duplicate timestamps','Missing readings','Unsupported gaps'}<=set(result['quality_flags']))
        self.assertEqual(result['quantity_basis'],'Supported-time total')
        self.assertIn('supported intervals',result['reason'].lower())
        self.assertEqual(self.kpi(run,'peak_power')['value'],900)

    def test_gap_alerts_are_data_quality_and_missing_source_is_not_evaluated(self):
        self.add('Power',[1,1,1],'W',t=[0,1,20]);self.profile['extensions']['max_gap_seconds']=2
        self.profile['anomalies']=[{'name':'Power gaps','type':'dropout','channel':'power'},{'name':'Absent speed','type':'dropout','channel':'speed'}]
        events=analyze_run(self.store,self.profile)['anomalies']
        self.assertEqual(events[0]['category'],'Data Quality');self.assertEqual(events[0]['status'],'Detected')
        self.assertIn('does not establish an appliance fault',events[0]['interpretation'])
        self.assertEqual(events[-1]['status'],'Not evaluated')
        self.assertTrue(all(event['event_id'].startswith('EV-') for event in events))

    def test_whole_run_coverage_uses_recording_scope_not_just_short_sensor_span(self):
        self.add('Power',[100,100],'W',t=[5,10]);self.add('Unknown clocked sensor',[1,1],'V',t=[0,20])
        result=self.kpi(analyze_run(self.store,self.profile),'total_energy')
        self.assertAlmostEqual(result['coverage'],.25)
        self.assertAlmostEqual(result['quality']['observed_span_s'],5)
        self.assertAlmostEqual(result['quality']['requested_span_s'],20)

    def test_scopes_recalculate_not_scale_and_preserve_original_event_ids(self):
        self.add('Power',[0,1000,0],'W',t=[0,60,120])
        self.profile['anomalies']=[{'name':'Configured power event','type':'condition','channel':'power','conditions':[{'channel':'power','op':'gt','value':500}]}]
        run=analyze_run(self.store,self.profile);interval=scoped_run(run,120,60)
        self.assertEqual(interval['anomalies'][0]['event_id'],run['anomalies'][0]['event_id'])
        self.assertEqual(interval['anomalies'][0]['original_start_s'],30)
        self.assertEqual(interval['anomalies'][0]['start_s'],60)
        self.assertGreaterEqual(interval['traces']['power'].t[0],60)
        self.assertAlmostEqual(self.kpi(interval,'total_energy')['value'],1/120)
        self.assertEqual(self.kpi(interval,'cycle_duration')['value'],1)
        self.assertEqual(run['report_scope'],'whole_recording')
        session=default_session();session['runs']['analysis']=self.dataset
        result=analyze_session(self.store,session,report_scope='both',cursor_interval_s=[60,120])
        self.assertEqual([r['report_scope'] for r in result['runs']],['whole_recording','cursor_interval'])

    def test_interval_comparison_envelope_excludes_outside_time(self):
        from app_engineering_compare import compare_runs
        self.add('Power',[100,100,100],'W',t=[0,60,120])
        reference=analyze_run(self.store,self.profile)
        candidate=copy.deepcopy(reference)
        candidate['traces']['power'].y=np.array([110.,110.,110.])
        candidate['traces']['power'].raw_y=np.array([110.,110.,110.])
        self.profile['tolerances']={'power':{'absolute':5,'unit':'W'}}
        comparison=compare_runs(scoped_run(reference,60,120),scoped_run(candidate,60,120),self.profile)
        self.assertAlmostEqual(comparison['envelopes']['power']['coverage_s'],60)
        self.assertAlmostEqual(comparison['envelopes']['power']['duration_s'],60)

    def test_coverage_requirement_is_configurable_and_does_not_invent_default_threshold(self):
        self.add('Power',[100,100,100],'W',t=[0,1,10]);self.profile['extensions']['max_gap_seconds']=2
        run=analyze_run(self.store,self.profile)
        self.assertNotIn('Below configured coverage requirement',self.kpi(run,'total_energy')['quality_flags'])
        self.profile['extensions']['minimum_coverage']={'total_energy':.8}
        self.assertEqual(self.kpi(analyze_run(self.store,self.profile),'total_energy')['blocker'],'Insufficient configured coverage')
        self.profile['extensions']['minimum_coverage']['total_energy']=2
        with self.assertRaises(ValueError):analyze_run(self.store,self.profile)

    def test_template_confirmation_can_be_revoked_without_affecting_other_profiles(self):
        with tempfile.TemporaryDirectory() as root:
            templates=MappingTemplates(Path(root)/'mappings.json')
            templates.save(self.profile,{'A':'speed'},{'A':'RPM'})
            templates.save(load_profile('refrigerator'),{'B':'power'},{'B':'W'})
            templates.save(self.profile,{},replace_profile=True)
            self.assertEqual(templates.get(self.profile),{});self.assertEqual(templates.get_units(self.profile),{})
            self.assertTrue(templates.get(load_profile('refrigerator')))

    def test_counter_totals_do_not_claim_changes_across_unsupported_intervals(self):
        self.add('OOB retries',[0,1,5],'count',t=[0,1,20])
        self.profile['extensions']['max_gap_seconds']=2
        result=self.kpi(analyze_run(self.store,self.profile),'oob_retries')
        self.assertIsNone(result['value'])
        self.assertIn('unknown gaps',result['reason'])

    def test_main_cancel_button_also_cancels_the_managed_engineering_task(self):
        from PySide6 import QtWidgets,QtTest
        from app_workbench import AdvancedStudioWindow
        type(self)._qt_app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'ANALIZER_OUTPUT_DIR':root,'ANALIZER_SETTINGS_DIR':root}):
            window=AdvancedStudioWindow();completed=[]
            def work(token):
                if token.wait(2):raise InterruptedError('cancelled')
                return 42
            try:
                window.engineering.task(work,completed.append)
                token=window.engineering.cancel_token
                window.cancel_operation()
                for _ in range(100):
                    QtTest.QTest.qWait(20)
                    if not window.busy:break
                self.assertFalse(window.busy);self.assertTrue(token.is_set())
                self.assertEqual(completed,[])
            finally:window.close();type(self)._qt_app.processEvents()


if __name__=='__main__':unittest.main()
