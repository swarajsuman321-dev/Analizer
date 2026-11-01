"""Hand-calculated, arbitrary-selection quick-analysis user workflows."""
from copy import deepcopy
import json
import threading
import unittest

import numpy as np
import pandas as pd

from app_channel_store import Channel, ChannelStore, Dataset
from app_quick_signal_analysis import analyse_selected_signals


class QuickSignalAnalysisTests(unittest.TestCase):
    def store(self):
        store = ChannelStore()
        dataset = Dataset('Synthetic appliance', pd.DataFrame({'raw': [1, 2, 3]}), 'synthetic://run')
        store.datasets[dataset.id] = dataset
        return store, dataset

    def channel(self, store, dataset, name, x, y, unit='W', actuator=False):
        return store.add(Channel(name, x, y, dataset_id=dataset.id, unit='state' if actuator else unit,
            kind='discrete' if actuator else 'analog', coordinate_unit='s',
            attributes={'actuator_binary': actuator}, source=dataset.source))

    @staticmethod
    def pointwise(result):
        return [row for row in result['comparisons'] if row['comparison_type'].startswith('common_window')]

    def test_three_same_file_signals_compare_without_a_two_signal_limit(self):
        store, ds = self.store()
        channels = [self.channel(store, ds, f'Unknown sensor {i}', [0, 1, 2], [i, i+1, i+2]) for i in range(3)]
        before = [(c.x.copy(), c.y.copy()) for c in channels]
        result = analyse_selected_signals(store, [c.id for c in channels])
        self.assertEqual(len(result['inventory']), 3)
        self.assertEqual(len(result['runs']), 1)
        self.assertEqual(len(result['pairings']), 2)
        errors = self.pointwise(result)
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(row['status'] == 'computed' for row in errors), errors)
        self.assertAlmostEqual(errors[0]['mean_bias'], 1)
        self.assertAlmostEqual(errors[1]['mean_bias'], 2)
        self.assertTrue(all(row['reference_run_id'] == ds.id for row in errors))
        for channel, (x, y) in zip(channels, before):
            np.testing.assert_array_equal(channel.x, x)
            np.testing.assert_array_equal(channel.y, y)
        json.dumps(result, allow_nan=False)

    def test_three_valves_exact_known_overlap_union_and_censoring(self):
        store, ds = self.store()
        times = np.arange(8.)
        channels = [self.channel(store, ds, f'Valve {index}', times,
                    np.where((times >= index) & (times < index+3), 128., 0.), actuator=True)
                    for index in (1, 2, 3)]
        result = analyse_selected_signals(store, [c.id for c in channels])
        metrics = result['metrics']
        for channel in channels:
            on = next(m for m in metrics if m['field_id'] == channel.id and m['metric_id'] == 'state.on_duration_s')
            rising = next(m for m in metrics if m['field_id'] == channel.id and m['metric_id'] == 'state.rising_count')
            self.assertEqual(on['value'], 3.)
            self.assertEqual(rising['value'], 1)
        overlap = result['actuator_overlaps'][0]
        self.assertEqual(overlap['all_on_duration_s'], 1.)
        self.assertEqual(overlap['union_duration_s'], 5.)
        pair = next(row for row in overlap['overlaps'] if row['field_ids'] == [channels[0].id, channels[1].id])
        self.assertEqual(pair['duration_s'], 2.)
        self.assertEqual(pair['supported_duration_s'], 7.)
        self.assertTrue(all('rmse' not in row for row in self.pointwise(result)))
        np.testing.assert_array_equal(channels[0].y, [0, 128, 128, 128, 0, 0, 0, 0])

    def test_sampled_gap_and_initial_on_do_not_invent_rising_edges_or_overlap(self):
        store, ds = self.store()
        a = self.channel(store, ds, 'Valve A', [0, 1, 10, 11], [1, 1, 1, 1], actuator=True)
        b = self.channel(store, ds, 'Valve B', [4, 5, 6], [0, 1, 0], actuator=True)
        result = analyse_selected_signals(store, [a.id, b.id], max_gap_seconds=2)
        rising = next(m for m in result['metrics'] if m.get('field_id') == a.id and m['metric_id'] == 'state.rising_count')
        self.assertEqual(rising['value'], 0)
        overlap = next(m for m in result['metrics'] if m['metric_id'] == 'actuator.pair_overlap')
        self.assertIsNone(overlap['value'], 'No common support is unknown, not zero overlap')
        episodes = [e for e in result['events'] if e.get('field_id') == a.id and e['type'] == 'active_episode']
        self.assertEqual(len(episodes), 2)
        self.assertTrue(all(e['left_censored'] and e['right_censored'] for e in episodes))

    def test_elapsed_uses_recording_origin_not_late_channel_origin(self):
        store, first = self.store()
        second = Dataset('Second', pd.DataFrame(), 'synthetic://second')
        store.datasets[second.id] = second
        self.channel(store, first, 'First clock witness', [100, 101], [0, 0])
        self.channel(store, second, 'Second clock witness', [200, 201], [0, 0])
        late_a = self.channel(store, first, 'Late A', [101, 102, 103], [1, 2, 3])
        late_b = self.channel(store, second, 'Late B', [202, 203, 204], [2, 3, 4])
        result = analyse_selected_signals(store, [late_a.id, late_b.id])
        plots = result['plot_series']
        self.assertEqual(plots[0]['aligned_x'][0], 1)
        self.assertEqual(plots[1]['aligned_x'][0], 2)
        error = self.pointwise(result)[0]
        self.assertAlmostEqual(error['supported_duration_s'], 1)
        self.assertAlmostEqual(error['mean_bias'], 0)

    def test_no_timebase_produces_samples_without_fake_seconds(self):
        store, ds = self.store()
        a = store.add(Channel('Unknown counter?', [0, 1, 2], [4, 5, 6], dataset_id=ds.id,
            coordinate_kind='sample', coordinate_unit='sample'))
        result = analyse_selected_signals(store, [a.id])
        minimum = next(m for m in result['metrics'] if m['metric_id'] == 'minimum')
        mean = next(m for m in result['metrics'] if m['metric_id'] == 'time_mean')
        self.assertEqual(minimum['value'], 4)
        self.assertIsNone(mean['value'])
        self.assertEqual(result['plot_series'][0]['coordinate_unit'], 'sample')

    def test_interval_clips_supported_overlap_without_changing_native_counts(self):
        store, ds = self.store()
        a = self.channel(store, ds, 'Valve A', [0, 1, 2, 3, 4, 5], [0, 1, 1, 1, 0, 0], actuator=True)
        b = self.channel(store, ds, 'Valve B', [0, 1, 2, 3, 4, 5], [0, 0, 1, 1, 1, 0], actuator=True)
        result = analyse_selected_signals(store, [a.id, b.id], interval_s=(2.5, 3.5))
        overlap = next(m for m in result['metrics'] if m['metric_id'] == 'actuator.pair_overlap')
        self.assertEqual(overlap['value'], 1)
        self.assertEqual(overlap['scope']['start_s'], 2.5)
        on = next(m for m in result['metrics'] if m.get('field_id') == a.id and m['metric_id'] == 'state.on_duration_s')
        self.assertEqual(on['value'], 1.)
        rising = next(m for m in result['metrics'] if m.get('field_id') == a.id and m['metric_id'] == 'state.rising_count')
        self.assertEqual(rising['value'], 0)

    def test_unit_conversion_and_zero_baseline_are_descriptive_not_acceptance(self):
        store, ds = self.store()
        a = self.channel(store, ds, 'A', [0, 1, 2], [0, 0, 0], unit='°C')
        b = self.channel(store, ds, 'B', [0, 1, 2], [32, 32, 32], unit='°F')
        result = analyse_selected_signals(store, [a.id, b.id])
        error = self.pointwise(result)[0]
        self.assertAlmostEqual(error['rmse'], 0, places=12)
        scalar = next(c for c in result['comparisons'] if c.get('metric_id') == 'maximum')
        self.assertIsNone(scalar['relative_percent'])
        self.assertEqual(scalar['acceptance']['status'], 'not_evaluated')

    def test_cancellation_and_invalid_selection_are_explicit(self):
        store, ds = self.store()
        a = self.channel(store, ds, 'A', [0, 1], [0, 1])
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(InterruptedError):
            analyse_selected_signals(store, [a.id], cancelled=cancel)
        with self.assertRaises(ValueError):
            analyse_selected_signals(store, [a.id, 'removed'])
        with self.assertRaises(ValueError):
            analyse_selected_signals(store, [a.id], gap_factor=float('nan'))

    def test_analysis_mode_keeps_independent_statistics_and_overlap_without_comparison(self):
        store, ds = self.store()
        a = self.channel(store, ds, 'Valve A', [0, 1, 2], [0, 1, 0], actuator=True)
        b = self.channel(store, ds, 'Valve B', [0, 1, 2], [0, 1, 0], actuator=True)
        result = analyse_selected_signals(store, [a.id, b.id], mode='analysis')
        self.assertEqual(result['kind'], 'analysis')
        self.assertEqual(result['comparisons'], [])
        self.assertEqual(result['pairings'], [])
        self.assertEqual(len(result['actuator_overlaps']), 1)
        self.assertTrue(any(m['metric_id'] == 'state.on_duration_s' for m in result['metrics']))
