import tempfile
import unittest
from pathlib import Path
import numpy as np
from nptdms import TdmsWriter,RootObject,GroupObject,ChannelObject
from app_channel_store import ChannelStore,Channel
from app_ingestion import ingest,read_tables
from app_workspace_io import save_workspace,load_workspace


def write(path,objects):
    with TdmsWriter(path) as writer:writer.write_segment(objects)


def labsys(group,times,values,unit='',status=None,properties=None):
    return [GroupObject(group,properties=properties or {'Unit':unit}),ChannelObject(group,group+'_dTime',np.array(times,float),properties={'unit_string':'sec'}),
            ChannelObject(group,group+'_Value',np.array(values,float),properties={'unit_string':unit}),
            ChannelObject(group,group+'_Status',status or ['OK']*len(values))]


class TdmsTests(unittest.TestCase):
    def test_labsys_independent_clocks_units_quality_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'example.tdms'
            objects=[RootObject(properties={'name':'Example','start':np.datetime64('2026-08-12T07:00:00')})]
            objects+=labsys('PDH_AAS_B_V1_0_R',[60,120,180],[0,128,-2],status=['OK','BAD','OK'])
            objects+=labsys('Pressure',[61,121],[8.5,16.5],'Pa',properties={'Unit':'Pa','LabSys_Scaling_Active':True,'Labsys_Scaling_Type':'Lookup Table'})
            objects+=labsys('PDH_RTH_D_UI_REMAIN_TIME_MINUTES_0_R',[62,122,182],[229,228,227],'Minutes')
            objects+=labsys('Motor_is_error',[60,120],[0,4])
            objects+=labsys('Progress_state',[60,120],[2,49])
            write(path,objects);store=ChannelStore();ids=ingest(store,path)
            self.assertEqual(len(ids),5);self.assertEqual(len(store.datasets),1)
            channels={c.name:c for c in store.channels.values()};valve=channels['PDH_AAS_B_V1_0_R']
            np.testing.assert_allclose(valve.x,[1,2,3]);np.testing.assert_allclose(valve.values()[1],[0,np.nan,1],equal_nan=True)
            self.assertEqual(valve.raw_y[1],128);self.assertTrue(valve.attributes['actuator_binary']);self.assertEqual(channels['Pressure'].unit,'Pa')
            np.testing.assert_allclose(channels['Pressure'].x,[61/60,121/60]);np.testing.assert_allclose(channels['Pressure'].y,[8.5,16.5])
            self.assertEqual(channels['PDH_RTH_D_UI_REMAIN_TIME_MINUTES_0_R'].unit,'min')
            self.assertFalse(channels['Motor_is_error'].attributes.get('actuator_binary'));self.assertEqual(channels['Motor_is_error'].y[1],4)
            self.assertEqual(channels['Progress_state'].y[1],49)
            frame=next(iter(store.datasets.values())).frame
            self.assertEqual(frame[valve.attributes['source_column']].iloc[1],128);self.assertEqual(frame.attrs['tdms_file_properties']['name'],'Example')
            from app_actuators import interpret_channel
            np.testing.assert_allclose(interpret_channel(valve).values()[1],[0,np.nan,1],equal_nan=True)
            saved=save_workspace(Path(directory)/'saved.json',store,[]);restored,_,_=load_workspace(saved)
            np.testing.assert_allclose(restored.channels[valve.id].values()[1],valve.values()[1],equal_nan=True)
            self.assertEqual(next(iter(restored.datasets.values())).frame.attrs,frame.attrs)

    def test_waveforms_keep_sampling_rates_offsets_and_common_absolute_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'waveform.tdms';start=np.datetime64('2026-01-01T12:00:00')
            write(path,[ChannelObject('Sensors','Time',np.array([0.,1.,2.]),properties={'unit_string':'s'}),ChannelObject('Sensors','A',np.array([10.,20.,30.]),properties={'wf_increment':2.,'wf_start_offset':5.,'wf_start_time':start,'unit_string':'degC'}),
                        ChannelObject('Sensors','B',np.array([1.,2.]),properties={'wf_increment':3.,'wf_start_time':start+np.timedelta64(30,'s'),'unit_string':'bar'})])
            store=ChannelStore();ingest(store,path);a,b=store.channels.values()
            np.testing.assert_allclose(a.x,np.array([5,7,9])/60);np.testing.assert_allclose(b.x,np.array([30,33])/60)
            self.assertEqual(a.unit,'°C');self.assertEqual(b.unit,'bar');self.assertEqual(len(a.y),3);self.assertEqual(len(b.y),2)
            sample=ChannelStore();ingest(sample,path,force_sample=True)
            self.assertTrue(all(c.coordinate_kind=='sample' for c in sample.channels.values()))

    def test_absolute_clock_sorting_and_remaining_time_is_a_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'absolute.tdms';start=np.datetime64('2026-01-01T12:00:00')
            write(path,[ChannelObject('First','Time',start+np.array([120,0,60],dtype='timedelta64[s]')),
                        ChannelObject('First','Temperature',np.array([3.,1.,2.]),properties={'unit_string':'°C'}),
                        ChannelObject('Second','Timestamp',start+np.array([30,90],dtype='timedelta64[s]')),
                        ChannelObject('Second','Remaining_time',np.array([10.,9.]),properties={'unit_string':'min'})])
            store=ChannelStore();ingest(store,path);a,b=store.channels.values()
            np.testing.assert_allclose(a.x,[0,1,2]);np.testing.assert_allclose(a.y,[1,2,3]);np.testing.assert_allclose(b.x,[.5,1.5])
            self.assertEqual(b.name,'Remaining_time');self.assertEqual(b.unit,'min')

    def test_engineering_adapter_is_causal_and_keeps_raw_actuator_codes(self):
        from app_data import smart_read_file
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'engineering.tdms'
            write(path,labsys('PDH_AAS_B_V1_0_R',[0,2,20],[0,128,0])+labsys('Pressure',[1,3,10],[10,20,30],'Pa'))
            frame=smart_read_file(path);self.assertEqual(frame.attrs['column_units']['PDH_AAS_B_V1_0_R'],'boolean')
            seconds=(frame.datetime-frame.datetime.iloc[0]).dt.total_seconds().to_numpy()
            at=lambda second:frame.loc[np.isclose(seconds,second)].iloc[0]
            self.assertEqual(at(1)['PDH_AAS_B_V1_0_R'],0);self.assertEqual(at(3)['PDH_AAS_B_V1_0_R'],128)
            self.assertTrue(np.isnan(at(10)['PDH_AAS_B_V1_0_R']));self.assertEqual(at(3)['Pressure'],20)
            self.assertIn('previous reading',frame.attrs['tdms_projection_policy'])

    def test_align_tdms_keeps_original_table_and_boolean_interpretation(self):
        from app_analysis_service import align_recordings
        from app_actuators import interpret_channel
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'machine.tdms'
            write(path,labsys('PDH_AAS_B_V1_0_R',[0,2,4],[0,128,0])+labsys('Pressure',[1,3],[10,20],'Pa'))
            store,frame=align_recordings('',str(path),'Raw Timestamps (No Shift)')
            valve=next(c for c in store.channels.values() if c.name=='PDH_AAS_B_V1_0_R')
            valve=interpret_channel(valve);self.assertTrue(valve.attributes['actuator_binary']);self.assertIn(128,valve.raw_y)
            original=next(d for d in store.datasets.values() if d.name=='Original machine')
            column=next(c for c in original.frame if c.endswith("_Value'"))
            self.assertEqual(original.frame[column].iloc[1],128)

    def test_no_clock_keeps_sample_indices_and_invalid_waveform_is_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'samples.tdms';write(path,[ChannelObject('Data','Reading',np.array([1.,np.nan,3.]))])
            store=ChannelStore();ingest(store,path);channel=next(iter(store.channels.values()))
            self.assertEqual(channel.coordinate_kind,'sample');np.testing.assert_array_equal(channel.x,[0,1,2]);self.assertTrue(np.isnan(channel.y[1]))
            path=Path(directory)/'bad.tdms';write(path,[ChannelObject('Data','Bad',np.array([1.]),properties={'wf_increment':-1.})])
            count=len(store.channels)
            with self.assertRaisesRegex(ValueError,'timing'):ingest(store,path)
            self.assertEqual(len(store.channels),count)
            path.write_bytes(b'TDSm invalid')
            with self.assertRaisesRegex(ValueError,'Cannot read TDMS'):read_tables(path)


class HoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        from app_plot_workspace import PlotPane
        self.store=ChannelStore();self.a=self.store.add(Channel('Temperature',[1,2,3],[10,20,30],unit='°C',coordinate_unit='min'))
        self.b=self.store.add(Channel('Pressure',[1.05,2.05,3.05],[100,200,300],unit='Pa',coordinate_unit='min'))
        self.pane=PlotPane(self.store);self.pane.resize(1000,600);self.pane.show();self.pane.bind([self.a.id,self.b.id]);self.app.processEvents()
        self.pane.getViewBox().setRange(xRange=[1,3.1],yRange=[0,40],padding=0);self.pane.axes['Pa'][1].setYRange(0,400,padding=0);self.app.processEvents()
    def tearDown(self):self.pane.close();self.app.processEvents()

    def test_real_mouse_hover_matches_each_axis_and_keeps_locked_cursors(self):
        from PySide6 import QtCore,QtTest
        p=self.pane;p.lock_cursor(0,self.a.id);cursors=[line.value() for line in p.cursor_lines]
        position=p.getViewBox().mapViewToScene(QtCore.QPointF(2.05,20));state=p.hover_values(position)
        self.assertAlmostEqual(state['x'],2.05);self.assertAlmostEqual(state['axes'][0]['y'],20);self.assertAlmostEqual(state['axes'][1]['y'],200,delta=1) # Independent view geometry can differ by a subpixel.
        self.assertEqual(state['nearest']['channel'],self.b.id);self.assertAlmostEqual(state['nearest']['x'],2.05);self.assertAlmostEqual(state['nearest']['y'],200)
        p.activateWindow();p.raise_();self.app.processEvents();QtTest.QTest.mouseMove(p.viewport(),QtCore.QPoint(0,0));QtTest.QTest.qWait(20)
        QtTest.QTest.mouseMove(p.viewport(),p.mapFromScene(position));QtTest.QTest.qWait(150);self.app.processEvents()
        self.assertIsNotNone(p.hover_state);self.assertFalse(hasattr(p,'hover_label'));self.assertIn('Pa',p.hover_text);self.assertIn('Mouse X',p.hover_text)
        self.assertEqual([line.value() for line in p.cursor_lines],cursors)
        self.assertTrue(p.hover_marker.isVisible())

    def test_missing_values_empty_selection_and_leaving_clear_hover(self):
        from PySide6 import QtCore
        p=self.pane
        self.store.update(self.a.id,y=np.array([np.nan]*3));self.store.update(self.b.id,y=np.array([np.nan]*3));p.bind([self.a.id,self.b.id])
        position=p.getViewBox().sceneBoundingRect().center();p._mouse_hover((position,))
        self.assertIsNone(p.hover_state['nearest']);self.assertIn('No sample',p.hover_text);self.assertFalse(p.hover_marker.isVisible())
        p._mouse_hover((QtCore.QPointF(-100,-100),));self.assertIsNone(p.hover_state);self.assertEqual(p.hover_text,'')
        p.bind([]);p._mouse_hover((position,));self.assertIsNone(p.hover_state);self.assertTrue(all(not line.isVisible() for line in p.hover_lines))

    def test_shifted_normalized_channels_show_original_sample_values(self):
        from PySide6 import QtCore
        p=self.pane;self.store.update(self.b.id,shift=10);p.bind([self.b.id]);p.normalized=True;p.bind([self.b.id]);self.app.processEvents()
        scene=p.getViewBox().mapViewToScene(QtCore.QPointF(12.05,.5));state=p.hover_values(scene)
        self.assertEqual(state['nearest']['y'],200);self.assertEqual(state['nearest']['unit'],'Pa');self.assertAlmostEqual(state['nearest']['x'],12.05)
