"""Real instrument text wrappers must not turn timestamps into sample indexes."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app_channel_store import ChannelStore
from app_data import extract_datetime_series, smart_read_file, timestamp_text
from app_ingestion import ingest


class CsvTimeLiteralTests(unittest.TestCase):
    def test_wrapped_millisecond_timestamps_through_both_import_paths(self):
        text = ['="2026-10-30 13:00:37.349"',
                '="2026-10-30 13:00:37.351"',
                '="2026-10-30 13:09:28.4252"']
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'instrument.csv'
            pd.DataFrame({'timestamp': text, 'Power [W]': [1., 2., 3.]}).to_csv(path, index=False)
            frame = smart_read_file(path)
            before = frame.copy(deep=True)
            parsed = extract_datetime_series(frame, fallback=False)
            expected = pd.to_datetime([value[2:-1] for value in text])
            np.testing.assert_array_equal(parsed.to_numpy(), expected.to_numpy())
            pd.testing.assert_frame_equal(frame, before)
            store = ChannelStore()
            ids = ingest(store, path)
            self.assertEqual(len(ids), 1)
            channel = store.channels[ids[0]]
            self.assertEqual(channel.coordinate_kind, 'time')
            self.assertEqual(channel.coordinate_unit, 'min')
            self.assertEqual(channel.attributes['time_origin'], expected[0].isoformat())
            np.testing.assert_allclose(channel.x, [0, .002/60, 8.85127], atol=1e-10)
            self.assertEqual(next(iter(store.datasets.values())).frame['timestamp'].tolist(), text)

    def test_wrapped_separate_date_and_clock_with_invalid_row(self):
        frame = pd.DataFrame({'date': ['="2026-10-30"']*3,
                              'time': ['="23:59:59.999"', 'invalid', '="12:00:00.001"']})
        parsed = extract_datetime_series(frame, fallback=False)
        self.assertEqual(parsed.iloc[0], pd.Timestamp('2026-10-30 23:59:59.999'))
        self.assertTrue(pd.isna(parsed.iloc[1]))
        self.assertEqual(parsed.iloc[2], pd.Timestamp('2026-10-30 12:00:00.001'))

    def test_only_complete_text_literals_are_unwrapped(self):
        source = pd.Series([' ="text" ', '=1+1', '=HYPERLINK("example")', None,
                            '2026-10-30', '="broken', '="a"&"b"'])
        parsed = timestamp_text(source)
        self.assertEqual(parsed.iloc[0], 'text')
        for index in (1, 2, 4, 5, 6):
            self.assertEqual(parsed.iloc[index], source.iloc[index])
        self.assertTrue(pd.isna(parsed.iloc[3]))

    def test_direct_import_uses_clock_rollover_parser(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'clock.csv'
            pd.DataFrame({'time': ['="23:59:59.999"', '="00:00:00.001"'],
                          'voltage': [1, 2]}).to_csv(path,index=False)
            store = ChannelStore()
            channel = store.channels[ingest(store,path)[0]]
            np.testing.assert_allclose(channel.x,[0,.002/60],atol=1e-12)


if __name__ == '__main__':
    unittest.main()
