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
    def test_utf8_bom_before_datetime_heading_with_excel_timestamp_literals(self):
        text=['="2026-10-31 00:00:00.001"','="2026-10-31 00:00:00.099"','="2026-10-31 00:02:19.600"']
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'bom-clock.csv'
            pd.DataFrame({'datetime':text,'Speed [RPM]':[0,10,20]}).to_csv(path,index=False,encoding='utf-8-sig')
            original=path.read_bytes()
            store=ChannelStore();ids=ingest(store,path)
            self.assertEqual(len(ids),1)
            channel=store.channels[ids[0]]
            self.assertEqual(channel.coordinate_kind,'time')
            self.assertEqual(channel.attributes['time_origin'],'2026-10-31T00:00:00.001000')
            np.testing.assert_allclose(channel.x,[0,.098/60,139.599/60],atol=1e-12)
            self.assertEqual(next(iter(store.datasets.values())).frame.iloc[:,0].tolist(),text)
            self.assertEqual(path.read_bytes(),original)

    def test_timestamp_values_under_nonstandard_header_after_signal_columns(self):
        text=['="2026-10-30 13:00:37.349"', '="2026-10-30 13:00:37.351"', '="2026-10-30 13:09:28.4252"']
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'logger.csv'
            frame=pd.DataFrame({**{f'Signal {i}':[1,2,3] for i in range(5)},'Logger recorded at':text})
            frame.to_csv(path,index=False)
            parsed=extract_datetime_series(smart_read_file(path),fallback=False)
            self.assertTrue(parsed.notna().all())
            store=ChannelStore();ids=ingest(store,path)
            self.assertEqual(len(ids),5)
            for id in ids:
                channel=store.channels[id]
                self.assertEqual(channel.coordinate_kind,'time')
                np.testing.assert_allclose(channel.x,[0,.002/60,8.85127],atol=1e-10)
            pd.testing.assert_frame_equal(next(iter(store.datasets.values())).frame,frame)

    def test_whitespace_and_logger_clock_alias_preserve_millisecond_units(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'elapsed.csv'
            pd.DataFrame({' dTime [ms] ':[60000,60002,120000],'Signal':[1,2,3]}).to_csv(path,index=False)
            store=ChannelStore();ids=ingest(store,path)
            self.assertEqual(len(ids),1)
            channel=store.channels[ids[0]]
            self.assertEqual(channel.coordinate_kind,'time')
            np.testing.assert_allclose(channel.x,[1,60002/60000,2],atol=1e-12)

    def test_no_clock_keeps_samples_and_explicit_sample_import_overrides_timestamps(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'untimed.csv'
            pd.DataFrame({'Row ID':[100,200,300],'Remaining time [min]':[3,2,1],'Signal':[1,2,3]}).to_csv(path,index=False)
            store=ChannelStore();ingest(store,path)
            for channel in store.channels.values():
                self.assertEqual(channel.coordinate_kind,'sample')
                np.testing.assert_array_equal(channel.x,[0,1,2])
            pd.DataFrame({'Logger recorded at':['="2026-10-30 12:00:00.001"','="2026-10-30 12:00:01.002"'],'Signal':[1,2]}).to_csv(path,index=False)
            store=ChannelStore();ingest(store,path,force_sample=True)
            channel=next(c for c in store.channels.values() if c.name=='Signal')
            self.assertEqual(channel.coordinate_kind,'sample')
            np.testing.assert_array_equal(channel.x,[0,1])

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
