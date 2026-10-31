"""Physics, missing-data rules and reproducibility for configurable engineering."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from app_channel_store import Channel,ChannelStore,Dataset
from app_appliance_profiles import load_profile,validate_profile,recognize
from app_engineering_units import convert,calibrated
from app_engineering_trace import Trace
from app_engineering_analytics import analyze_run
from app_engineering_compare import envelope,delta_kpis,anchor_seconds,deviation_color
from app_engineering_session import default_session,analyze_session
from app_engineering_reports import export_engineering,SHEETS


class EngineeringTests(unittest.TestCase):
    def setUp(self):self.store=ChannelStore();self.profile=load_profile()
    def add(self,name,y,unit='',t=None,kind='analog',dataset=None,**attrs):
        if dataset is None:
            dataset=next(iter(self.store.datasets),None)
            if dataset is None:
                ds=Dataset('Test',pd.DataFrame(),'');self.store.datasets[ds.id]=ds;dataset=ds.id
        return self.store.add(Channel(name,np.array(t if t is not None else [0,60,120],float),np.array(y,float),unit=unit,coordinate_unit='s',kind=kind,dataset_id=dataset,attributes=attrs))
    def result(self,key,run=None):return next(r for r in (run or analyze_run(self.store,self.profile))['kpis'] if r['id']==key)

    def test_profiles_schemas_and_unknown_keys(self):
        for name in ('washing_machine','refrigerator','dishwasher','hvac','generic_appliance'):self.assertEqual(load_profile(name)['schema_version'],1)
        bad=copy.deepcopy(self.profile);bad['unknown']=1
        with self.assertRaises(ValueError):validate_profile(bad)
        bad=copy.deepcopy(self.profile);bad['kpis'][0]['op']='eval'
        with self.assertRaises(ValueError):validate_profile(bad)

    def test_known_energy_flow_temperature_and_partial_availability(self):
        self.add('Power',[1000]*3,'W');self.add('Flow',[6]*3,'L/min');self.add('Water temperature',[20,30,40],'°C')
        self.profile['phases']=[{'name':'Heat','conditions':[{'channel':'temperature','op':'ge','value':20}]}]
        run=analyze_run(self.store,self.profile)
        self.assertAlmostEqual(self.result('total_energy',run)['value'],1/30)
        self.assertAlmostEqual(self.result('total_water',run)['value'],12)
        self.assertAlmostEqual(self.result('heating_rate',run)['value'],10)
        self.assertEqual(self.result('vibration_rms',run)['status'],'Not Available')
        self.assertEqual(self.result('total_energy',run)['acceptance'],'Not Evaluated')

    def test_temperature_and_power_only_does_not_invent_water_or_motor(self):
        self.add('Power',[100]*3,'W');self.add('Water temperature',[20,21,22],'°C')
        for key in ('total_water','peak_speed','vibration_rms','oob_retries'):self.assertIsNone(self.result(key)['value'])

    def test_units_affine_calibration_and_original_arrays(self):
        self.assertAlmostEqual(float(convert(273.15,'K','°C')),0)
        self.assertAlmostEqual(float(convert(1,'bar','mm H₂O')),100000/9.80665)
        self.assertAlmostEqual(float(convert(60,'L/min','L/s')),1)
        self.assertAlmostEqual(float(convert(1000,'μS/cm','µS/cm')),1000)
        with self.assertRaises(ValueError):convert(1,'kHz','Pa')
        with self.assertRaises(ValueError):calibrated([2],{'verified':False},'L')
        cal={'id':'CAL-1','verified':True,'x':[1,3],'y':[0,10],'output_unit':'L'}
        self.assertAlmostEqual(calibrated([2],cal,'L')[0],5);self.assertTrue(np.isnan(calibrated([4],cal,'L')[0]))
        c=self.add('Power',[1,1,1],'kW');before=c.y.copy();self.assertAlmostEqual(self.result('total_energy')['value'],1/30);np.testing.assert_array_equal(c.y,before);self.assertFalse(c.y.flags.writeable)

    def test_mapping_priority_and_ambiguous_candidates(self):
        c=self.add('Power',[1,2,3],'W',canonical_id='heater_power')
        self.assertEqual(recognize(self.store,self.profile)[0]['canonical_id'],'heater_power')
        self.assertEqual(recognize(self.store,self.profile,{c.id:'power'})[0]['canonical_id'],'power')
        self.assertIsNone(recognize(self.store,self.profile,{c.id:None})[0]['canonical_id'])
        self.profile['channels'][1]['aliases'].append('Power');c.attributes.clear()
        row=recognize(self.store,self.profile)[0];self.assertIsNone(row['canonical_id']);self.assertGreater(len(row['candidates']),1)

    def test_duplicate_mapping_requires_review(self):
        self.add('Power',[1,2,3],'W');self.add('Active power',[1,2,3],'W')
        self.assertIsNone(self.result('total_energy')['value'])

    def test_gap_coverage_duplicates_and_no_extrapolation(self):
        c=self.add('Power',[0,1000,np.nan,1000,1000,1000],'W',t=[0,0,60,120,180,1000])
        trace=Trace(c,'W',max_gap_seconds=70)
        self.assertTrue(np.isnan(trace.sample([-1,500,1001])).all());self.assertEqual(trace.sample([0])[0],1000)
        self.assertAlmostEqual(trace.stats()['known_s'],60);self.assertLess(trace.stats()['coverage'],1)
        self.assertEqual(len(c.x),6)

    def test_discrete_nonzero_actuators_and_unknown_fraction(self):
        self.add('Inlet valve',[0,128,0],'state',kind='discrete')
        self.assertAlmostEqual(self.result('fill_duration')['value'],1)

    def test_configured_phases_debounce_overlap_and_no_invented_names(self):
        self.add('Inlet valve',[0,128,128,0],'state',t=[0,10,20,40],kind='discrete')
        self.assertEqual(analyze_run(self.store,self.profile)['phases'],[])
        self.profile['phases']=[{'name':'Fill','conditions':[{'channel':'cold_valve','op':'on'}],'minimum_seconds':5,'debounce_seconds':2}]
        phases=analyze_run(self.store,self.profile)['phases'];self.assertEqual(len(phases),1);self.assertEqual(phases[0]['start_s'],12);self.assertEqual(phases[0]['end_s'],40)

    def test_acceptance_is_explicit_and_quality_qualified(self):
        self.add('Power',[1000]*3,'W');self.profile['acceptance']={'peak_power':{'max':900,'unit':'W'}}
        self.assertEqual(self.result('peak_power')['acceptance'],'Fail');self.assertEqual(self.result('total_energy')['acceptance'],'Not Evaluated')

    def test_mixed_rate_tolerance_crossing_and_zero_reference(self):
        a=Trace(self.add('A',[0,0],'W',t=[0,10]),'W');b=Trace(self.add('B',[0,5,10],'W',t=[0,5,10]),'W')
        result=envelope(a,b,{'absolute':2,'unit':'W'})
        self.assertEqual(result['count'],1);self.assertAlmostEqual(result['duration_s'],8);self.assertAlmostEqual(result['first_s'],2);self.assertIsNone(result['max_percent'])
        self.assertEqual(result['coverage_s'],10)

    def test_discrete_envelope_does_not_interpolate_codes_or_bridge_gaps(self):
        a=Trace(self.add('A',[0,0,0],'state',t=[0,5,10],kind='discrete'),'state');b=Trace(self.add('B',[0,128,0],'state',t=[0,5,10],kind='discrete'),'state')
        result=envelope(a,b,{'absolute':0});self.assertAlmostEqual(result['duration_s'],5);self.assertEqual(result['first_s'],5)
        c=Trace(self.add('C',[1,np.nan,1],'state',t=[0,5,10],kind='discrete'),'state');self.assertEqual(envelope(a,c,{})['coverage_s'],0)

    def test_time_dependent_limits_validate_and_undefined_percent_is_neutral(self):
        a=Trace(self.add('A',[10,10],'°C',t=[0,10]),'°C');b=Trace(self.add('B',[12,12],'°C',t=[0,10]),'°C')
        result=envelope(a,b,{'times_s':[0,10],'lower':[9,9],'upper':[11,13],'unit':'°C'})
        self.assertAlmostEqual(result['duration_s'],5)
        with self.assertRaises(ValueError):envelope(a,b,{'times_s':[0,0],'lower':[0,0],'upper':[1,1]})
        self.assertIsNone(deviation_color(None));self.assertNotEqual(deviation_color(5),deviation_color(5.1));self.assertNotEqual(deviation_color(10),deviation_color(10.1))

    def test_anchor_no_source_mutation_and_cancel(self):
        c=self.add('Inlet valve',[0,128,0],'state',kind='discrete');before=c.x.copy()
        self.assertEqual(anchor_seconds(self.store,{'mode':'actuator','channel_id':c.id}),60);np.testing.assert_array_equal(c.x,before)
        token=threading.Event();token.set()
        with self.assertRaises(InterruptedError):analyze_run(self.store,self.profile,cancel=token)

    def test_reports_have_nine_sheets_traceability_na_and_vector_pdf(self):
        self.add('Power',[1000]*3,'W');run=analyze_run(self.store,self.profile)
        with tempfile.TemporaryDirectory() as root:
            xlsx=Path(root)/'report.xlsx';pdf=Path(root)/'report.pdf'
            export_engineering(xlsx,self.store,[run]);tables=pd.read_excel(xlsx,sheet_name=None)
            self.assertEqual(list(tables),SHEETS);self.assertIn('Profile configuration',tables['Test Metadata']['Field'].tolist())
            self.assertIn('Not Available',tables['Executive Summary']['Value'].tolist())
            export_engineering(pdf,self.store,[run]);self.assertTrue(pdf.read_bytes().startswith(b'%PDF'));self.assertGreater(pdf.stat().st_size,15000)
            token=threading.Event();token.set();original=xlsx.read_bytes()
            with self.assertRaises(InterruptedError):export_engineering(xlsx,self.store,[run],cancel=token)
            self.assertEqual(xlsx.read_bytes(),original)

    def test_generic_profile_unknown_channels_load_without_kpi_invention(self):
        self.add('Unknown Sensor',[1,2,3],'V');run=analyze_run(self.store,load_profile('generic_appliance'))
        self.assertIsNone(run['mapping'][0]['canonical_id']);self.assertTrue(all(k['value'] is None for k in run['kpis'] if k['id']!='cycle_duration'));self.assertEqual(self.result('cycle_duration',run)['value'],2)

    def test_session_isolation_and_role_persistence(self):
        a=self.add('Power',[100]*3,'W');ds=Dataset('Candidate',pd.DataFrame(),'');self.store.datasets[ds.id]=ds;b=self.add('Power',[110]*3,'W',dataset=ds.id)
        session=default_session();session['runs'].update(reference=a.dataset_id,candidate=b.dataset_id)
        for id in (a.dataset_id,b.dataset_id):self.store.datasets[id].frame.attrs['program_start']={'source_min':0.,'confirmed':True,'evidence':'Reviewed fixture program start'}
        result=analyze_session(self.store,session,True);row=next(r for r in result['comparison']['kpis'] if r['id']=='peak_power')
        self.assertAlmostEqual(row['percent'],10);self.assertAlmostEqual(row['delta'],10);self.assertEqual(len(self.store.channels),2)

    def test_invalid_profile_conditions_limits_and_calibrations_are_rejected(self):
        for patch in ({'acceptance':{'peak_power':{'max':float('nan')}}},{'tolerances':{'power':{'relative_percent':-1}}},{'phases':[{'name':'Heat','conditions':[{'channel':'temperature','op':'gt'}]}]},{'calibrations':{'bad':{'id':'C','verified':True,'input_unit':'kHz','output_unit':'Pa','x':[2,1],'y':[0,10]}}}):
            with self.subTest(patch=patch):
                with self.assertRaises(ValueError):validate_profile({**self.profile,**patch})

    def test_fractional_actuator_is_unknown_and_source_codes_remain_intact(self):
        c=self.add('Inlet valve',[0,.5,128],'state',kind='discrete');run=analyze_run(self.store,self.profile)
        self.assertTrue(np.isnan(run['traces']['cold_valve'].y[1]));self.assertEqual(c.y[1],.5)

    def test_fault_stall_dropout_and_missing_evidence_are_distinguished(self):
        self.add('Fault code',[0,7,0],'code',kind='discrete');self.add('Water temperature',[20,20,20],'°C')
        self.profile['anomalies']=[{'name':'Confirmed fault','type':'fault','channel':'fault','fault_values':[7]},{'name':'Temperature stall','type':'stall','channel':'temperature','window_seconds':60,'maximum_change':.1,'minimum_seconds':1},{'name':'Missing vibration','type':'dropout','channel':'vibration_x'}]
        rows=analyze_run(self.store,self.profile)['anomalies'];self.assertEqual(rows[0]['status'],'Detected');self.assertEqual(rows[0]['start_s'],60);self.assertEqual(rows[-1]['status'],'Not evaluated')
        self.assertEqual(next(r for r in rows if r['name']=='Temperature stall')['status'],'Detected')

    def test_temperature_std_is_stable_for_large_sensor_offset(self):
        c=self.add('Water temperature',[1e12,1e12+1,1e12+2],'°C');stats=Trace(c,'°C').stats()
        self.assertAlmostEqual(stats['std'],(1/3)**.5,places=6)

    def test_relative_envelope_splits_at_reference_zero_crossing(self):
        a=Trace(self.add('A',[-10,10],'W',t=[0,10]),'W');b=Trace(self.add('B',[0,0],'W',t=[0,10]),'W')
        record=envelope(a,b,{'relative_percent':50});self.assertAlmostEqual(record['duration_s'],10);self.assertEqual(len(record['grid']),3)

    def test_canonical_templates_reuse_source_identity_without_replacing_user_override(self):
        from app_engineering_templates import MappingTemplates
        from app_appliance_profiles import channel_key
        c=self.add('Logger value',[1,2,3],'W')
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'mapping.json';templates=MappingTemplates(path);templates.save(self.profile,{channel_key(c):'power'})
            saved=MappingTemplates(path).get(self.profile)
            self.assertEqual(recognize(self.store,self.profile,saved)[0]['canonical_id'],'power')
            self.assertEqual(recognize(self.store,self.profile,{**saved,c.id:'heater_power'})[0]['canonical_id'],'heater_power')

    def test_analog_phase_crossings_and_hysteresis_use_real_crossing_time(self):
        self.add('Water temperature',[0,10,5,0],'°C',t=[0,10,20,30])
        self.profile['phases']=[{'name':'Heat','conditions':[{'channel':'temperature','op':'gt','value':8,'off_threshold':4}]}]
        phase=analyze_run(self.store,self.profile)['phases'][0];self.assertAlmostEqual(phase['start_s'],8);self.assertAlmostEqual(phase['end_s'],22)

    def test_configured_actuator_sequence_and_missing_window_stall(self):
        self.add('Heater',[0,1,1,0],'state',t=[0,10,20,30],kind='discrete');self.add('Drain pump',[0,0,1,0],'state',t=[0,10,20,30],kind='discrete')
        self.profile['anomalies']=[{'name':'Confirmed forbidden order','type':'sequence','channel':'heater','sequence':[{'channel':'heater','op':'on'},{'channel':'drain','op':'on'}],'within_seconds':30}]
        result=analyze_run(self.store,self.profile)['anomalies'][0];self.assertEqual(result['status'],'Detected');self.assertEqual(result['start_s'],10);self.assertEqual(result['end_s'],20)
        self.add('Water temperature',[20,np.nan,20,20],'°C',t=[0,60,120,180]);self.profile['anomalies']=[{'name':'Stall','type':'stall','channel':'temperature','window_seconds':120,'maximum_change':.1}]
        self.assertEqual(analyze_run(self.store,self.profile)['anomalies'][0]['status'],'Not evaluated')

    def test_counter_reset_is_not_reported_as_valid_increase(self):
        self.add('OOB retries',[0,10,5],'count')
        result=self.result('oob_retries');self.assertIsNone(result['value']);self.assertIn('reset',result['reason'].lower())

    def test_confirmed_unit_override_does_not_modify_recorded_unit(self):
        c=self.add('Power',[1000]*3,'');run=analyze_run(self.store,self.profile,source_units={c.id:'W'})
        self.assertAlmostEqual(self.result('total_energy',run)['value'],1/30);self.assertEqual(c.unit,'')

    def test_absolute_recorded_origins_and_unknown_timezone(self):
        a=self.add('Power',[100]*3,'W',time_origin='2026-01-01T00:00:00+00:00');ds=Dataset('B',pd.DataFrame(),'');self.store.datasets[ds.id]=ds
        b=self.add('Power',[110]*3,'W',dataset=ds.id,time_origin='2026-01-01T00:01:00+00:00')
        session=default_session();session['runs'].update(reference=a.dataset_id,candidate=b.dataset_id)
        session['anchors']={role:{'mode':'recorded'} for role in ('reference','candidate')}
        result=analyze_session(self.store,session,True);self.assertEqual(result['runs'][1]['offset_s'],60)
        from app_engineering_compare import recording_origin
        b.attributes['time_origin']='2026-01-01T00:01:00'
        self.assertIsNone(recording_origin(self.store,b.dataset_id));self.assertIsNotNone(recording_origin(self.store,b.dataset_id,'UTC'))

    def test_unverified_or_estimated_reference_does_not_receive_formal_pass(self):
        c=self.add('Power',[1000]*3,'W',reference_calibration_verified=False)
        self.assertIsNone(self.result('total_energy')['value'])
        c.attributes.update(reference_calibration_verified=True,values_estimated_from_pixels=True)
        self.profile['acceptance']={'peak_power':{'max':1100,'unit':'W'}}
        result=self.result('peak_power');self.assertEqual(result['status'],'Estimated source');self.assertEqual(result['acceptance'],'Not Evaluated')

    def test_affine_rms_and_temperature_difference_acceptance_use_correct_units(self):
        self.add('Water temperature',[0,100,0],'°C')
        self.profile['kpis'].append({'id':'temperature_rms_kelvin','name':'Temperature RMS K','channel':'temperature','op':'rms','unit':'K','group':'Thermal'})
        self.profile['acceptance']={'temperature_stability':{'max':30,'unit':'K'}}
        run=analyze_run(self.store,self.profile);stability=self.result('temperature_stability',run)
        self.assertEqual(stability['acceptance'],'Pass')
        rms=self.result('temperature_rms_kelvin',run)['value'];self.assertAlmostEqual(rms,(273.15**2+273.15*100+10000/3)**.5,places=6)

    def test_broken_bundled_profile_does_not_prevent_legacy_workbench_startup(self):
        from unittest.mock import patch
        with patch('app_engineering_session.load_profile',side_effect=ValueError('invalid bundled profile')):
            session=default_session();self.assertTrue(session['profile_warning']);self.assertEqual(session['profile']['kpis'],[])

    def test_duplicate_peaks_are_preserved_and_timing_does_not_receive_pass(self):
        self.add('Power',[0,900,100,100],'W',t=[0,0,60,120]);self.profile['acceptance']={'peak_power':{'max':1000,'unit':'W'}}
        result=self.result('peak_power');self.assertEqual(result['value'],900);self.assertEqual(result['acceptance'],'Not Evaluated');self.assertEqual(result['status'],'Duplicate timestamp timing')

    def test_all_unknown_actuator_intervals_are_not_reported_as_zero_on_time(self):
        self.add('Inlet valve',[0,np.nan,0],'state',kind='discrete')
        self.assertIsNone(self.result('fill_duration')['value'])
