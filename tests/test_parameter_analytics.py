"""Hand-calculated native-resolution capability and trusted-extension checks."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import numpy as np

from app_parameter_analytics import analyse_field, capability_registry
from app_parameter_capabilities import CapabilityDefinition, CapabilityRegistry
from app_extensions import PluginManager


def projection(values, x=None, **extra):
    return dict(values=np.asarray(values), x_s=None if x is None else np.asarray(x,float),
        source_indices=np.arange(len(values)), valid=np.ones(len(values),bool),
        structure='analog',role='',instance='',unit='',status='computed',
        acquisition_policy={'mode':'continuous','max_gap_seconds':10.,'duplicate_clock':'reject'},
        provenance={}, **extra)


def mapped(role='',**extra):
    return dict(authority={'reviewed':True},encoding={'stored_values':'engineering'},role=role,parameters={},**extra)


def metrics(output):
    return {record['metric_id']:record for record in output['metrics']}


class NativeCapabilitiesTests(unittest.TestCase):
    def test_unknown_has_raw_native_stats_but_no_fake_time(self):
        p=projection([1.,4.,np.nan,7.]); before=p['values'].copy()
        records=metrics(analyse_field(p,run_id='run',field_id='field'))
        self.assertEqual(records['maximum']['value'],7)
        self.assertEqual(records['maximum']['source_sample_indices'],[3])
        self.assertEqual(records['valid_sample_count']['value'],3)
        self.assertIsNone(records['time_mean']['value'])
        self.assertEqual(records['time_mean']['status'],'insufficient_data')
        self.assertNotIn('active_power.supported_energy',records)
        np.testing.assert_equal(p['values'],before)
        json.dumps(records,allow_nan=False)

    def test_piecewise_linear_moments_sampling_density_invariant(self):
        sparse=metrics(analyse_field(projection([0.,10.],[0.,10.])))
        dense=metrics(analyse_field(projection([0.,1.,2.,9.,10.],[0.,1.,2.,9.,10.])))
        for name in ('time_mean','time_rms','time_std','minimum_slope','maximum_slope','supported_duration'):
            self.assertAlmostEqual(sparse[name]['value'],dense[name]['value'],places=12)
        self.assertAlmostEqual(sparse['time_mean']['value'],5.)
        self.assertAlmostEqual(sparse['time_rms']['value'],np.sqrt(100/3))
        self.assertAlmostEqual(sparse['time_std']['value'],np.sqrt(100/12))

    def test_scope_between_samples_retains_interpolated_support(self):
        records=metrics(analyse_field(projection([0.,10.],[0.,10.]),scopes=[{'kind':'stage','start_s':2.,'end_s':8.}]))
        self.assertAlmostEqual(records['time_mean']['value'],5.)
        self.assertAlmostEqual(records['supported_duration']['value'],6.)
        self.assertEqual(records['sample_count']['value'],0)

    def test_gaps_are_not_zero_and_known_support_is_separate(self):
        p=projection([2.,2.,np.nan,8.,8.],[0.,1.,2.,10.,11.])
        p['acquisition_policy']['max_gap_seconds']=2
        records=metrics(analyse_field(p))
        self.assertEqual(records['supported_duration']['value'],2.)
        self.assertAlmostEqual(records['time_mean']['value'],5.)
        self.assertEqual(records['time_mean']['status'],'partial')
        self.assertAlmostEqual(records['coverage_fraction']['value'],2/11)

    def test_duplicate_policy_must_be_explicit_and_first_is_honoured(self):
        p=projection([0.,100.,10.],[0.,0.,10.])
        records=metrics(analyse_field(p))
        self.assertIsNone(records['time_mean']['value'])
        p['acquisition_policy']['duplicate_clock']='first'
        records=metrics(analyse_field(p))
        self.assertAlmostEqual(records['time_mean']['value'],5.)
        self.assertEqual(records['maximum']['value'],100.)
        p['acquisition_policy']['duplicate_clock']='last'
        self.assertAlmostEqual(metrics(analyse_field(p))['time_mean']['value'],55.)

    def test_explicit_custom_role_bands_need_no_ui_change(self):
        p=projection([0.,10.],[0.,10.]);p.update(role='custom_clamp_force',unit='N')
        mapping=mapped();mapping['parameters']={'bands':[{'name':'operating','low':2.,'high':8.}], 'distribution_bins':[0,5,10]}
        records=metrics(analyse_field(p,mapping=mapping))
        self.assertAlmostEqual(records['dwell:operating']['value'],6.)
        self.assertAlmostEqual(records['dwell:operating.fraction']['value'],.6)
        rows=records['supported_distribution']['value']
        self.assertEqual([r['duration_s'] for r in rows],[5.,5.])
        self.assertNotIn('measured_flow.supported_volume',records)

    def test_enum_never_gets_mean_of_codes(self):
        p=projection([34,34,42,34],[0,1,2,3]);p.update(structure='enum',unit='code')
        p['acquisition_policy']['mode']='held'
        records=metrics(analyse_field(p,mapping={'state_dictionary':{'34':'idle','42':'working'}}))
        self.assertNotIn('time_mean',records)
        self.assertEqual(records['state.transition_count']['value'],2)
        self.assertEqual(records['state.state_sequence']['value'],[34,42,34])
        rows=records['state.occupancy']['value']
        self.assertEqual({r['label']:r['duration_s'] for r in rows},{'idle':2.,'working':1.})

    def test_counter_reset_and_rollover_are_distinct(self):
        p=projection([8.,9.,1.,3.],[0,1,2,3]);p.update(structure='counter',unit='count')
        mapping=mapped(); mapping['counter_policy']={'reset':'split'}
        result=analyse_field(p,mapping=mapping);records=metrics(result)
        self.assertEqual(records['counter.increment']['value'],3.)
        self.assertEqual(records['counter.reset_count']['value'],1)
        self.assertEqual(records['counter.increment']['status'],'partial')
        mapping['counter_policy']={'reset':'rollover','modulus':10.,'source':'documented fixture'}
        records=metrics(analyse_field(p,mapping=mapping))
        self.assertEqual(records['counter.increment']['value'],5.)
        self.assertEqual(records['counter.rollover_count']['value'],1)
        self.assertEqual(records['counter.reset_count']['value'],0)
        self.assertNotIn('time_mean',records)

    def test_countdown_changes_are_not_consumption(self):
        p=projection([60.,59.,59.,65.,63.],[0,1,2,3,4]);p.update(structure='countdown',unit='min')
        mapping=mapped();mapping['parameters']={'pause_tolerance':0.,'jump_threshold':3.}
        records=metrics(analyse_field(p,mapping=mapping))
        self.assertEqual(records['countdown.upward_revision_count']['value'],1)
        self.assertEqual(records['countdown.pause_duration']['value'],1.)
        self.assertEqual(records['countdown.jump_count']['value'],1)
        self.assertIsNone(records['countdown.final_estimate_error']['value'])
        self.assertNotIn('counter.increment',records)

    def test_measured_flow_integrates_native_time_and_missing_support(self):
        p=projection([60.,60.,np.nan,120.,120.],[0,30,40,60,90]);p.update(role='measured_flow',unit='L/min',signal_kind='measurement')
        p['acquisition_policy']['max_gap_seconds']=30.
        records=metrics(analyse_field(p,mapping=mapped('measured_flow')))
        self.assertAlmostEqual(records['measured_flow.supported_volume']['value'],90.)
        self.assertEqual(records['measured_flow.supported_volume']['status'],'partial')
        p['signal_kind']='command'
        self.assertIsNone(metrics(analyse_field(p,mapping=mapped()))['measured_flow.supported_volume']['value'])

    def test_active_power_energy_requires_review_and_measured_power(self):
        p=projection([1.,1.],[0.,3600.]);p.update(role='active_power',unit='kW',signal_kind='measurement')
        p['acquisition_policy']['max_gap_seconds']=3600.
        self.assertEqual(metrics(analyse_field(p,mapping=mapped()))['active_power.supported_energy']['value'],1000.)
        self.assertIsNone(metrics(analyse_field(p))['semantic.availability']['value'])
        p['unit']='A'
        self.assertEqual(metrics(analyse_field(p,mapping=mapped()))['active_power.supported_energy']['status'],'needs_mapping')

    def test_rotation_does_not_invent_direction_retry_or_soak(self):
        p=projection([-100.,0.,100.],[0.,1.,2.]);p.update(role='rotational_speed',unit='RPM',signal_kind='feedback')
        mapping=mapped();mapping['parameters']={'stationary_tolerance':10.,'plateau_slope_tolerance':1.}
        records=metrics(analyse_field(p,mapping=mapping))
        self.assertAlmostEqual(records['speed.stationary_duration']['value'],.2)
        self.assertAlmostEqual(records['speed.rotation_duration']['value'],1.8)
        self.assertEqual(records['speed.directional_activity']['status'],'needs_mapping')
        self.assertEqual(records['speed.confirmed_retry_count']['status'],'missing_input')
        self.assertEqual(records['speed.soak_duration']['status'],'missing_input')
        mapping['direction']={'encoding':'signed','confirmed':True}
        records=metrics(analyse_field(p,mapping=mapping))
        self.assertAlmostEqual(records['speed.positive_duration']['value'],.9)
        self.assertAlmostEqual(records['speed.negative_duration']['value'],.9)

    def test_rotation_target_hold_and_direction_sequence_cross_zero(self):
        p=projection([0.,100.,100.,100.,0.,-100.,-100.],[0.,1.,2.,3.,4.,5.,6.])
        p.update(role='rotational_speed',unit='RPM',signal_kind='feedback')
        mapping=mapped();mapping['parameters']={'stationary_tolerance':0.,'plateau_slope_tolerance':0.,
            'target_band':{'low':90.,'high':110.,'hold_seconds':1.,'settling_policy':'hold'}}
        mapping['direction']={'encoding':'signed','confirmed':True}
        records=metrics(analyse_field(p,mapping=mapping))
        self.assertAlmostEqual(records['speed.target.time_to_reach']['value'],.9)
        self.assertAlmostEqual(records['speed.target.settling_time']['value'],.9)
        self.assertEqual(records['speed.direction_reversal_count']['value'],1)
        self.assertEqual(records['speed.observed_start_count']['value'],2)
        mapping['parameters']['target_band']['settling_policy']='through_end'
        self.assertIsNone(metrics(analyse_field(p,mapping=mapping))['speed.target.settling_time']['value'])

    def test_held_distribution_does_not_double_count_boundary(self):
        p=projection([5.,5.,10.],[0.,1.,2.]);p['acquisition_policy']['mode']='held'
        records=metrics(analyse_field(p,mapping={'parameters':{'distribution_bins':[0,5,10]}}))
        self.assertEqual([r['duration_s'] for r in records['supported_distribution']['value']],[0.,2.])

    def test_documented_uint64_bitfield_decodes_without_float_rounding(self):
        high=2**63
        p=projection(np.array([high+1,high,0],dtype=np.uint64),[0.,1.,2.]);p.update(structure='bitfield',unit='code')
        p['acquisition_policy']['mode']='held'
        mapping=mapped();mapping['parameters']={'bit_masks':[{'name':'low','mask':1,'documented':True,'source':'fixture'},
            {'name':'high','mask':high,'documented':True,'source':'fixture'}]}
        result=analyse_field(p,mapping=mapping)
        durations={m['instance']:m['value'] for m in result['metrics'] if m['metric_id']=='state.on_duration_s'}
        self.assertEqual(durations,{'/low':1.,'/high':2.})
        self.assertEqual(metrics(result)['bitfield.undecoded_values']['value'],[0])

    def test_large_native_integer_extrema_and_counter_increments_are_exact(self):
        base=2**63
        p=projection(np.array([base+2,base+1,base+3],dtype=np.uint64),[0.,1.,2.])
        records=metrics(analyse_field(p))
        self.assertEqual(records['minimum']['value'],base+1)
        self.assertEqual(records['maximum']['value'],base+3)
        self.assertEqual(records['range']['value'],2)
        self.assertEqual(records['maximum']['source_sample_indices'],[2])
        self.assertIsNone(records['time_mean']['value'])
        p['structure']='counter'
        mapping=mapped();mapping['counter_policy']={'reset':'split'}
        self.assertEqual(metrics(analyse_field(p,mapping=mapping))['counter.increment']['value'],2)

    def test_suppressed_short_state_pulses_remain_in_evidence(self):
        p=projection([0,1,0,0],[0.,1.,1.1,2.]);p['structure']='binary';p['acquisition_policy']['mode']='held'
        result=analyse_field(p,mapping={'parameters':{'min_dwell_s':.2}})
        self.assertTrue(any(e.get('suppressed') for e in result['events']))
        self.assertEqual(metrics(result)['state.rising_count']['value'],1)
        self.assertAlmostEqual(metrics(result)['state.on_duration_s']['value'],.1)

    def test_cancellation_event_and_capability_failure_isolation(self):
        registry=capability_registry().clone()
        def failing(projection,c):
            c.emit('must_rollback',123)
            c.quality.append({'wrong':True})
            raise ValueError('fixture failure')
        registry.register(CapabilityDefinition('fixture.failing',structures=('analog',)),failing,trusted=True)
        result=analyse_field(projection([1.,2.],[0.,1.]),registry=registry)
        records=metrics(result)
        self.assertNotIn('must_rollback',records)
        self.assertEqual(records['fixture.failing.availability']['status'],'error')
        self.assertEqual(records['maximum']['value'],2.)
        self.assertFalse(any(row.get('wrong') for row in result['quality']))
        cancel=threading.Event();cancel.set()
        with self.assertRaises(InterruptedError): analyse_field(projection([1.]),cancelled=cancel)


class TrustedRegistryTests(unittest.TestCase):
    def test_registry_requires_valid_trusted_immutable_definition(self):
        registry=CapabilityRegistry()
        definition=CapabilityDefinition('fixture.custom',parameters={'nested':{'bands':[1,2]}})
        with self.assertRaises(TypeError): definition.parameters['nested']['bands'][0]=5
        with self.assertRaises(ValueError): registry.register(definition,lambda *_:None)
        registry.register(definition,lambda *_:None,trusted=True)
        with self.assertRaises(ValueError): registry.register(definition,lambda *_:None,trusted=True)
        with self.assertRaises(ValueError): CapabilityDefinition('invalid id')
        json.dumps(registry.definitions(),allow_nan=False)

    def test_analyser_only_patch_and_failed_registration_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=PluginManager(Path(tmp)/'patches')
            example=Path(__file__).resolve().parents[1]/'examples/parameter_plugins/native_median_absolute_deviation.py'
            manager.install(example)
            records=metrics(analyse_field(projection([1.,2.,9.]),registry=manager.parameter_registry))
            self.assertEqual(records['example.native_mad']['value'],1.)
            self.assertEqual(records['example.native_mad']['definition_version'],'1')
            bad=Path(tmp)/'bad.py'
            bad.write_text("from app_parameter_capabilities import CapabilityDefinition\ndef register_patch(m):\n m.register_analyser(CapabilityDefinition('fixture.rollback'),lambda p,c:None)\n raise ValueError('rollback')\n",encoding='utf-8')
            with self.assertRaises(ValueError):manager.install(bad)
            names={d['capability_id'] for d in manager.parameter_registry.definitions()}
            self.assertNotIn('fixture.rollback',names)
            self.assertIn('example.native_mad',names)
            manager.set_enabled(example.name,False)
            self.assertNotIn('example.native_mad',{d['capability_id'] for d in manager.parameter_registry.definitions()})
    def test_comparator_only_patch_and_registry_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=PluginManager(Path(tmp)/'patches')
            plugin=Path(tmp)/'pair.py'
            plugin.write_text("from app_parameter_capabilities import CapabilityDefinition\ndef register_patch(m):\n m.register_comparator(CapabilityDefinition('example.pair'),lambda left,right,context:[])\n",encoding='utf-8')
            manager.install(plugin)
            self.assertIn('example.pair',{d['capability_id'] for d in manager.comparator_registry.definitions()})
            plugin.write_text("from app_parameter_capabilities import CapabilityDefinition\ndef register_patch(m):\n m.register_comparator(CapabilityDefinition('fixture.fail'),lambda l,r,c:[])\n raise ValueError('failed comparator')\n",encoding='utf-8')
            with self.assertRaises(ValueError):manager.install(plugin)
            self.assertNotIn('fixture.fail',{d['capability_id'] for d in manager.comparator_registry.definitions()})


if __name__=='__main__': unittest.main()
