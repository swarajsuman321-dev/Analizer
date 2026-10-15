import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from PySide6 import QtWidgets,QtCore,QtTest,QtGui
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
        self.assertTrue(p.cursor_markers[0].isVisible());mx,my=p.cursor_markers[0].getData();np.testing.assert_equal(mx,[4]);np.testing.assert_equal(my,[2])
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

    def test_y_pan_moves_every_unit_axis(self):
        p=self.pane;view=p.getViewBox();view.setMouseMode(view.PanMode);view.setMouseEnabled(x=False,y=True)
        views=p.y_views();before=[list(v.viewRange()[1]) for v in views]
        start=p.mapFromScene(view.sceneBoundingRect().center());end=start+QtCore.QPoint(0,60)
        QtTest.QTest.mouseMove(p.viewport(),start);QtTest.QTest.qWait(40)
        QtTest.QTest.mousePress(p.viewport(),QtCore.Qt.MouseButton.MiddleButton,pos=start)
        QtTest.QTest.mouseMove(p.viewport(),start+QtCore.QPoint(0,30),delay=40);QtTest.QTest.mouseMove(p.viewport(),end,delay=40)
        QtTest.QTest.mouseRelease(p.viewport(),QtCore.Qt.MouseButton.MiddleButton,pos=end);self.app.processEvents()
        shifts=[(v.viewRange()[1][0]-a[0])/(a[1]-a[0]) for v,a in zip(views,before)]
        self.assertGreater(abs(shifts[0]),.01);np.testing.assert_allclose(shifts,shifts[0],rtol=1e-5,atol=1e-8)

    def test_wheel_zoom_moves_every_unit_axis_and_history_restores(self):
        p=self.pane;views=p.y_views();before=[list(v.viewRange()[1]) for v in views]
        pos=p.mapFromScene(p.getViewBox().sceneBoundingRect().center());global_pos=p.viewport().mapToGlobal(pos)
        event=QtGui.QWheelEvent(QtCore.QPointF(pos),QtCore.QPointF(global_pos),QtCore.QPoint(),QtCore.QPoint(0,120),QtCore.Qt.MouseButton.NoButton,QtCore.Qt.KeyboardModifier.NoModifier,QtCore.Qt.ScrollPhase.NoScrollPhase,False)
        QtWidgets.QApplication.sendEvent(p.viewport(),event);self.app.processEvents()
        after=[v.viewRange()[1] for v in views]
        self.assertGreater(len(views),1)
        factors=[(b[1]-b[0])/(a[1]-a[0]) for a,b in zip(before,after)]
        self.assertLess(factors[0],1);np.testing.assert_allclose(factors,factors[0],rtol=1e-6)
        p.navigate_history(-1)
        for view,bounds in zip(views,before):np.testing.assert_allclose(view.viewRange()[1],bounds,rtol=1e-6)

    def test_zoom_buttons_change_all_axes_and_locked_readout_is_explicit(self):
        from app_workbench import AdvancedStudioWindow
        w=AdvancedStudioWindow();w.show();a=w.store.add(Channel('Pressure',np.arange(11.),np.arange(11.)*100,unit='Pa',coordinate_unit='min'));b=w.store.add(Channel('Temperature',np.arange(11.),np.arange(11.)+20,unit='°C',coordinate_unit='min'))
        w.dashboard.assign([a.id,b.id]);p=w.dashboard.active;p.lock_cursor(0,b.id);point=p.cursor_lines[0].value();p.cursor_lines[1].setValue(8);w._readouts()
        self.assertIn(f'{point+20:.6g} °C',w.interval_card.text())
        self.assertIn('A locked · Temperature',w.interval_card.text());self.assertEqual(w.readout.columnCount(),9)
        self.assertEqual(w.readout.horizontalHeaderItem(5).text(),'Δ value');self.assertEqual(w.readout.item(1,6).text(),'22');self.assertEqual(w.readout.item(1,7).text(),'28');self.assertEqual(w.readout.item(1,8).text(),'25')
        before=[v.viewRange()[1] for v in p.y_views()];w.studio.zoom(.5)
        for v,bounds in zip(p.y_views(),before):self.assertAlmostEqual(v.viewRange()[1][1]-v.viewRange()[1][0],(bounds[1]-bounds[0])*.5)
        p.fit();self.assertEqual(p.cursor_lines[0].value(),point)
        w.close();self.app.processEvents()

    def test_summary_scope_and_quick_notes_persist_and_export(self):
        from unittest.mock import patch
        from app_workbench import AdvancedStudioWindow
        from app_workspace_io import save_workspace,render_report
        w=AdvancedStudioWindow();w.show();c=w.store.add(Channel('Probe',np.arange(11.),np.arange(11.),unit='°C',coordinate_unit='min'));w.dashboard.assign([c.id]);p=w.dashboard.active
        p.cursor_lines[0].setValue(2);p.cursor_lines[1].setValue(4);w._readouts();self.assertEqual(w.readout.item(0,8).text(),'3')
        w.stats_scope.setCurrentIndex(1);w._readouts();self.assertEqual(w.readout.item(0,6).text(),'0');self.assertEqual(w.readout.item(0,7).text(),'10');self.assertEqual(w.readout.item(0,8).text(),'5');self.assertEqual(w.readout.item(0,5).text(),'2')
        from app_reporting import interval_tables
        exported,summary=interval_tables(w.store,w.dashboard.state());self.assertEqual(summary.iloc[0]['Min'],0);self.assertEqual(summary.iloc[0]['Max'],10);self.assertEqual(len(exported),3)
        with patch.object(QtWidgets.QInputDialog,'getText',return_value=('Door {open}',True)):w.studio.add_plot_note()
        self.assertEqual(p.annotations[0]['start'],2)
        with tempfile.TemporaryDirectory() as root:
            p.lock_cursor(0,c.id);svg=Path(root)/'note.svg';rendered=render_report(svg,w.store,w.dashboard.state());self.assertIn('Door {open}',svg.read_text());self.assertEqual(rendered[0]['cursor_A_locked_channel'],'Probe')
            saved=save_workspace(Path(root)/'session.json',w.store,[ws.state() for ws in w.workspaces],w.ui_state());w.stats_scope.setCurrentIndex(0);w.restore_path(saved)
            self.assertEqual(w.stats_scope.currentText(),'Whole recording');self.assertEqual(w.dashboard.active.annotations[0]['text'],'Door {open}')
        w.close();self.app.processEvents()

    def test_visible_shortcuts_and_reset(self):
        from app_workbench import AdvancedStudioWindow
        w=AdvancedStudioWindow();w.show();self.app.processEvents()
        actions=[a for submenu in w.studio.submenus.values() for a in submenu.actions()]
        shortcuts={a.text():a.shortcut().toString() for a in actions}
        self.assertEqual(shortcuts['Fit'],'Ctrl+0');self.assertEqual(shortcuts['Zoom X'],'Ctrl+1');self.assertEqual(shortcuts['Lock cursors to channel…'],'Ctrl+L')
        w.close();self.app.processEvents()
