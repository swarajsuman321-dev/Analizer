"""Acquisition CSV timestamps retain spreadsheet text-literal precision.

All fixtures are synthetic. Normalisation is a parsing projection, not formula
execution or a rewrite of the original source table.
"""
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from app_channel_store import ChannelStore
from app_data import _parse_timestamp_column, extract_datetime_series, timestamp_text
from app_ingestion import ingest
from app_parameter_inventory import inventory_runs, source_field
from app_workspace_io import load_workspace, save_workspace


class SpreadsheetTimestampTests(unittest.TestCase):
    def test_literal_and_plain_timestamp_mixture_preserves_milliseconds(self):
        values = pd.Series(['="2026-01-02 10:20:30.123"',
                            '2026-01-02 10:20:30.221',
                            '  ="2026-01-02 10:20:30.324"  '])
        before = values.copy()
        parsed = _parse_timestamp_column(values, 'datetime')
        self.assertTrue(parsed.notna().all())
        np.testing.assert_allclose((parsed-parsed.iloc[0]).dt.total_seconds(), [0., .098, .201], atol=1e-12)
        pd.testing.assert_series_equal(values, before)
        self.assertEqual(parsed.iloc[0].microsecond, 123000)

    def test_unwrap_is_narrow_inert_and_never_accepts_formula_expressions(self):
        values = pd.Series(['=NOW()', '=1+1', '="2026-01-02"&" 10:20:30"',
                            '= "2026-01-02"', '="2026-01-02\n10:20:30"',
                            '="not a timestamp"', None, ''])
        unwrapped = timestamp_text(values)
        self.assertEqual(unwrapped.iloc[0], '=NOW()')
        self.assertEqual(unwrapped.iloc[2], values.iloc[2])
        self.assertEqual(unwrapped.iloc[3], values.iloc[3])
        self.assertEqual(unwrapped.iloc[4], values.iloc[4])
        self.assertTrue(_parse_timestamp_column(values, 'datetime').isna().all())

    def test_open_engineering_inventory_and_restore_use_the_same_clock(self):
        frame = pd.DataFrame({'datetime': ['="2026-01-02 10:20:30.123"',
            '="2026-01-02 10:20:30.221"', '="2026-01-02 10:20:30.324"'],
            'Pressure [Pa]': [10., 11., 12.]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'synthetic-export.csv'
            frame.to_csv(path, index=False, encoding='utf-8-sig')
            store = ChannelStore()
            ingest(store, path)
            self.assertEqual(len(store.datasets), 1)
            self.assertEqual(len(store.channels), 1)
            channel = next(iter(store.channels.values()))
            self.assertEqual(channel.coordinate_unit, 'min')
            self.assertEqual(channel.coordinate_kind, 'time')
            np.testing.assert_allclose(channel.x, np.array([0., .098, .201])/60, atol=1e-12)
            source = next(iter(store.datasets.values())).frame
            self.assertEqual(source['datetime'].tolist(), frame['datetime'].tolist())
            engineering = extract_datetime_series(source, fallback=False)
            np.testing.assert_allclose((engineering-engineering.iloc[0]).dt.total_seconds(), channel.x*60, atol=1e-12)
            fields = inventory_runs(store)[0]['fields']
            field = next(f for f in fields if f['original_name'] == 'Pressure [Pa]')
            native = source_field(store, field)
            np.testing.assert_allclose(native['coordinates'], channel.x*60, atol=1e-12)
            self.assertEqual(native['clock']['origin'], '2026-01-02T10:20:30.123000')
            self.assertEqual(native['clock']['quality']['invalid_timestamps'], 0)
            saved = Path(directory)/'workspace.json'
            save_workspace(saved, store, [], {})
            restored, _, _ = load_workspace(saved)
            restored_field = next(f for f in inventory_runs(restored)[0]['fields'] if f['id'] == field['id'])
            np.testing.assert_allclose(source_field(restored, restored_field)['coordinates'], native['coordinates'], atol=1e-12)
            self.assertEqual(next(iter(restored.datasets.values())).frame['datetime'].tolist(), frame['datetime'].tolist())

    def test_split_date_time_literals_agree_across_midnight(self):
        frame = pd.DataFrame({'Date': ['="2026-01-02"', '="2026-01-03"'],
                              'Time': ['="23:59:59.950"', '="00:00:00.050"'],
                              'Temperature': [20., 21.]})
        parsed = extract_datetime_series(frame, fallback=False)
        self.assertTrue(parsed.notna().all())
        self.assertAlmostEqual((parsed.iloc[1]-parsed.iloc[0]).total_seconds(), .1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'split-clock.csv'
            frame.to_csv(path, index=False)
            store = ChannelStore()
            ingest(store, path)
            self.assertEqual(len(store.channels), 1)
            channel = next(iter(store.channels.values()))
            np.testing.assert_allclose(channel.x, [0, .1/60], atol=1e-12)
            field = next(f for f in inventory_runs(store)[0]['fields'] if f['original_name'] == 'Temperature')
            np.testing.assert_allclose(source_field(store, field)['coordinates'], [0, .1], atol=1e-12)

    def test_invalid_and_backward_clock_rows_stay_in_original_evidence(self):
        frame = pd.DataFrame({'datetime': ['="2026-01-02 10:20:30.000"', None,
            '="2026-01-02 10:20:30.200"', '="2026-01-02 10:20:30.100"', '=NOW()'],
            'Value': [1, 2, 3, 4, 5]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'quality-clock.csv'
            frame.to_csv(path, index=False)
            store = ChannelStore()
            ingest(store, path)
            channel = next(iter(store.channels.values()))
            np.testing.assert_allclose(channel.x, np.array([0., .1, .2])/60, atol=1e-12)
            np.testing.assert_array_equal(channel.y, [1, 4, 3])
            field = next(f for f in inventory_runs(store)[0]['fields'] if f['original_name'] == 'Value')
            native = source_field(store, field)
            np.testing.assert_allclose(native['coordinates'], [0., np.nan, .2, .1, np.nan], equal_nan=True, atol=1e-12)
            np.testing.assert_array_equal(native['source_indices'], np.arange(5))
            self.assertEqual(native['clock']['quality']['invalid_timestamps'], 2)
            self.assertEqual(native['clock']['quality']['backwards'], 1)

    def test_unknown_or_formula_only_timestamps_do_not_become_assumed_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'invalid-clock.csv'
            pd.DataFrame({'datetime': ['=NOW()', '=1+1'], 'Value': [1, 2]}).to_csv(path, index=False)
            store = ChannelStore()
            with self.assertRaisesRegex(ValueError, 'Cannot interpret coordinate column'):
                ingest(store, path)
            self.assertEqual(store.datasets, {})
            self.assertEqual(store.channels, {})

    def test_numeric_elapsed_literal_keeps_declared_units_and_original_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'elapsed-clock.csv'
            pd.DataFrame({'Time [s]': ['="30.000"', '="30.125"', '30.250'],
                          'Value': [1, 2, 3]}).to_csv(path, index=False)
            store = ChannelStore()
            ingest(store, path)
            channel = next(iter(store.channels.values()))
            np.testing.assert_allclose(channel.x, np.array([30., 30.125, 30.25])/60, atol=1e-12)
            field = next(f for f in inventory_runs(store)[0]['fields'] if f['original_name'] == 'Value')
            np.testing.assert_allclose(source_field(store, field)['coordinates'], [30., 30.125, 30.25], atol=1e-12)
