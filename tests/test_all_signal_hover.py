"""One hover time inspects every trace without hiding missing source support."""
from copy import deepcopy
import unittest

import numpy as np
from PySide6 import QtCore,QtTest,QtWidgets

from app_channel_store import Channel,ChannelStore
from app_hover_samples import hover_sample,compatible_hover_coordinate
from app_plot_workspace import PlotWorkspace


class NativeHoverSampleTests(unittest.TestCase):
    def test_native_indices_duplicate_policy_gaps_and_invalid_readings(self):
        channel=Channel('Sensor',[0,1,1,2,100,101],[2,3,4,np.nan,8,9],coordinate_unit='s')
        self.assertEqual(hover_sample(channel,1)['index'],2)
        self.assertEqual(hover_sample(channel,1)['y'],4)
        self.assertFalse(hover_sample(channel,2)['available'])
        self.assertIn('missing',hover_sample(channel,2)['reason'])
        self.assertFalse(hover_sample(channel,60)['available'])
        self.assertIn('gap',hover_sample(channel,60)['reason'])
        self.assertFalse(hover_sample(channel,-1)['available'])
        self.assertEqual(hover_sample(channel,100)['y'],8)

    def test_native_unit_conversion_does_not_rebase_recordings(self):
        self.assertEqual(compatible_hover_coordinate(('time','min'),('time','s'),2.5),150)
        self.assertEqual(compatible_hover_coordinate(('sample','sample'),('sample','sample'),30),30)
        self.assertIsNone(compatible_hover_coordinate(('time','min'),('frequency','Hz'),2))
        self.assertIsNone(compatible_hover_coordinate(('sample','sample'),('time','min'),2))

    def test_single_observation_is_inspectable_only_at_its_real_time(self):
        channel=Channel('One observation',[7],[42],coordinate_unit='s')
        self.assertEqual(hover_sample(channel,7)['y'],42)
        self.assertFalse(hover_sample(channel,7.01)['available'])

    def test_bad_user_gap_metadata_does_not_raise_a_mouse_callback_exception(self):
        for limit in ('not a duration',float('nan'),-1):
            channel=Channel('Sensor',[0,1,2],[3,4,5],coordinate_unit='s',attributes={'max_gap_seconds':limit})
            record=hover_sample(channel,.5)
            self.assertFalse(record['available'])
            self.assertIn('Invalid configured',record['reason'])


class AllSignalHoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.store=ChannelStore()
        self.temperature=self.store.add(Channel('Temperature',[0,1,2],[10,20,30],unit='°C',coordinate_unit='min'))
        self.pressure=self.store.add(Channel('Pressure',[0,.5,1,1.5,2],[100,150,200,250,300],unit='Pa',coordinate_unit='min'))
        self.valve=self.store.add(Channel('Valve',[0,1,2],[0,1,0],unit='state',kind='discrete',coordinate_unit='min',attributes={'actuator_binary':True}))
        self.workspace=PlotWorkspace(self.store)
        self.workspace.resize(1100,800);self.workspace.set_layout('Vertical split')
        self.top,self.bottom=self.workspace.visible_panes()
        self.top.bind([self.temperature.id,self.pressure.id]);self.bottom.bind([self.valve.id])
        self.workspace.show();self.app.processEvents()
        self.top.getViewBox().setRange(xRange=[0,2],yRange=[0,40],padding=0)
        self.top.axes['Pa'][1].setYRange(0,400,padding=0)
        self.bottom.getViewBox().setRange(xRange=[0,2],yRange=[-.2,1.2],padding=0)
        self.app.processEvents()

    def tearDown(self):
        self.workspace.close();self.app.processEvents()

    def hover(self,x,y=20):
        point=self.top.getViewBox().mapViewToScene(QtCore.QPointF(x,y))
        self.top._mouse_hover((point,))

    def test_one_time_emits_all_values_and_colored_markers_on_independent_axes(self):
        before=deepcopy(self.workspace.state())
        observed=[];self.workspace.hoverValuesChanged.connect(observed.append)
        self.hover(1)
        self.assertEqual(set(self.top.hover_markers),{self.temperature.id,self.pressure.id})
        self.assertEqual(set(self.bottom.hover_markers),{self.valve.id})
        payload=observed[-1]
        values={record['channel']:record for record in payload['values']}
        self.assertEqual(len(values),3)
        self.assertEqual(values[self.temperature.id]['y'],20)
        self.assertEqual(values[self.pressure.id]['y'],200)
        self.assertEqual(values[self.valve.id]['y'],1)
        self.assertEqual(values[self.valve.id]['index'],1)
        self.assertAlmostEqual(self.bottom.hover_lines[0].value(),1)
        self.assertFalse(self.bottom.hover_lines[1].isVisible())
        self.assertIn('Valve: ON',self.workspace.hover_readout.toolTip())
        self.assertIn('Valve: ON',self.top.hover_text, 'Fullscreen hosts use the same combined inspection text')
        self.assertEqual(self.workspace.state(),before)
        for id in (self.temperature.id,self.pressure.id):
            view,marker=self.top.hover_markers[id]
            self.assertIs(view,self.top.curves[id][0])
            self.assertEqual(marker.opts['brush'].color().name(),self.top.curves[id][1].pen.color().name())

    def test_missing_signal_stays_unknown_and_other_markers_remain_visible(self):
        self.store.update(self.pressure.id,y=np.full(5,np.nan));self.top.bind(self.top.ids)
        self.hover(1)
        values={record['channel']:record for record in self.workspace.hover_values['values']}
        self.assertFalse(values[self.pressure.id]['available'])
        self.assertIsNone(values[self.pressure.id]['y'])
        self.assertTrue(values[self.temperature.id]['available'])
        self.assertTrue(self.top.hover_markers[self.temperature.id][1].isVisible())
        self.assertNotIn(self.pressure.id,self.top.hover_markers)
        self.assertIn('Pressure: Unknown',self.workspace.hover_readout.toolTip())

    def test_normalized_markers_use_display_height_but_readouts_keep_original_units(self):
        self.top.normalized=True;self.top.bind([self.temperature.id,self.pressure.id])
        self.app.processEvents();self.hover(1,.5)
        values={record['channel']:record for record in self.workspace.hover_values['values']}
        self.assertEqual(values[self.pressure.id]['y'],200)
        self.assertEqual(values[self.pressure.id]['unit'],'Pa')
        marker=self.top.hover_markers[self.pressure.id][1]
        np.testing.assert_allclose(marker.getData()[1],[1.5])

    def test_clear_and_rebind_remove_every_stale_marker_without_canvas_resize(self):
        geometries=[pane.geometry() for pane in self.workspace.visible_panes()]
        self.hover(1)
        self.top.clear_hover()
        self.assertIsNone(self.workspace.hover_values)
        self.assertEqual(self.top.hover_markers,{})
        self.assertEqual(self.bottom.hover_markers,{})
        self.assertEqual([pane.geometry() for pane in self.workspace.visible_panes()],geometries)
        self.hover(1);self.top.bind([])
        self.assertIsNone(self.workspace.hover_values)
        self.assertFalse(self.bottom.hover_lines[0].isVisible())

    def test_sample_domain_graphs_do_not_receive_temporal_hover(self):
        sample=self.store.add(Channel('Sample only',[0,1,2],[4,5,6],coordinate_kind='sample',coordinate_unit='sample'))
        self.bottom.bind([sample.id]);self.app.processEvents()
        self.hover(1)
        self.assertNotIn(sample.id,{record['channel'] for record in self.workspace.hover_values['values']})
        self.assertFalse(self.bottom.hover_lines[0].isVisible())
