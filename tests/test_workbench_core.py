import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from app_channel_store import Channel,ChannelStore,Dataset
from app_ingestion import ingest
from app_signal_processing import IntervalSummary,formula,transform,conversion
from app_workspace_io import save_workspace,load_workspace,export_processed
from app_fast_plot import EnvelopeCache


class ChannelTests(unittest.TestCase):
    def test_immutable_identity_and_batched_events(self):
        store=ChannelStore();events=[];store.observe(events.append)
        with store.batch():
            a=store.add(Channel('A',[0,1],[1,2]));store.add(Channel('B',[0,1],[3,4]))
        self.assertEqual(len(events),1)
        with self.assertRaises(ValueError):a.y[0]=5
        changed=store.update(a.id,name='Renamed')
        self.assertEqual(changed.id,a.id);self.assertEqual(changed.revision,1)
        self.assertEqual(store.duplicate(a.id).parents,[a.id])

    def test_duplicate_sampling_last_and_unknown(self):
        c=Channel('A',[0,1,1,2,3],[0,1,9,np.nan,4])
        self.assertEqual(c.sample(1),9)
        self.assertTrue(np.isnan(c.sample(1.5)));self.assertTrue(np.isnan(c.sample(-1)));self.assertTrue(np.isnan(c.sample(4)))
        state=Channel('B',[0,1,2],[0,10,0],kind='discrete')
        self.assertEqual(state.sample(.5),0)
        self.assertEqual(Channel('C',[0,1],[0,10]).sample(.5),5)

    def test_masks_and_revision_invalidate_arrays(self):
        store=ChannelStore();c=store.add(Channel('A',[0,1,2],[1,2,3]))
        x,y=c.values();changed=store.update(c.id,masks=[(.5,1.5)])
        self.assertTrue(np.isnan(changed.sample(.7)));self.assertTrue(np.isnan(changed.values()[1][1]));self.assertEqual(c.y[1],2)

    def test_source_rows_duplicates_precision_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'input.csv';path.write_text('timestamp,value [W],state\n2026-10-01 01:02:03.000001,1,0\n2026-10-01 01:02:03.000001,2,1\n2026-10-01 01:02:03.000004,,0\n')
            store=ChannelStore();ids=ingest(store,path)
            c=store.channels[ids[0]]
            self.assertEqual(len(c.x),3);self.assertAlmostEqual(c.x[-1],.000003);self.assertEqual(c.sample(0),2)
            self.assertEqual(c.unit,'W');self.assertEqual(len(next(iter(store.datasets.values())).frame),3)


class NumericalTests(unittest.TestCase):
    def setUp(self):
        self.store=ChannelStore();self.c=self.store.add(Channel('Power',[0,1,2],[0,2,4],unit='W'))

    def test_span_weighted_statistics(self):
        stats=IntervalSummary(self.c).query(.5,1.5)
        self.assertAlmostEqual(stats['Mean'],2)
        self.assertAlmostEqual(stats['RMS'],np.sqrt(13/3))
        self.assertAlmostEqual(stats['Integral'],2);self.assertEqual(stats['Coverage'],1)
        self.assertEqual(stats['Min'],1);self.assertEqual(stats['Max'],3)

    def test_duplicate_area_and_missing_coverage(self):
        c=Channel('A',[0,1,1,2],[0,2,8,10])
        self.assertEqual(IntervalSummary(c).query(0,2)['Integral'],10)
        c=Channel('B',[0,1,2,3],[1,1,np.nan,1])
        self.assertAlmostEqual(IntervalSummary(c).query(0,3)['Coverage'],1/3)

    def test_calculus_seconds_and_reset(self):
        c=Channel('A',[0,1,2],[0,60,120],coordinate_unit='min',unit='W')
        np.testing.assert_allclose(transform(c,'Differentiation').y,1)
        np.testing.assert_allclose(transform(c,'Cumulative integration').y,[0,1800,7200])
        gap=Channel('Gap',[0,1,2,3,4],[1,1,np.nan,2,2])
        np.testing.assert_allclose(transform(gap,'Cumulative integration').y,[0,1,np.nan,0,2],equal_nan=True)

    def test_zero_duration_unknown_does_not_reset_integral(self):
        c=Channel('Jump',[0,1,1,1,2],[1,1,np.nan,2,2])
        np.testing.assert_allclose(transform(c,'Cumulative integration').y,[0,1,np.nan,1,3],equal_nan=True)

    def test_formula_units_alignment_and_security(self):
        self.store.add(Channel('kPower',[0,1,2],[0,.002,.004],unit='kW'))
        result=formula(self.store,'Ch("Power") - Ch("kPower")')
        np.testing.assert_allclose(result.y,0)
        self.assertEqual(formula(self.store,'convert(Ch("Power"), "kW")').unit,'kW')
        self.assertEqual(formula(self.store,'Ch("Power") / Ch("Power")').unit,'')
        for expression in ('__import__("os")','Ch("Power").y','Ch("Power")[0]','[1,2]'):
            with self.assertRaises(ValueError):formula(self.store,expression)
        self.store.add(Channel('Other',[0,2,4],[0,1,2],unit='W'))
        with self.assertRaises(ValueError):formula(self.store,'Ch("Power") + Ch("Other")')
        with self.assertRaises(ValueError):conversion('W','Pa')

    def test_explicit_resampling_and_missing_support(self):
        c=Channel('A',[0,1,1,2,3,4],[0,1,2,np.nan,3,4])
        res=transform(c,'Resampling',step=.5)
        self.assertEqual(res.sample(1),2);self.assertTrue(np.isnan(res.sample(1.5)))
        with self.assertRaises(ValueError):transform(c,'FFT')
        with self.assertRaises(ValueError):transform(res,'FFT')

    def test_frequency_coordinates_and_psd(self):
        x=np.arange(1024)/128;c=Channel('Sine',x,np.sin(2*np.pi*8*x),unit='V')
        fft=transform(c,'FFT');psd=transform(c,'Welch PSD')
        self.assertEqual(fft.coordinate_kind,'frequency');self.assertEqual(fft.coordinate_unit,'Hz')
        self.assertAlmostEqual(fft.x[np.argmax(fft.y)],8)
        self.assertAlmostEqual(psd.x[np.argmax(psd.y)],8)

    def test_processing_operations(self):
        x=np.arange(1000)/100;c=Channel('Sine',x,np.sin(x*3),unit='V')
        for operation,params in [('Moving average',{'window':11}),('Savitzky–Golay',{'window':11,'order':2}),('Butterworth low-pass',{'cutoff':5}),('Offset and scale',{'offset':1,'scale':2}),('Time shift',{'shift':3}),('Histogram',{'bins':10}),('Peak and valley detection',{}),('Descriptive statistics',{})]:
            with self.subTest(operation=operation):
                result=transform(c,operation,**params);self.assertEqual(result.parents,[c.id]);self.assertTrue(len(result.y))
        stats=transform(c,'Descriptive statistics');self.assertEqual(stats.attributes['metric_labels'][-1],'Count');self.assertEqual(stats.attributes['metric_units'][-1],'count')

    def test_envelope_peak_budget_and_missing(self):
        x=np.arange(100001);y=np.zeros(len(x));y[50000]=100;y[70000]=np.nan
        cache=EnvelopeCache(x,y);dx,dy=cache.visible(0,100000,2000)
        self.assertLess(len(dx),2500);self.assertEqual(np.nanmax(dy),100);self.assertTrue(np.isnan(dy).any())
        self.assertLess(len(cache.visible(49900,50100,2000)[0]),250)


class PersistenceTests(unittest.TestCase):
    def test_exact_source_channel_and_view_roundtrip(self):
        store=ChannelStore();frame=pd.DataFrame({'float':[np.pi,np.nan],'string':['x','y'],'bool':[True,False]})
        ds=Dataset('Source',frame);store.datasets[ds.id]=ds
        c=store.add(Channel('A',[0,1,1],[np.pi,np.nan,2],dataset_id=ds.id,masks=[(.2,.4)]))
        views=[{'layout':'Single','panes':[{'ids':[c.id],'cursors':[.1,.9]}]}]
        with tempfile.TemporaryDirectory() as root:
            path=save_workspace(Path(root)/'work.json',store,views)
            restored,saved,ui=load_workspace(path)
            np.testing.assert_array_equal(restored.channels[c.id].y,c.y)
            pd.testing.assert_frame_equal(restored.datasets[ds.id].frame,frame)
            self.assertEqual(saved,views)
            stats=transform(c,'Descriptive statistics');data=export_processed(Path(root)/'result.csv',[stats])
            read=pd.read_csv(Path(root)/'result.csv');self.assertEqual(read.iloc[-1]['unit'],'count');self.assertEqual(len(data),7)
            export_processed(Path(root)/'result.xlsx',[c]);self.assertEqual(len(pd.read_excel(Path(root)/'result.xlsx')),3)
