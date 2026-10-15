import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from PySide6 import QtWidgets,QtCore,QtTest
from app_channel_store import Channel,ChannelStore
from app_ingestion import ingest
from app_plot_workspace import PlotWorkspace

class UnitDetectionTests(unittest.TestCase):
    def test_unit_row_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'row.csv';path.write_text('time,Temperature,Power\n[s],[degC],[kW]\n0,20,1\n60,22,2\n')
            store=ChannelStore();ingest(store,path);channels=list(store.channels.values())
            self.assertEqual([c.unit for c in channels],['°C','kW']);np.testing.assert_equal(channels[0].x,[0,1])
            self.assertEqual(next(iter(store.datasets.values())).frame.iloc[0,0],'[s]')
            path.write_text('time,Temperature,Power\ns,degC,kW\n0,20,1\n60,22,2\n');store=ChannelStore();ingest(store,path)
            self.assertEqual([c.unit for c in store.channels.values()],['°C','kW'])
    def test_declared_suffix_and_known_names(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'units.csv';pd.DataFrame({'time':[0,60,120],'Probe (degC)':[1,2,3],'Pressure_kPa':[1,2,3],'heater_power':[2,3,4],'water_temp_ops':[20,21,22],'unknown':[1,2,3]}).to_csv(path,index=False)
            store=ChannelStore();ingest(store,path)
            self.assertEqual([c.unit for c in store.channels.values()],['°C','kPa','W','°C',''])

class NavigationLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        self.store=ChannelStore();self.a=self.store.add(Channel('Slow {sensor}',np.array([0.,2,4,6,8,10]),np.arange(6.),unit='V',coordinate_unit='min'))
        self.b=self.store.add(Channel('Fast',np.arange(11.),np.arange(11.)*3,unit='W',coordinate_unit='min'))
        self.workspace=PlotWorkspace(self.store);self.workspace.resize(1200,800);self.workspace.show();self.workspace.assign([self.b.id,self.a.id]);self.app.processEvents();self.pane=self.workspace.active
    def tearDown(self):self.workspace.close();self.workspace.deleteLater();self.app.processEvents()
    def test_lock_uses_chosen_clock_pan_shift_and_other_readouts(self):
        p=self.pane;p.lock_cursor(0,self.a.id);p.cursor_lines[0].setValue(3.1)
        self.assertEqual(p.cursor_lines[0].value(),4)
        p.setXRange(6,10,padding=0);self.app.processEvents();self.assertEqual(p.cursor_lines[0].value(),4)
        p.step_cursor(0,1);self.assertEqual(p.cursor_lines[0].value(),6);self.assertEqual(p.measurements()[self.b.id]['A'],18)
        p.cursor_lines[0].setValue(8.8);self.assertEqual(p.cursor_lines[0].value(),8)
        self.store.update(self.a.id,shift=1);p.bind(p.ids,fit=False);p._cursor_changed();self.assertEqual(p.cursor_lines[0].value(),9)
    def test_linked_lock_survives_pan_and_releases_when_hidden(self):
        w=self.workspace;w.set_layout('Vertical split');w.panes[1].bind([self.b.id]);w.link();p=w.panes[0];p.lock_cursor(0,self.a.id);point=p.cursor_lines[0].value()
        w.panes[1].setXRange(8,10,padding=0);self.app.processEvents()
        self.assertEqual(p.cursor_lines[0].value(),point);self.assertEqual(w.panes[1].cursor_lines[0].value(),point)
        w.set_visible([self.a.id],False);self.assertTrue(all(not p.cursor_locks[0] for p in w.panes))
    def test_locks_persist_and_arrow_keys_step(self):
        p=self.pane;p.lock_cursor(0,self.a.id);state=p.state();before=p.cursor_lines[0].value();QtTest.QTest.keyClick(p,QtCore.Qt.Key.Key_Right)
        self.assertGreater(p.cursor_lines[0].value(),before);p.restore(state);self.assertEqual(p.cursor_locks[0],state['cursor_locks'][0]);self.assertEqual(p.cursor_lines[0].value(),state['cursors'][0])
    def test_deleting_both_cursor_anchors_is_safe(self):
        p=self.pane;p.lock_cursor(0,self.a.id);p.lock_cursor(1,self.a.id)
        self.store.delete([self.a.id]);p.bind([self.b.id],fit=False)
        self.assertEqual(p.cursor_locks,[None,None])

    def test_alignment_refresh_preserves_hidden_channels_and_locks(self):
        from app_workbench import AdvancedStudioWindow
        from app_analysis_service import align_recordings
        w=AdvancedStudioWindow();w.show();self.app.processEvents()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'data.csv';pd.DataFrame({'timestamp':pd.date_range('2026-10-15',periods=4,freq='min'),'water_temp':[20,21,22,23],'water_pressure':[0,10,20,30]}).to_csv(path,index=False)
            result=lambda:align_recordings('',str(path),'Raw Timestamps (No Shift)')[0]
            w.merge_store(result(),w.dashboard,deduplicate_alignment=True);ids=list(w.store.channels);p=w.dashboard.active;p.lock_cursor(0,ids[0]);w.dashboard.set_visible([ids[-1]],False)
            w.merge_store(result(),w.dashboard,deduplicate_alignment=True)
            self.assertEqual(list(w.store.channels),ids);self.assertFalse(any(ids[-1] in p.ids for p in w.dashboard.visible_panes()));self.assertEqual(w.dashboard.active.cursor_locks[0]['channel'],ids[0])
            from dataclasses import replace
            from app_channel_store import identity
            duplicate=w.store.add(replace(w.store.channels[ids[0]],id=identity()));w.dashboard.active.bind([duplicate.id]);w.dashboard.active.lock_cursor(0,duplicate.id)
            w.merge_store(result(),w.dashboard,deduplicate_alignment=True)
            self.assertEqual(list(w.store.channels),ids);self.assertIn(ids[0],w.dashboard.active.ids);self.assertEqual(w.dashboard.active.cursor_locks[0]['channel'],ids[0])
        w.close();self.app.processEvents()

    def test_visible_shortcuts_and_reset(self):
        from app_workbench import AdvancedStudioWindow
        w=AdvancedStudioWindow();w.show();self.app.processEvents()
        actions=[a for submenu in w.studio.submenus.values() for a in submenu.actions()]
        shortcuts={a.text():a.shortcut().toString() for a in actions}
        self.assertEqual(shortcuts['Fit'],'Ctrl+0');self.assertEqual(shortcuts['Zoom X'],'Ctrl+1');self.assertEqual(shortcuts['Lock cursors to channel…'],'Ctrl+L')
        w.close();self.app.processEvents()
