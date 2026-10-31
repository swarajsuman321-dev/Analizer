"""Unequal recordings must not pull the shared A/B pair onto shorter clocks."""
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6 import QtCore,QtWidgets
from app_channel_store import Channel, Dataset
from app_workbench import AdvancedStudioWindow


class SharedTimeCursorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.root=tempfile.TemporaryDirectory()
        self.settings=patch.dict('os.environ',{'ANALIZER_SETTINGS_DIR':self.root.name,'ANALIZER_OUTPUT_DIR':self.root.name})
        self.settings.start()
        self.window=AdvancedStudioWindow();self.window.show()
        self.workspace=self.window.dashboard
        self.dataset=Dataset('One run',pd.DataFrame());self.window.store.datasets[self.dataset.id]=self.dataset
        self.long=self.window.store.add(Channel('Long',np.arange(11.),np.arange(11.),unit='V',coordinate_unit='min',dataset_id=self.dataset.id))
        self.short=self.window.store.add(Channel('Short',np.arange(4.),np.arange(4.)+20,unit='V',coordinate_unit='min',dataset_id=self.dataset.id))
        self.workspace.set_layout('Vertical split')
        self.workspace.panes[0].bind([self.long.id]);self.workspace.panes[1].bind([self.short.id]);self.workspace.link()
        self.app.processEvents()

    def tearDown(self):
        self.window.close();self.app.processEvents();self.settings.stop();self.root.cleanup()

    def test_short_trace_cannot_clamp_shared_cursors_on_pan_or_refresh(self):
        p,q=self.workspace.visible_panes()
        p.cursor_lines[0].setValue(8);p.cursor_lines[1].setValue(9)
        self.app.processEvents()
        for pane in (p,q):self.assertEqual([line.value() for line in pane.cursor_lines],[8,9])
        self.assertTrue(np.isnan(q.measurements()[self.short.id]['A']))
        q._cursor_changed();q.setXRange(0,3,padding=0);self.app.processEvents()
        for pane in (p,q):self.assertEqual([line.value() for line in pane.cursor_lines],[8,9])
        self.workspace.refresh();self.app.processEvents()
        for pane in (p,q):self.assertEqual([line.value() for line in pane.cursor_lines],[8,9])

    def test_combined_readout_and_card_resolve_channels_from_every_split(self):
        p,q=self.workspace.visible_panes();p.cursor_lines[0].setValue(8);p.cursor_lines[1].setValue(9)
        self.window._readouts()
        self.assertEqual(self.window.readout.rowCount(),2)
        self.assertEqual(self.window.readout.item(1,2).text(),'Unknown')
        self.window.readout.selectRow(1);self.window.update_interval_card()
        self.assertIn('Short',self.window.interval_card.text())
        self.workspace.set_active(q);self.window._readouts()
        self.assertEqual(self.window.readout.rowCount(),2)
        self.assertEqual(self.window.readout.item(0,2).text(),'Unknown')

    def test_same_source_ranges_remain_linked_even_if_global_lock_is_off(self):
        p,q=self.workspace.visible_panes();self.workspace.set_time_lock(False)
        p.setXRange(2,7,padding=0);self.app.processEvents()
        np.testing.assert_allclose(q.getViewBox().viewRange()[0],[2,7])

    def test_frequency_graph_keeps_independent_cursors_and_readout(self):
        p,q=self.workspace.visible_panes()
        fft=self.window.store.add(Channel('Spectrum',np.arange(4.),np.arange(4.),unit='V',coordinate_unit='Hz',coordinate_kind='frequency'))
        q.bind([fft.id]);q.cursor_lines[0].setValue(1)
        p.cursor_lines[0].setValue(8);self.app.processEvents()
        self.assertEqual(q.cursor_lines[0].value(),1)
        self.workspace.set_active(q);self.window._readouts()
        self.assertEqual(self.window.readout.rowCount(),1)
        self.assertIn('Spectrum',self.window.readout.item(0,0).text())

    def test_hover_marks_each_trace_on_its_axis_without_moving_cursors(self):
        p,q=self.workspace.visible_panes()
        before=[[line.value() for line in pane.cursor_lines] for pane in (p,q)]
        point=p.getViewBox().mapViewToScene(QtCore.QPointF(2.,2.))
        p._mouse_hover((point,))
        self.assertIn('Long',self.workspace.hover_readout.toolTip())
        self.assertIn('Short',self.workspace.hover_readout.toolTip())
        for pane,id,value in ((p,self.long.id,2.),(q,self.short.id,22.)):
            marker=pane.inspection_markers[id][1]
            self.assertTrue(marker.isVisible())
            x,y=marker.getData();np.testing.assert_allclose(x,[2.]);np.testing.assert_allclose(y,[value])
        self.assertEqual([[line.value() for line in pane.cursor_lines] for pane in (p,q)],before)
        p.clear_hover()
        self.assertTrue(all(not marker.isVisible() for pane in (p,q) for _,marker in pane.inspection_markers.values()))

    def test_new_graph_inherits_legible_time_axis_in_light_and_dark_themes(self):
        for theme,color in (('Light','#182033'),('Dark','#e3eaf5')):
            self.window.theme.apply(theme)
            pane=self.workspace.add_graph()
            self.assertEqual(pane.getAxis('bottom').textPen().color().name(),color)


if __name__=='__main__':unittest.main()
