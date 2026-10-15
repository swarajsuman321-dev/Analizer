"""Minute-based presentation must convert coordinates, not merely relabel axes."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from app_channel_store import Channel,ChannelStore
from app_ingestion import ingest
from app_time_units import normalize_minutes,presentation_statistics
from app_signal_processing import IntervalSummary,transform
from app_reporting import interval_tables


class MinutesTests(unittest.TestCase):
    def test_numeric_seconds_milliseconds_minutes_and_hours_convert(self):
        with tempfile.TemporaryDirectory() as root:
            for column,values in [('time [s]',[0,60,120]),('time [ms]',[0,60000,120000]),('time [min]',[0,1,2]),('time [h]',[0,1/60,2/60])]:
                frame=pd.DataFrame({column:values,'Signal':[1,2,3]});path=Path(root)/'data.csv';frame.to_csv(path,index=False)
                store=ChannelStore();ingest(store,path);c=next(iter(store.channels.values()))
                self.assertEqual(c.coordinate_unit,'min');np.testing.assert_allclose(c.x,[0,1,2])
                pd.testing.assert_frame_equal(next(iter(store.datasets.values())).frame,pd.read_csv(path))
    def test_simulation_time_already_in_minutes_is_not_divided_again(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'run_simulated_values.csv'
            pd.DataFrame({'time':[0,60,120],'water_temp':[20,30,40],'water_pressure':[0,100,200],'drum_speed':[0,40,0],'water_volume':[0,5,0],'process_state':[0,3,0],'heater_power':[0,2000,0]}).to_csv(path,index=False)
            store=ChannelStore();ingest(store,path)
            for c in store.channels.values():self.assertEqual(c.coordinate_unit,'min');np.testing.assert_allclose(c.x,[0,60,120])
    def test_datetimes_convert_elapsed_seconds_to_minutes(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'data.csv';pd.DataFrame({'timestamp':pd.date_range('2026-10-15',periods=3,freq='30s'),'Power':[0,2,4]}).to_csv(path,index=False)
            store=ChannelStore();ingest(store,path);c=next(iter(store.channels.values()))
            np.testing.assert_allclose(c.x,[0,.5,1]);self.assertEqual(c.coordinate_unit,'min')
    def test_sample_coordinates_are_not_divided(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'data.csv';pd.DataFrame({'Signal':[10,20,30]}).to_csv(path,index=False)
            store=ChannelStore();ingest(store,path);normalize_minutes(store)
            c=next(iter(store.channels.values()));np.testing.assert_equal(c.x,[0,1,2]);self.assertEqual(c.coordinate_unit,'sample')
    def test_old_workspace_cursors_annotations_masks_and_shift_convert(self):
        store=ChannelStore();c=store.add(Channel('Time left',np.array([0.,60,120]),np.array([120.,60,0]),unit='s',shift=60,masks=[(90,120)]))
        views=[{'panes':[{'ids':[c.id],'range':[[0,240],[0,120]],'cursors':[60,180],'bindings':{c.id:'s'},'axes':{},'annotations':[{'kind':'Marker','start':120,'end':120},{'kind':'Threshold','start':60,'end':60}]}]}]
        normalize_minutes(store,views);c=store.channels[c.id]
        np.testing.assert_equal(c.x,[0,1,2]);np.testing.assert_equal(c.y,[2,1,0]);self.assertEqual(c.shift,1);self.assertEqual(c.masks,[(1.5,2.)]);self.assertEqual(c.unit,'min')
        pane=views[0]['panes'][0];self.assertEqual(pane['cursors'],[1,3]);self.assertEqual(pane['range'],[[0,4],[0,2]])
        self.assertEqual(pane['annotations'][0]['start'],2);self.assertEqual(pane['annotations'][1]['start'],1)
        normalize_minutes(store);np.testing.assert_equal(store.channels[c.id].x,[0,1,2])
    def test_fft_retains_physical_hertz_after_time_conversion(self):
        x=np.arange(1000)/100;store=ChannelStore();c=store.add(Channel('Wave',x,np.sin(2*np.pi*5*x)))
        original=transform(c,'FFT');normalize_minutes(store);converted=transform(store.channels[c.id],'FFT')
        np.testing.assert_allclose(original.x,converted.x,atol=1e-12);np.testing.assert_allclose(original.y,converted.y,atol=1e-10)
        self.assertEqual(converted.coordinate_unit,'Hz')
    def test_interval_export_time_and_statistics_use_minutes(self):
        store=ChannelStore();c=store.add(Channel('Power',np.array([0.,60,120]),np.array([0.,60,120]),unit='W'));normalize_minutes(store);c=store.channels[c.id]
        stats=presentation_statistics(c,IntervalSummary(c).query(0,2))
        self.assertEqual(stats['ΔX'],2);self.assertEqual(stats['Slope'],60);self.assertEqual(stats['Integral'],120)
        data,summary=interval_tables(store,{'layout':'Single','panes':[{'ids':[c.id],'cursors':[0,2]}]})
        np.testing.assert_equal(data.coordinate.to_numpy(),[0,1,2]);self.assertEqual(summary.iloc[0]['coordinate_unit'],'min')
        self.assertEqual(summary.iloc[0]['cursor_B_X'],2)


if __name__=='__main__':unittest.main()
