"""Hand-calculated orchestration cases on public synthetic source tables."""
from copy import deepcopy
import json
import math
import threading
import unittest

import numpy as np
import pandas as pd

from app_channel_store import Channel, ChannelStore, Dataset
from app_parameter_comparison import (analyse_recordings, compare_metric_records,
                                      compare_selected_fields, comparator_registry, suggest_pairings)
from app_parameter_capabilities import CapabilityDefinition
from app_parameter_contracts import metric_record
from app_parameter_inventory import inventory_runs
from app_parameter_semantics import default_mapping


class ParameterComparisonTests(unittest.TestCase):
    def fixture(self, x=(100., 101., 102.), y=(0., 1., 2.), bx=(200., 201., 202.),
                by=(1., 2., 3.), *, units=('W', 'W'), structure='analog', extra=None):
        store = ChannelStore()
        channels = []
        for name, times, values, source_unit in zip(('Reference', 'Candidate'), (x, bx), (y, by), units):
            frame = pd.DataFrame({'t': times, 'signal': values})
            frame.attrs['inventory_fields'] = {
                key: {'column_position': i, 'original_name': key, 'length': len(frame), 'clock': 't',
                      'coordinate_unit': 's', 'clock_description': {'kind': 'time', 'trust': 'declared',
                          'domain': 'relative', 'acquisition_policy': 'sampled' if structure == 'analog' else 'held_state'},
                      **({'disposition': 'supporting clock'} if key == 't' else {})}
                for i, key in enumerate(frame.columns)}
            frame.attrs['column_units'] = {'t': 's', 'signal': source_unit}
            dataset = Dataset(name, frame, source=name+'.synthetic')
            store.datasets[dataset.id] = dataset
            channel = store.add(Channel('signal', times, values, unit=source_unit,
                dataset_id=dataset.id, attributes={'source_column': 'signal'}))
            channels.append(channel)
        runs = inventory_runs(store)
        fields = [next(field for field in run['fields'] if field['source_key'] == 'signal') for run in runs]
        mappings = {}
        for field in fields:
            mapping = default_mapping(field)
            mapping.update(structure=structure, role='test_signal', instance='main', signal_kind='measurement',
                unit=field['unit'], encoding={'stored_values': 'engineering'},
                authority={'kind': 'user_confirmed', 'source': 'Synthetic fixture review', 'version': '1', 'reviewed': True},
                acquisition_policy={'mode': 'continuous' if structure == 'analog' else 'held', 'clock_reviewed': True,
                    'max_gap_seconds': None, 'duplicate_clock': 'reject', 'clock_reset': 'reject'})
            if extra:
                mapping.update(deepcopy(extra))
            mappings[field['id']] = mapping
        pairings = [{'reference_field_id': fields[0]['id'], 'candidate_field_id': fields[1]['id'], 'confirmed': True}]
        return store, channels, fields, mappings, pairings

    def result(self, **kwargs):
        store, channels, fields, mappings, pairings = self.fixture(**kwargs)
        return analyse_recordings(store, mappings=mappings, pairings=pairings), store, channels, fields

    @staticmethod
    def pointwise(result):
        return next(row for row in result['comparisons'] if row['comparison_type'].startswith('common_window'))

    def test_elapsed_native_metrics_and_exact_common_error(self):
        result, store, channels, fields = self.result()
        self.assertEqual(result['status'], 'completed', result['readiness'])
        error = self.pointwise(result)
        self.assertEqual(error['status'], 'computed', error)
        self.assertEqual(error['supported_duration_s'], 2)
        self.assertAlmostEqual(error['mean_bias'], 1)
        self.assertAlmostEqual(error['mae'], 1)
        self.assertAlmostEqual(error['rmse'], 1)
        self.assertAlmostEqual(error['absolute_difference_area'], 2)
        self.assertEqual(len(result['inventory']), 4)
        self.assertEqual(result['schema_version'], 2)
        self.assertEqual(result['provenance']['recording_origins_s'][channels[0].dataset_id], 100)
        metric = next(row for row in result['metrics'] if row['field_id'] == fields[0]['id'] and row['metric_id'] == 'time_mean')
        self.assertEqual(metric['value'], 1)
        np.testing.assert_array_equal(channels[0].x, [100, 101, 102])
        np.testing.assert_array_equal(store.datasets[channels[0].dataset_id].frame['signal'], [0, 1, 2])
        json.dumps(result, allow_nan=False)

    def test_pairing_suggestions_never_accept_names(self):
        store, _, fields, mappings, _ = self.fixture()
        generic = analyse_recordings(store)
        self.assertEqual(generic['pairings'], [])
        self.assertEqual(generic['comparisons'], [])
        self.assertEqual(suggest_pairings(generic), [])
        reviewed = analyse_recordings(store, mappings=mappings)
        suggested = suggest_pairings(reviewed)
        self.assertEqual(len(suggested), 1)
        self.assertIs(suggested[0]['confirmed'], False)
        self.assertEqual(reviewed['comparisons'], [])
        self.assertTrue(any(row.get('field_id') == fields[0]['id'] and 'unpaired' in row.get('remedy', '') for row in reviewed['readiness']))

    def test_unconfirmed_or_wrong_kind_pair_is_retained_blocked(self):
        store, _, fields, mappings, pairings = self.fixture()
        pairings[0]['confirmed'] = False
        result = analyse_recordings(store, mappings=mappings, pairings=pairings)
        self.assertEqual(result['pairings'][0]['status'], 'not_comparable')
        self.assertFalse(any(row['comparison_type'] == 'common_window_analog' for row in result['comparisons']))
        pairings[0]['confirmed'] = True
        mappings[fields[1]['id']]['signal_kind'] = 'command'
        result = analyse_recordings(store, mappings=mappings, pairings=pairings)
        self.assertIn('signal kind', ' '.join(result['pairings'][0]['reasons']))

    def test_different_sampling_density_preserves_time_errors(self):
        sparse, *_ = self.result(x=(0., 2.), y=(0., 0.), bx=(20., 22.), by=(-2., 2.))
        times = np.array([20., 20.01, 20.02, 20.03, 20.04, 21., 22.])
        store, _, _, mappings, pairings = self.fixture(x=(0., 2.), y=(0., 0.), bx=times, by=(times-21)*2)
        for mapping in mappings.values():
            mapping['acquisition_policy']['max_gap_seconds'] = 3.
        dense = analyse_recordings(store, mappings=mappings, pairings=pairings)
        for name in ('mean_bias', 'mae', 'rmse', 'supported_duration_s', 'absolute_difference_area'):
            self.assertAlmostEqual(self.pointwise(sparse)[name], self.pointwise(dense)[name], msg=name)

    def test_per_source_gap_limits_and_missing_values_excluded(self):
        store, _, fields, mappings, pairings = self.fixture(x=(0., 1., 10., 11.), y=(0., 0., 0., 0.),
            bx=(20., 21., 30., 31.), by=(1., 1., 1., 1.))
        mappings[fields[0]['id']]['acquisition_policy']['max_gap_seconds'] = 1.1
        mappings[fields[1]['id']]['acquisition_policy']['max_gap_seconds'] = 20
        result = analyse_recordings(store, mappings=mappings, pairings=pairings)
        row = self.pointwise(result)
        self.assertAlmostEqual(row['supported_duration_s'], 2)
        self.assertAlmostEqual(row['mean_bias'], 1)
        self.assertEqual(row['source_gap_limits_s'], [1.1, 20])
        self.assertTrue(any(not interval['supported'] for interval in row['intervals']))

    def test_native_nonoverlap_and_manual_alignment(self):
        store, _, fields, mappings, pairings = self.fixture()
        native = analyse_recordings(store, mappings=mappings, pairings=pairings, options={'alignment': 'native'})
        self.assertEqual(self.pointwise(native)['status'], 'not_comparable')
        candidate_run_id = fields[1]['run_id']
        manual = analyse_recordings(store, mappings=mappings, pairings=pairings,
            options={'alignment': 'manual', 'offsets_s': {candidate_run_id: 1}})
        self.assertEqual(self.pointwise(manual)['supported_duration_s'], 1)
        plots = {row['field_id']: row for row in manual['plot_series']}
        self.assertEqual(plots[fields[1]['id']]['original_x'], [200, 201, 202])
        self.assertEqual(plots[fields[1]['id']]['aligned_x'], [1, 2, 3])

    def test_anchor_requires_confirmation_and_keeps_native_measurements(self):
        store, _, fields, mappings, pairings = self.fixture()
        missing = analyse_recordings(store, mappings=mappings, pairings=pairings, options={'alignment': 'anchor'})
        self.assertEqual(self.pointwise(missing)['status'], 'not_comparable')
        anchored = analyse_recordings(store, mappings=mappings, pairings=pairings,
            options={'alignment': 'anchor', 'anchors_s': {fields[0]['run_id']: 101, fields[1]['run_id']: 201}})
        self.assertEqual(self.pointwise(anchored)['mean_bias'], 1)
        self.assertTrue(any(row.get('time_s') == 102 for row in anchored['metrics'] if row['field_id'] == fields[0]['id'] and row['metric_id'] == 'maximum'))

    def test_state_agreement_has_no_enum_rmse(self):
        result, _, _, fields = self.result(x=(0., 1., 2., 3.), y=(0., 1., 1., 0.),
            bx=(10., 11., 12., 13.), by=(0., 0., 1., 0.), units=('state', 'state'), structure='binary')
        row = self.pointwise(result)
        self.assertEqual(row['comparison_type'], 'common_window_state')
        self.assertEqual(row['agreement_duration_s'], 2)
        self.assertEqual(row['mismatch_duration_s'], 1)
        self.assertNotIn('rmse', row)
        duty = next(row for row in result['comparisons'] if row.get('metric_id') == 'state.duty_cycle')
        self.assertAlmostEqual(duty['delta'], -100/3)
        self.assertEqual(duty['delta_unit'], 'percentage points')
        self.assertIsNone(duty['relative_percent'])

    def test_scalar_affine_difference_and_absolute_temperature_percentage(self):
        a = metric_record('maximum', 100, '°C', role='temperature', instance='sensor')
        b = metric_record('maximum', 212, '°F', role='temperature', instance='sensor')
        difference = compare_metric_records(a, b)
        self.assertAlmostEqual(difference['delta'], 0)
        self.assertIsNone(difference['relative_percent'])
        self.assertIn('temperature', difference['relative_reason'])
        a = metric_record('range', 10, '°C', role='temperature', statistic='difference')
        b = metric_record('range', 18, '°F', role='temperature', statistic='difference')
        self.assertAlmostEqual(compare_metric_records(a, b)['delta'], 0)

    def test_metric_definition_scope_and_zero_reference_block_bad_ratios(self):
        a = metric_record('time_mean', 0, 'W', role='power')
        b = metric_record('time_mean', 1, 'W', role='power')
        ratio = compare_metric_records(a, b)
        self.assertEqual(ratio['delta'], 1)
        self.assertIsNone(ratio['relative_percent'])
        self.assertIn('zero', ratio['relative_reason'])
        b['definition_version'] = '2'
        self.assertEqual(compare_metric_records(a, b)['status'], 'not_comparable')
        b['definition_version'] = '1'
        b['scope'] = {'kind': 'interval', 'start_s': 1, 'end_s': 2}
        self.assertEqual(compare_metric_records(a, b)['status'], 'not_comparable')

    def test_cancellation_retains_full_inventory_and_completed_evidence(self):
        store, _, _, mappings, pairings = self.fixture()
        cancel = threading.Event()
        def progress(event):
            if event['phase'] == 'analysis' and event['completed'] == 1:
                cancel.set()
        result = analyse_recordings(store, mappings=mappings, pairings=pairings,
            options={'cancelled': cancel, 'progress': progress})
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(len(result['inventory']), 4)
        self.assertLess(result['completed_field_count'], result['requested_field_count'])
        self.assertTrue(result['metrics'])
        self.assertTrue(any(row['status'] == 'cancelled' for row in result['readiness']))

    def test_selected_source_channels_create_only_the_explicit_pair(self):
        store, channels, fields, mappings, _ = self.fixture()
        result = compare_selected_fields(store, channels[0].id, channels[1].id, mappings=mappings)
        self.assertEqual(len(result['pairings']), 1)
        self.assertEqual(result['pairings'][0]['reference_field_id'], fields[0]['id'])
        self.assertEqual(result['pairings'][0]['candidate_field_id'], fields[1]['id'])

    def test_plot_budget_does_not_change_native_measurements(self):
        values = np.sin(np.arange(1000)/30)
        store, _, fields, mappings, pairings = self.fixture(x=np.arange(1000), y=values,
            bx=np.arange(1000)+2000, by=values+1)
        for mapping in mappings.values():
            mapping['acquisition_policy']['max_gap_seconds'] = 2
        small = analyse_recordings(store, mappings=mappings, pairings=pairings, options={'plot_budget': 12})
        large = analyse_recordings(store, mappings=mappings, pairings=pairings, options={'plot_budget': 2000})
        self.assertEqual(small['metrics'], large['metrics'])
        self.assertEqual(small['events'], large['events'])
        self.assertEqual(small['comparisons'], large['comparisons'])
        selected = next(row for row in small['plot_series'] if row['field_id'] == fields[0]['id'])
        self.assertLessEqual(len(selected['y']), 12)

    def test_late_channel_retains_the_recording_origin(self):
        store, channels, fields, mappings, pairings = self.fixture(x=(102., 104.), y=(2., 2.), bx=(200., 204.), by=(3., 3.))
        run = store.datasets[channels[0].dataset_id]
        run.frame['earlier_time'] = [100., 104.]
        run.frame['earlier_value'] = [0., 0.]
        for key in ('earlier_time', 'earlier_value'):
            run.frame.attrs['inventory_fields'][key] = {'column_position': list(run.frame.columns).index(key),
                'original_name': key, 'length': 2, 'clock': 'earlier_time', 'coordinate_unit': 's',
                'clock_description': {'kind': 'time', 'trust': 'declared', 'domain': 'relative', 'acquisition_policy': 'sampled'}}
        result = analyse_recordings(store, mappings=mappings, pairings=pairings)
        row = self.pointwise(result)
        self.assertAlmostEqual(row['supported_duration_s'], 2)
        self.assertAlmostEqual(row['coverage_fraction'], .5)
        picture = next(p for p in result['plot_series'] if p['field_id'] == fields[0]['id'])
        self.assertEqual(picture['aligned_x'], [2, 4])
        self.assertEqual(picture['original_x'], [102, 104])

    def test_native_calendar_origin_does_not_overlay_different_dates(self):
        store, _, fields, mappings, pairings = self.fixture(x=(0., 1., 2.), bx=(0., 1., 2.))
        for run, origin in zip(store.datasets.values(), ('2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00')):
            for spec in run.frame.attrs['inventory_fields'].values():
                spec['clock_description'].update(domain='absolute', origin=origin)
        result = analyse_recordings(store, mappings=mappings, pairings=pairings, options={'alignment': 'native'})
        self.assertEqual(self.pointwise(result)['status'], 'not_comparable')
        offsets = result['provenance']['native_calendar_offsets_s']
        self.assertEqual(offsets[fields[1]['run_id']]-offsets[fields[0]['run_id']], 86400)

    def test_event_matching_uses_elapsed_alignment_but_retains_native_evidence(self):
        result, *_ = self.result(x=(100., 101., 102., 103.), y=(0., 1., 1., 0.),
            bx=(200., 201., 202., 203.), by=(0., 1., 1., 0.), units=('state', 'state'), structure='binary')
        matching = next(row for row in result['comparisons'] if row['comparison_type'] == 'event_sequence')
        self.assertFalse(matching['missing'])
        self.assertFalse(matching['added'])
        self.assertTrue(matching['matches'])
        for match in matching['matches']:
            self.assertEqual(match['onset_delta_s'], 0)
            self.assertIn('native_onset_s', match['reference'])
        self.assertTrue(all(event['onset_s'] >= 100 for event in result['events']))

    def test_trusted_comparator_extension_and_failure_are_isolated(self):
        store, _, fields, mappings, pairings = self.fixture()
        comparators = comparator_registry().clone()
        comparators.register(CapabilityDefinition('example.checked', structures=('analog',), scopes=('pair',)),
            lambda a, b, c: {'comparison_type': 'example_custom', 'status': 'computed', 'value': 7}, trusted=True)
        def broken(a, b, c):
            raise ValueError('Example intentional failure')
        comparators.register(CapabilityDefinition('example.broken', structures=('analog',), scopes=('pair',)), broken, trusted=True)
        result = analyse_recordings(store, mappings=mappings, pairings=pairings, comparators=comparators)
        custom = next(row for row in result['comparisons'] if row.get('comparator_id') == 'example.checked')
        self.assertEqual(custom['value'], 7)
        self.assertEqual(custom['reference_field_id'], fields[0]['id'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(self.pointwise(result)['status'], 'computed')
        self.assertTrue(any('intentional failure' in ' '.join(row.get('reasons', [])) for row in result['comparisons']))

    def test_pre_cancelled_run_returns_inventory_without_fake_zero_metrics(self):
        store, _, _, mappings, pairings = self.fixture()
        cancel = threading.Event(); cancel.set()
        result = analyse_recordings(store, mappings=mappings, pairings=pairings, options={'cancelled': cancel})
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['completed_field_count'], 0)
        self.assertEqual(len(result['inventory']), 4)
        self.assertEqual(result['metrics'], [])

    def test_stage_relative_is_display_only_and_keeps_native_metrics(self):
        store, _, fields, mappings, pairings = self.fixture()
        a, b = fields[0]['run_id'], fields[1]['run_id']
        stages = [{'id': 'reviewed', 'kind': 'manual', 'confirmed': True, 'run_id': run_id,
                   'start_s': start, 'end_s': end, 'label': 'Reviewed interval', 'type': 'reviewed'}
                  for run_id, start, end in ((a, 100, 102), (b, 200, 202))]
        original = analyse_recordings(store, mappings=mappings, pairings=pairings, options={'stage_definitions': stages})
        view = analyse_recordings(store, mappings=mappings, pairings=pairings, options={
            'stage_definitions': stages, 'alignment': 'stage_relative',
            'stage_view': {a: a+':stage:reviewed:0:0', b: b+':stage:reviewed:0:0'}})
        self.assertEqual(original['metrics'], view['metrics'])
        self.assertEqual(self.pointwise(view)['status'], 'not_comparable')
        picture = next(p for p in view['plot_series'] if p['field_id'] == fields[0]['id'])
        self.assertEqual(picture['aligned_x'], [0, .5, 1])
        self.assertEqual(picture['aligned_coordinate_unit'], 'stage progress (0–1)')


if __name__ == '__main__':
    unittest.main()
