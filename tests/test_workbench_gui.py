import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6 import QtWidgets,QtCore
from app_channel_store import Channel,Dataset
from app_workbench import AdvancedStudioWindow
from app_signal_processing import transform
from app_workspace_io import save_workspace,render_report


class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        self.window=AdvancedStudioWindow();self.window.show();self.errors=[]
        self.messages=patch.object(QtWidgets.QMessageBox,'warning',side_effect=lambda *args:self.errors.append(args[-1]));self.messages.start()
        self.app.processEvents()
    def tearDown(self):
        self.window.close();self.app.processEvents();self.messages.stop();self.assertEqual(self.errors,[])
    def add(self,name='Signal',unit='V',coordinate='time'):
        c=Channel(name,np.arange(1001)/100,np.sin(np.arange(1001)/100),unit=unit,coordinate_kind=coordinate,coordinate_unit='s' if coordinate=='time' else 'Hz')
        self.window.store.add(c);return c
    def select(self,id):
        iterator=QtWidgets.QTreeWidgetItemIterator(self.window.portal.tree)
        while iterator.value():
            item=iterator.value();item.setSelected(item.data(0,QtCore.Qt.ItemDataRole.UserRole)==id);iterator+=1
        self.app.processEvents()
    def test_launch_tabs_axes_and_original_samples(self):
        w=self.window;self.assertEqual(w.tabs.tabText(0),'Engineering Dashboard');self.assertEqual(w.tabs.tabText(2),'Telemetry')
        a=self.add();b=self.add('Power','W');w.dashboard.assign([a.id,b.id]);pane=w.dashboard.active
        self.assertEqual(len(pane.axes),1);pane.cursor_lines[0].setValue(3.25);w._readouts()
        self.assertAlmostEqual(float(w.readout.item(0,2).text()),a.sample(3.25),places=5)
        self.assertGreater(len(pane.curves[a.id][1].xData),0)
    def test_layout_expansion_preserves_frequency_and_axes(self):
        w=self.window;a=self.add();b=self.add('Power','W');w.dashboard.assign([a.id,b.id]);first=w.dashboard.active
        first.cursor_lines[0].setValue(2);state=first.state();f=w.store.add(transform(a,'FFT'));w.dashboard.assign([f.id])
        self.assertEqual(w.dashboard.layout_name,'Horizontal split');self.assertEqual(first.ids,[a.id,b.id]);self.assertEqual(first.bindings,state['bindings'])
        # Binding the new frequency pane must not reset the time pane cursors.
        self.assertEqual(first.cursor_lines[0].value(),2)
        self.assertEqual(w.dashboard.panes[1].coordinate,('frequency','Hz'))
    def test_linked_panes_and_per_tab_cursor_preservation(self):
        w=self.window;a=self.add();w.dashboard.assign([a.id]);w.dashboard.set_layout('Horizontal split')
        second=w.dashboard.panes[1];second.bind([a.id]);w.dashboard.link();w.dashboard.active.cursor_lines[0].setValue(3)
        self.assertEqual(second.cursor_lines[0].value(),3)
        w.tabs.setCurrentIndex(2);w.tabs.setCurrentIndex(0);self.assertEqual(w.dashboard.panes[0].cursor_lines[0].value(),3)
    def test_active_view_bulk_visibility_mask_and_readout(self):
        w=self.window;a=self.add();w.dashboard.assign([a.id]);w.telemetry.assign([a.id]);self.select(a.id)
        w.organize('hide');self.assertEqual(w.dashboard.active.ids,[]);self.assertEqual(w.telemetry.active.ids,[a.id])
        w.dashboard.assign([a.id]);w.dashboard.active.cursor_lines[0].setValue(2);w.dashboard.active.cursor_lines[1].setValue(4);w.organize('mask interval')
        self.assertTrue(np.isnan(w.store.channels[a.id].sample(3)));w._readouts();self.assertEqual(w.readout.item(0,2).text(),'Unknown')
    def test_snapshot_restores_own_bindings_ranges_annotations_and_source(self):
        w=self.window;ds=Dataset('Raw',pd.DataFrame({'x':[1,2]}));w.store.datasets[ds.id]=ds;a=self.add();b=self.add('B','W')
        w.dashboard.assign([a.id]);w.telemetry.assign([b.id]);w.telemetry.active.annotate('ROI',2,4,'Interval');w.telemetry.active.cursor_lines[0].setValue(2.5)
        w.tabs.setCurrentIndex(2);self.select(b.id);w.source_selector.setCurrentIndex(w.source_selector.findData(ds.id))
        with tempfile.TemporaryDirectory() as root:
            path=save_workspace(Path(root)/'workspace.json',w.store,[p.state() for p in w.workspaces],w.ui_state())
            w.store.delete([a.id,b.id]);w.restore_path(path)
            self.assertEqual(w.dashboard.active.ids,[a.id]);self.assertEqual(w.telemetry.active.ids,[b.id]);self.assertEqual(w.tabs.currentIndex(),2)
            self.assertEqual(w.telemetry.active.cursor_lines[0].value(),2.5);self.assertEqual(w.source_selector.currentData(),ds.id)
            self.assertEqual(w.telemetry.active.annotations[0]['kind'],'ROI');self.assertEqual(w.portal.selected(),[b.id])
    def test_preview_apply_and_busy_guard(self):
        w=self.window;a=self.add();self.select(a.id);w.operation.setCurrentText('Offset and scale');w.parameter_fields['scale'].setValue(2)
        w.preview_transform()
        loop=QtCore.QEventLoop();timer=QtCore.QTimer();timer.timeout.connect(lambda:loop.quit() if not w.busy else None);timer.start(5);QtCore.QTimer.singleShot(10000,loop.quit);loop.exec();timer.stop()
        self.assertFalse(w.busy);self.assertIsNotNone(w.preview);w.apply_preview();self.assertEqual(len(w.store.channels),2)
        result=list(w.store.channels.values())[-1];np.testing.assert_allclose(result.y,a.y*2)
        w.busy=True
        with self.assertRaises(ValueError):w.apply_preview()
        w.busy=False
    def test_regex_filter_and_bounds_status(self):
        w=self.window;a=self.add('Temperature','°C');self.add('Power','W');w.portal.regex.setChecked(True);w.portal.search.setText('Temp.*');self.assertEqual(w.portal.tree.topLevelItemCount(),1)
        self.select(a.id);w.prop_attrs.setPlainText('{}');w.warning_max.setText('0.1');w.fault_max.setText('0.2');w.apply_properties();w.dashboard.assign([a.id]);w.dashboard.active.cursor_lines[0].setValue(1);w._readouts()
        self.assertEqual(w.readout.item(0,4).text(),'Fault')
    def test_presentation_formats(self):
        w=self.window;a=self.add();w.dashboard.assign([a.id]);w.dashboard.active.annotate('Marker',3,text='Mark')
        with tempfile.TemporaryDirectory() as root:
            for suffix in ('png','svg','pdf','html','md'):
                path=Path(root)/('report.'+suffix);stats=render_report(path,w.store,w.dashboard.state());self.assertGreater(path.stat().st_size,100);self.assertEqual(stats[0]['channel'],a.name)

    def test_hidden_layout_panes_survive_snapshot_and_reexpansion(self):
        w=self.window;a=self.add();b=self.add('Frequency','V','frequency');w.dashboard.assign([a.id,b.id])
        w.dashboard.set_layout('Single');state=w.dashboard.state();self.assertEqual(len(state['panes']),2)
        w.dashboard.restore(state);w.dashboard.set_layout('Horizontal split');self.assertEqual(w.dashboard.panes[1].ids,[b.id])

    def test_masking_refresh_keeps_secondary_axis_annotations(self):
        w=self.window;a=self.add();b=self.add('Power','W');w.dashboard.assign([a.id,b.id]);pane=w.dashboard.active
        pane.annotate('Threshold',.5,text='Limit',axis='W');w.store.update(b.id,masks=[(1,2)])
        self.assertEqual(len(pane.annotation_items),1);self.assertEqual(pane.annotation_items[0][0],pane.axes['W'][1])

    def test_restore_rejects_obsolete_worker_completion(self):
        import threading
        w=self.window;a=self.add();applied=[];released=threading.Event()
        with tempfile.TemporaryDirectory() as root:
            path=save_workspace(Path(root)/'workspace.json',w.store,[p.state() for p in w.workspaces],w.ui_state())
            w.background(lambda:(released.wait(5),a)[1],lambda c:applied.append(c))
            w.restore_path(path);released.set();w.pool.waitForDone();self.app.processEvents()
            self.assertEqual(applied,[]);self.assertFalse(w.busy);self.assertEqual(list(w.store.channels),[a.id])
