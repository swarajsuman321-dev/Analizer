"""Independent numerical examples for explicit, gap-aware two-signal reports."""
from copy import deepcopy
import json
import math
import threading
import unittest

import numpy as np
import pandas as pd

from app_channel_store import Channel, ChannelStore, Dataset
from app_operation_context import operation_context
from app_signal_comparison import compare_signals


class SignalComparisonTests(unittest.TestCase):
    def pair(self, x=(0, 1, 2), left=(0, 0, 0), right=(1, 1, 1), *,
             right_x=None, unit='W', right_unit=None, kind='analog', binary=False):
        store = ChannelStore()
        a, b = Dataset('Reference appliance', pd.DataFrame()), Dataset('Candidate appliance', pd.DataFrame())
        store.datasets.update({a.id: a, b.id: b})
        attrs = {'actuator_binary': True} if binary else {}
        reference = store.add(Channel('Parameter', x, left, unit=unit, kind=kind,
                                      coordinate_unit='min', dataset_id=a.id, attributes=dict(attrs)))
        candidate = store.add(Channel('Parameter', x if right_x is None else right_x, right,
                                      unit=unit if right_unit is None else right_unit, kind=kind,
                                      coordinate_unit='min', dataset_id=b.id, attributes=dict(attrs)))
        return store, reference, candidate

    def run_pair(self, *args, **kwargs):
        options = kwargs.pop('options', {})
        store, reference, candidate = self.pair(*args, **kwargs)
        result = compare_signals(store, reference.id, candidate.id, **options)
        self.assertEqual(result['status'], 'compared', result['reason'])
        return result

    def test_linear_crossing_uses_exact_absolute_and_square_integrals(self):
        result = self.run_pair(x=(0, 2), left=(0, 0), right=(-2, 2), options={'tolerance': 1})
        metrics = result['metrics']
        self.assertAlmostEqual(metrics['mean_bias'], 0)
        self.assertAlmostEqual(metrics['mean_absolute_difference'], 1)
        self.assertAlmostEqual(metrics['rmse'], 2/math.sqrt(3))
        self.assertAlmostEqual(metrics['different_duration_min'], 2)
        self.assertAlmostEqual(metrics['within_tolerance_duration_min'], 1)
        self.assertEqual(metrics['max_absolute_difference'], 2)
        self.assertEqual(metrics['max_difference_time_min'], 0)
        self.assertEqual(metrics['coverage_fraction'], 1)

    def test_unequal_sampling_density_does_not_weight_one_logger_more(self):
        sparse = self.run_pair(x=(0, 2), left=(0, 0), right=(-2, 2))
        times = np.r_[0., .01, .02, .03, .04, 1., 2.]
        dense = self.run_pair(x=(0, 2), left=(0, 0), right=times*2-2, right_x=times,
                              options={'max_gap_seconds': 180})
        for key in ('mean_bias', 'mean_absolute_difference', 'rmse',
                    'max_absolute_difference', 'compared_duration_min'):
            self.assertAlmostEqual(sparse['metrics'][key], dense['metrics'][key])

    def test_elapsed_alignment_uses_dataset_start_and_keeps_late_channel_offset(self):
        store, reference, candidate = self.pair(x=(102, 104), left=(2, 2),
                                               right_x=(200, 204), right=(3, 3))
        store.add(Channel('Earlier parameter', [100, 104], [0, 0], unit='W', coordinate_unit='min',
                          dataset_id=reference.dataset_id))
        result = compare_signals(store, reference.id, candidate.id)
        self.assertEqual(result['status'], 'compared')
        self.assertEqual(result['alignment']['reference_origin_min'], 100)
        self.assertEqual(result['alignment']['candidate_origin_min'], 200)
        self.assertEqual(result['reference']['plot']['time_min'], [2, 4])
        self.assertEqual(result['metrics']['compared_duration_min'], 2)
        self.assertEqual(result['metrics']['coverage_fraction'], .5)
        self.assertEqual(result['metrics']['mean_bias'], 1)
        np.testing.assert_array_equal(reference.x, [102, 104])

    def test_recorded_nonoverlap_is_blocked_without_extrapolation(self):
        store, reference, candidate = self.pair(x=(10, 12), left=(0, 0),
                                               right_x=(20, 22), right=(1, 1))
        result = compare_signals(store, reference.id, candidate.id, alignment='recorded')
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('No joint', result['reason'])
        self.assertEqual(result['metrics']['compared_duration_min'], 0)
        self.assertIsNone(result['metrics']['mean_bias'])
        self.assertTrue(all(not row['supported'] for row in result['differences']))

    def test_derived_clock_cannot_rebase_original_recording_start(self):
        store, reference, candidate = self.pair(x=(10, 11, 12), left=(0, 0, 0),
                                               right_x=(20, 21, 22), right=(1, 1, 1))
        store.add(Channel('Derived earlier clock', [0, 1, 2], [4, 5, 6], unit='W',
                          coordinate_unit='min', dataset_id=reference.dataset_id,
                          parents=[reference.id], recipe={'operation': 'manual derived clock'}))
        result = compare_signals(store, reference.id, candidate.id)
        self.assertEqual(result['status'], 'compared')
        self.assertEqual(result['alignment']['reference_origin_min'], 10)
        self.assertEqual(result['metrics']['compared_duration_min'], 2)
        self.assertEqual(result['metrics']['mean_bias'], 1)

    def test_elapsed_origin_preserves_deliberate_channel_time_shifts(self):
        store, reference, candidate = self.pair()
        reference.shift = .5
        result = compare_signals(store, reference.id, candidate.id)
        self.assertEqual(result['alignment']['reference_origin_min'], 0)
        self.assertEqual(result['reference']['plot']['time_min'], [.5, 1.5, 2.5])
        self.assertEqual(result['metrics']['compared_duration_min'], 1.5)
        self.assertEqual(reference.shift, .5)

    def test_manual_offset_is_projection_only_and_is_disclosed(self):
        store, reference, candidate = self.pair()
        result = compare_signals(store, reference.id, candidate.id, alignment='manual', offset_min=1)
        self.assertEqual(result['metrics']['compared_duration_min'], 1)
        self.assertEqual(result['metrics']['coverage_fraction'], 1/3)
        self.assertEqual(result['alignment']['candidate_offset_min'], 1)
        np.testing.assert_array_equal(candidate.values()[0], [0, 1, 2])

    def test_missing_values_and_long_gaps_do_not_contribute_difference_time(self):
        result = self.run_pair(x=(0, 1, 2, 10, 11), left=(0, np.nan, 2, 2, 2),
                              right_x=np.arange(12), right=np.full(12, 3.))
        self.assertEqual(result['metrics']['compared_duration_min'], 1)
        self.assertAlmostEqual(result['metrics']['coverage_fraction'], 1/11)
        self.assertEqual(result['metrics']['mean_bias'], 1)
        self.assertEqual(result['reference']['quality']['missing_readings'], 1)
        self.assertEqual(result['reference']['quality']['gap_count'], 1)
        self.assertTrue(any(not row['supported'] for row in result['differences']))

    def test_masks_are_respected_without_changing_original_arrays(self):
        store, reference, candidate = self.pair(x=(0, 1, 2, 3), left=(2, 2, 2, 2), right=(3, 3, 3, 3))
        reference.masks = [(1, 1)]
        result = compare_signals(store, reference.id, candidate.id)
        self.assertEqual(result['metrics']['compared_duration_min'], 1)
        self.assertEqual(result['metrics']['mean_bias'], 1)
        np.testing.assert_array_equal(reference.y, [2, 2, 2, 2])
        self.assertEqual(reference.masks, [(1, 1)])

    def test_last_duplicate_controls_timing_but_source_peak_is_retained(self):
        result = self.run_pair(x=(0, 1, 1, 2), left=(0, 100, 0, 0),
                              right_x=(0, 1, 2), right=(0, 0, 0))
        self.assertEqual(result['metrics']['max_absolute_difference'], 0)
        self.assertEqual(result['reference']['statistics']['max'], 100)
        self.assertEqual(result['reference']['statistics']['samples'], 4)
        self.assertEqual(result['reference']['quality']['duplicate_timestamps'], 1)
        self.assertEqual(len(result['differences']), 2)

    def test_confirmed_actuators_compare_held_on_off_durations(self):
        result = self.run_pair(left=(0, 128, 0), right=(-2, -2, -2), unit='raw',
                              kind='discrete', binary=True)
        self.assertEqual(result['metrics']['unit'], 'state')
        self.assertEqual(result['metrics']['mean_bias'], .5)
        self.assertEqual(result['metrics']['different_duration_min'], 1)
        self.assertEqual(result['reference']['activity']['active_duration_min'], 1)
        self.assertEqual(result['candidate']['activity']['active_duration_min'], 2)
        self.assertEqual(result['reference']['activity']['starts'], 1)
        self.assertEqual(result['reference']['activity']['stops'], 1)
        self.assertEqual(result['candidate']['activity']['starts'], 0)

    def test_numeric_state_or_code_is_not_automatically_binary(self):
        result = self.run_pair(left=(0, 128, 0), right=(0, 1, 0), unit='state', kind='discrete')
        self.assertEqual(result['metrics']['mean_bias'], -63.5)
        self.assertFalse(result['reference']['activity']['available'])

    def test_rotation_reversals_include_observed_zero_stop_but_not_gaps(self):
        result = self.run_pair(x=(0, 1, 2, 3, 4), left=(10, 0, 0, -10, 10),
                              right=(10, 0, 0, -10, 10), unit='RPM')
        activity = result['reference']['activity']
        self.assertEqual(activity['active_duration_min'], 3)
        self.assertEqual(activity['starts'], 1)
        self.assertEqual(activity['stops'], 1)
        self.assertEqual(activity['reversals'], 2)
        self.assertEqual(activity['positive_duration_min'], 1.5)
        self.assertEqual(activity['negative_duration_min'], 1.5)
        self.assertIn('protocol meaning may be unconfirmed', activity['interpretation'])
        gapped = self.run_pair(x=(0, 1, 10, 11), left=(10, 0, 0, -10), right=(10, 0, 0, -10), unit='RPM')
        self.assertEqual(gapped['reference']['activity']['reversals'], 0)

    def test_verified_affine_conversion_preserves_original_readings(self):
        store, reference, candidate = self.pair(left=(0, 50, 100), right=(32, 122, 212),
                                               unit='°C', right_unit='°F')
        result = compare_signals(store, reference.id, candidate.id)
        self.assertEqual(result['status'], 'compared')
        self.assertAlmostEqual(result['metrics']['max_absolute_difference'], 0)
        self.assertEqual(result['candidate']['original_unit'], '°F')
        self.assertEqual(result['candidate']['unit'], '°C')
        np.testing.assert_array_equal(candidate.y, [32, 122, 212])

    def test_affine_roundoff_does_not_fabricate_full_duration_differences(self):
        for reference_unit, candidate_unit, reference_y, candidate_y in (
                ('°C', '°F', (0, 50, 100), (32, 122, 212)),
                ('°F', '°C', (32, 122, 212), (0, 50, 100))):
            with self.subTest(reference_unit=reference_unit):
                store, reference, candidate = self.pair(
                    left=reference_y, right=candidate_y,
                    unit=reference_unit, right_unit=candidate_unit)
                result = compare_signals(store, reference.id, candidate.id, tolerance=0)
                metrics = result['metrics']
                self.assertEqual(metrics['different_duration_min'], 0)
                self.assertEqual(metrics['within_tolerance_duration_min'], 2)
                self.assertEqual(metrics['tolerance'], 0)
                self.assertLessEqual(metrics['max_absolute_difference'], metrics['numerical_resolution_max'])
                self.assertIn('not measurement accuracy', metrics['numerical_resolution_policy'])
                # Preserve the actual conversion residual in raw evidence and
                # error metrics; only numerical inequality duration is resolved.
                if reference_unit == '°F':
                    self.assertGreater(metrics['max_absolute_difference'], 0)
                    self.assertTrue(any(row['delta_start'] != 0 or row['delta_end'] != 0
                                        for row in result['differences']))
                np.testing.assert_array_equal(reference.y, reference_y)
                np.testing.assert_array_equal(candidate.y, candidate_y)

    def test_tiny_recorded_changes_above_operation_resolution_remain_differences(self):
        same_unit = self.run_pair(left=(0, 0, 0), right=(1e-16, 1e-16, 1e-16))
        self.assertEqual(same_unit['metrics']['different_duration_min'], 2)
        self.assertEqual(same_unit['metrics']['mean_bias'], 1e-16)
        store, reference, candidate = self.pair(
            left=(32+1e-8, 122+1e-8, 212+1e-8), right=(0, 50, 100),
            unit='°F', right_unit='°C')
        converted = compare_signals(store, reference.id, candidate.id, tolerance=0)
        self.assertEqual(converted['metrics']['different_duration_min'], 2)
        self.assertEqual(converted['metrics']['within_tolerance_duration_min'], 0)
        self.assertGreater(converted['metrics']['mean_absolute_difference'],
                           1000*converted['metrics']['numerical_resolution_max'])

    def test_custom_units_and_unitless_numbers_are_qualified_not_calibrated(self):
        result = self.run_pair(unit='logger counts')
        self.assertIn('custom unit', ' '.join(result['limitations']))
        self.assertEqual(result['metrics']['mean_bias'], 1)
        unitless = self.run_pair(unit='')
        self.assertIn('not declared', ' '.join(unitless['limitations']))
        self.assertFalse(unitless['reference']['activity']['available'])

    def test_incompatible_units_and_interpretations_have_clear_blockers(self):
        for left_unit, right_unit in [('Pa', 'RPM'), ('', 'Pa')]:
            store, reference, candidate = self.pair(unit=left_unit, right_unit=right_unit)
            result = compare_signals(store, reference.id, candidate.id)
            self.assertEqual(result['status'], 'blocked')
            self.assertTrue(result['reason'])
        store, reference, candidate = self.pair(binary=True)
        candidate.attributes = {}
        self.assertIn('interpretations', compare_signals(store, reference.id, candidate.id)['reason'])

    def test_interval_clipping_is_exact_and_plot_has_supported_boundaries(self):
        result = self.run_pair(x=(0, 10), left=(0, 0), right=(0, 10), options={'interval': [4, 5]})
        self.assertEqual(result['metrics']['compared_duration_min'], 1)
        self.assertEqual(result['metrics']['mean_bias'], 4.5)
        self.assertAlmostEqual(result['metrics']['rmse'], math.sqrt(61/3))
        self.assertEqual(result['candidate']['plot']['time_min'], [4, 5])
        self.assertEqual(result['candidate']['plot']['value'], [4, 5])

    def test_identity_and_invalid_inputs_are_blocked(self):
        store, reference, candidate = self.pair()
        for left, right, options in [(reference.id, reference.id, {}), ('absent', candidate.id, {}),
                                     (reference.id, candidate.id, {'tolerance': -1}),
                                     (reference.id, candidate.id, {'tolerance': np.nan}),
                                     (reference.id, candidate.id, {'interval': [0, np.inf]}),
                                     (reference.id, candidate.id, {'offset_min': np.nan})]:
            self.assertEqual(compare_signals(store, left, right, **options)['status'], 'blocked')
        candidate.coordinate_kind = 'frequency'
        self.assertIn('time-based', compare_signals(store, reference.id, candidate.id)['reason'])
        candidate.coordinate_kind = 'time'; candidate.dataset_id = reference.dataset_id
        self.assertIn('different recordings', compare_signals(store, reference.id, candidate.id)['reason'])

    def test_no_supported_duration_is_not_fabricated_from_point_samples(self):
        store, reference, candidate = self.pair(x=(0,), left=(2,), right=(4,))
        self.assertEqual(compare_signals(store, reference.id, candidate.id)['status'], 'blocked')
        missing = self.pair(left=(np.nan, np.nan, np.nan), right=(1, 1, 1))
        result = compare_signals(missing[0], missing[1].id, missing[2].id)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['metrics']['compared_duration_min'], 0)
        self.assertIsNone(result['metrics']['rmse'])

    def test_complete_evidence_bounded_plot_strict_json_and_no_domain_mutation(self):
        x = np.arange(10001)/60
        store, reference, candidate = self.pair(x=x, left=np.zeros(len(x)), right=np.ones(len(x)))
        original = [(channel.x.copy(), channel.y.copy(), deepcopy(channel.attributes), channel.revision)
                    for channel in (reference, candidate)]
        result = compare_signals(store, reference.id, candidate.id)
        self.assertEqual(len(result['differences']), 10000)
        self.assertLessEqual(len(result['reference']['plot']['time_min']), 6000)
        self.assertIs(result['differences'][0]['supported'], True)
        self.assertIs(result['reference']['activity']['available'], False)
        json.dumps(result, allow_nan=False)
        self.assertEqual(len(result['reference']['loaded_snapshot_sha256']), 64)
        for channel, before in zip((reference, candidate), original):
            np.testing.assert_array_equal(channel.x, before[0]); np.testing.assert_array_equal(channel.y, before[1])
            self.assertEqual(channel.attributes, before[2]); self.assertEqual(channel.revision, before[3])

    def test_worker_cancellation_propagates_before_any_result_is_published(self):
        store, reference, candidate = self.pair()
        cancel = threading.Event(); cancel.set()
        with operation_context(cancel, lambda *args: None):
            with self.assertRaises(InterruptedError):
                compare_signals(store, reference.id, candidate.id)


if __name__ == '__main__':
    unittest.main()
