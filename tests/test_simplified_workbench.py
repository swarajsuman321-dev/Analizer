"""User-facing visibility, cursor, resize and report regression scenarios."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6 import QtCore,QtWidgets,QtGui,QtTest
from app_channel_store import Channel,ChannelStore
from app_workbench import AdvancedStudioWindow,FrameModel
from app_presentation import CURSOR_COLORS,MATCH_COLORS,match_color
from app_reporting import export_report,interval_tables,match_scorecard


class SimplifiedWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        self.window=AdvancedStudioWindow();self.window.resize(1280,850);self.window.show();self.app.processEvents()
        self.errors=[];self.warning=patch.object(QtWidgets.QMessageBox,'warning',side_effect=lambda *args:self.errors.append(args[-1]));self.warning.start()
    def tearDown(self):
        self.window.close();self.app.processEvents();self.warning.stop();self.assertEqual(self.errors,[])
    def add(self,name='Temperature',unit='°C',x=None,y=None,**kwargs):
        if x is None:x=np.arange(11,dtype=float)
        if y is None:y=np.asarray(x)*2
        return self.window.store.add(Channel(name,x,y,unit=unit,coordinate_unit='min',**kwargs))
    def item(self,channel_id):
        iterator=QtWidgets.QTreeWidgetItemIterator(self.window.portal.tree)
        while iterator.value():
            item=iterator.value()
            if item.data(0,QtCore.Qt.ItemDataRole.UserRole)==channel_id:return item
            iterator+=1
        raise AssertionError('Channel missing from tree')
    def test_checkbox_and_master_remove_axes_and_show_placeholder(self):
        w=self.window;a=self.add();b=self.add('Power','W')
        item=self.item(a.id);rect=w.portal.tree.visualItemRect(item)
        # Click the native indicator, not a parallel synthetic visibility API.
        option=QtWidgets.QStyleOptionViewItem();option.initFrom(w.portal.tree)
        option.rect=rect;option.features=QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        indicator=w.portal.tree.style().subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator,option,w.portal.tree)
        QtTest.QTest.mouseClick(w.portal.tree.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=indicator.center());self.app.processEvents()
        self.assertIn(a.id,w.dashboard.active.ids)
        w.set_channel_visibility([b.id],True);self.assertEqual(len(w.dashboard.active.axes),1)
        QtTest.QTest.mouseClick(w.portal.select_all,QtCore.Qt.MouseButton.LeftButton);self.app.processEvents()
        self.assertEqual(w.dashboard.active.ids,[]);self.assertEqual(w.dashboard.active.axes,{})
        self.assertTrue(w.dashboard.active.empty_label.isVisible());self.assertTrue(all(not line.isVisible() for line in w.dashboard.active.cursor_lines))
        self.assertEqual(w.readout.rowCount(),0)
        QtTest.QTest.mouseClick(w.portal.select_all,QtCore.Qt.MouseButton.LeftButton);self.app.processEvents()
        self.assertEqual(set(w.dashboard.active.ids),{a.id,b.id})
    def test_filtered_master_and_tab_visibility_are_consistent(self):
        w=self.window;a=self.add();b=self.add('Power','W');w.set_channel_visibility([a.id],True)
        w.portal.search.setText('Power');self.assertEqual(self.item(b.id).checkState(0),QtCore.Qt.CheckState.Unchecked)
        w.set_channel_visibility(list(w.store.channels),True)
        w.tabs.setCurrentIndex(1);self.app.processEvents();self.assertEqual(w.portal.select_all.checkState(),QtCore.Qt.CheckState.Unchecked)
        w.tabs.setCurrentIndex(0);self.app.processEvents();self.assertEqual(w.portal.select_all.checkState(),QtCore.Qt.CheckState.Checked)
        self.assertEqual(w.layout_combo.currentText(),w.dashboard.layout_name)
    def test_import_uses_active_workspace_without_truncating_channels(self):
        w=self.window;other=ChannelStore()
        for i in range(12):other.add(Channel(f'Channel {i}',np.arange(4),np.arange(4),unit='V'))
        w.tabs.setCurrentIndex(1);w.merge_store(other)
        self.assertEqual(w.tabs.currentIndex(),1);self.assertEqual(len(w.comparison.active.ids),12);self.assertEqual(w.dashboard.active.ids,[])
    def test_cursor_clamp_snap_inversion_and_null_values(self):
        w=self.window;a=self.add();b=self.add('Slow','bar',x=np.array([0,3,6,9,10]),y=np.array([0,np.nan,6,9,10]))
        w.dashboard.assign([a.id,b.id]);pane=w.dashboard.active
        pane.cursor_lines[0].setValue(-999);pane.cursor_lines[1].setValue(999)
        self.assertEqual([line.value() for line in pane.cursor_lines],[0,10])
        pane.cursor_lines[0].setValue(8.4);pane.cursor_lines[1].setValue(2.4)
        self.assertEqual([line.value() for line in pane.cursor_lines],[8,2])
        stats=pane.measurements();self.assertEqual(stats[a.id]['ΔX'],6);self.assertEqual(stats[a.id]['ΔY'],-12)
        self.assertTrue(np.isnan(stats[b.id]['B']))
        pane.setXRange(3,6,padding=0);self.app.processEvents()
        self.assertTrue(all(3<=line.value()<=6 for line in pane.cursor_lines))
        pane.setXRange(-999,999,padding=0);self.app.processEvents();self.assertTrue(all(0<=line.value()<=10 for line in pane.cursor_lines))
    def test_cursor_colors_survive_themes_and_match_readout(self):
        w=self.window;c=self.add();w.dashboard.assign([c.id])
        for theme in ('Dark','Light','System'):
            w.theme.apply(theme);w._readouts()
            for i,line in enumerate(w.dashboard.active.cursor_lines):
                self.assertEqual(line.pen.color().name(),CURSOR_COLORS[i].lower())
                self.assertEqual(line.hoverPen.color().name(),CURSOR_COLORS[i].lower())
                self.assertEqual(w.readout.item(0,i+2).foreground().color().name(),CURSOR_COLORS[i].lower())
        self.assertIn('ΔX',w.interval_card.text());self.assertIn('Mean',w.interval_card.text())
    def test_real_cursor_mouse_drag_stays_inside_data(self):
        w=self.window;c=self.add();w.dashboard.assign([c.id]);self.app.processEvents();pane=w.dashboard.active
        line=pane.cursor_lines[0];before=line.value()
        scene=pane.getViewBox().mapViewToScene(QtCore.QPointF(before,10));start=pane.mapFromScene(scene)
        end=start+QtCore.QPoint(100,0)
        QtTest.QTest.mouseMove(pane.viewport(),start)
        QtTest.QTest.qWait(40)  # Let the scene process hover before the drag starts.
        QtTest.QTest.mousePress(pane.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=start)
        QtTest.QTest.mouseMove(pane.viewport(),start+QtCore.QPoint(30,0),delay=30)
        QtTest.QTest.mouseMove(pane.viewport(),end,delay=30)
        QtTest.QTest.mouseRelease(pane.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=end)
        self.app.processEvents();self.assertNotEqual(line.value(),before);self.assertGreaterEqual(line.value(),0);self.assertLessEqual(line.value(),10)
    def test_missing_empty_and_mixed_frequency_channels(self):
        w=self.window;a=self.add(y=np.full(11,np.nan));b=self.add('Empty','W',x=np.array([]),y=np.array([]))
        c=self.add('Slow','bar',x=np.array([0,4,8]),y=np.array([0,4,8]))
        w.dashboard.assign([a.id,b.id,c.id]);w._readouts()
        stats=w.dashboard.active.measurements();self.assertTrue(np.isnan(stats[a.id]['Mean']));self.assertTrue(np.isnan(stats[b.id]['A']))
        w.set_channel_visibility([a.id,b.id,c.id],False);self.assertEqual(w.dashboard.active.axes,{})
    def test_axes_match_traces_and_resize_without_orphans(self):
        w=self.window;channels=[self.add('Temperature','°C'),self.add('Pressure','bar'),self.add('Power','W')]
        w.dashboard.assign([c.id for c in channels]);pane=w.dashboard.active
        for size in ((1024,680),(1600,1000),(1100,720)):
            w.resize(*size);w.show_dock('Properties');self.app.processEvents();w.docks['Properties'].hide();self.app.processEvents()
            self.assertGreater(pane.getViewBox().width(),150)
            for unit,(axis,vb) in pane.axes.items():
                self.assertAlmostEqual(vb.geometry().height(),pane.getViewBox().sceneBoundingRect().height(),delta=1)
                c=next(c for c in channels if c.unit==unit)
                self.assertEqual(axis.pen().color().name(),pane.curves[c.id][1].pen.color().name())
        w.set_channel_visibility([channels[1].id],False);self.assertEqual(len(pane.axes),1)
    def test_percentage_boundaries_are_visual_and_invalid_are_neutral(self):
        for value,color in ((90,MATCH_COLORS[0]),(100,MATCH_COLORS[0]),(89.99,MATCH_COLORS[1]),(70,MATCH_COLORS[1]),(69.99,MATCH_COLORS[2]),(0,MATCH_COLORS[2])):
            self.assertEqual(match_color(value),color)
            c=self.add(str(value),attributes={'match_percent':value});self.window.dashboard.assign([c.id],replace=True);self.window._readouts()
            cell=self.window.readout.item(0,4);self.assertEqual(cell.background().color().name(),color);self.assertEqual(cell.text(),f'{value:.1f}%')
        for value in (None,np.nan,np.inf,-1,101,'invalid'):self.assertIsNone(match_color(value))
        score=match_scorecard(pd.DataFrame({'percent':['10.00%','-30.00%','31.00%','0%','0%'],'status':['GREEN','RED','RED','REVIEW','MISSING']}))
        np.testing.assert_allclose(score.match_percent[:3],[90,70,69]);self.assertTrue(score.match_percent[3:].isna().all());self.assertNotIn('status',score)
    def test_active_interval_exports_roundtrip_colors_and_cursors(self):
        w=self.window;c=self.add(attributes={'match_percent':90});w.dashboard.assign([c.id]);pane=w.dashboard.active
        pane.cursor_lines[0].setValue(8);pane.cursor_lines[1].setValue(2)
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            data,summary=export_report(directory/'interval.xlsx',w.store,w.dashboard.state())
            self.assertEqual(data.coordinate.tolist(),list(range(2,9)));self.assertEqual(summary.iloc[0]['cursor_A_X'],8);self.assertEqual(summary.iloc[0]['ΔY'],-12)
            import openpyxl
            book=openpyxl.load_workbook(directory/'interval.xlsx');sheet=book['Cursor summary'];headers=[v.value for v in sheet[1]]
            self.assertEqual(sheet.cell(2,headers.index('match_percent')+1).fill.fgColor.rgb[-6:].lower(),MATCH_COLORS[0][1:]);book.close()
            export_report(directory/'interval.csv',w.store,w.dashboard.state());readback=pd.read_csv(directory/'interval.csv')
            self.assertEqual(readback.coordinate.tolist(),list(range(2,9)));self.assertEqual(readback.cursor_A_X.unique().tolist(),[8])
            for suffix in ('pdf','png'):
                export_report(directory/f'report.{suffix}',w.store,w.dashboard.state());self.assertGreater((directory/f'report.{suffix}').stat().st_size,1000)
            from PIL import Image
            pixels=np.asarray(Image.open(directory/'report.png').convert('RGB')).reshape(-1,3)
            for color in (*CURSOR_COLORS,MATCH_COLORS[0]):
                rgb=np.array([int(color[i:i+2],16) for i in (1,3,5)])
                self.assertTrue(np.any(np.max(np.abs(pixels.astype(int)-rgb),axis=1)<5),color)
    def test_export_button_uses_one_dialog_and_cancel_is_safe(self):
        w=self.window;c=self.add();w.dashboard.assign([c.id])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'quick.csv'
            with patch.object(QtWidgets.QFileDialog,'getSaveFileName',return_value=(str(path),'CSV interval (*.csv)')) as dialog:
                w.export_button.click();dialog.assert_called_once();self.assertTrue(path.exists())
            with patch.object(QtWidgets.QFileDialog,'getSaveFileName',return_value=('','')) as dialog:w.export_button.click();dialog.assert_called_once()
        self.assertNotIn('Preview sample',[a.text() for a in w.findChildren(QtGui.QAction)])
        self.assertEqual(w.tabs.count(),2);self.assertFalse(hasattr(w,'preview_plot'))
    def test_export_empty_selection_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'empty.pdf'
            with self.assertRaisesRegex(ValueError,'at least one channel'):export_report(path,self.window.store,self.window.dashboard.state())
            self.assertFalse(path.exists())

    def test_toggle_preserves_selected_interval_and_zoom(self):
        w=self.window;a=self.add();b=self.add('Power','W')
        w.set_channel_visibility([a.id],True);pane=w.dashboard.active
        pane.setXRange(2,9,padding=0);pane.cursor_lines[0].setValue(3);pane.cursor_lines[1].setValue(8)
        w.set_channel_visibility([b.id],True)
        self.assertEqual([line.value() for line in pane.cursor_lines],[3,8])
        np.testing.assert_allclose(pane.getViewBox().viewRange()[0],[2,9])
        w.set_channel_visibility([b.id],False)
        self.assertEqual([line.value() for line in pane.cursor_lines],[3,8])

    def test_delete_channels_from_hidden_panes_removes_stale_bindings(self):
        w=self.window;a=self.add();b=self.add('Power','W');workspace=w.dashboard
        workspace.assign([a.id]);workspace.set_layout('Horizontal split');workspace.panes[1].bind([b.id])
        workspace.set_layout('Single');w.store.delete([b.id]);workspace.set_layout('Horizontal split')
        self.assertEqual(workspace.panes[1].ids,[]);self.assertTrue(workspace.panes[1].empty_label.isVisible())
        w._readouts()

    def test_linked_panes_keep_common_cursor_with_different_sample_clocks(self):
        w=self.window;a=self.add();b=self.add('Slow','W',x=np.array([0,3,6,9,10]),y=np.array([0,3,6,9,10]))
        workspace=w.dashboard;workspace.assign([a.id]);workspace.set_layout('Horizontal split')
        second=workspace.panes[1];second.bind([b.id]);workspace.link()
        first=workspace.panes[0];first.cursor_lines[0].setValue(4)
        self.assertEqual(second.cursor_lines[0].value(),4)
        self.assertEqual(second.measurements()[b.id]['A'],3)
        first.setXRange(2,8,padding=0);self.app.processEvents()
        self.assertEqual(first.cursor_lines[0].value(),second.cursor_lines[0].value())
        np.testing.assert_allclose(first.getViewBox().viewRange()[0],second.getViewBox().viewRange()[0],atol=.1)

    def test_snapshot_retains_percentage_scorecard_without_stale_results(self):
        from app_workspace_io import save_workspace
        w=self.window;c=self.add();w.dashboard.assign([c.id])
        w.scorecard_data=match_scorecard(pd.DataFrame({'parameter':['Pressure','Unknown'],'percent':['10%','—'],'status':['GREEN','MISSING']}))
        with tempfile.TemporaryDirectory() as directory:
            path=save_workspace(Path(directory)/'session.json',w.store,[workspace.state() for workspace in w.workspaces],w.ui_state())
            w.scorecard_data=None;w.restore_path(path)
            self.assertEqual(w.scorecard_data.iloc[0]['match_percent'],90)
            self.assertTrue(pd.isna(w.scorecard_data.iloc[1]['match_percent']))
            path=save_workspace(Path(directory)/'plain.json',w.store,[workspace.state() for workspace in w.workspaces])
            w.restore_path(path);self.assertIsNone(w.scorecard_data)

    def test_analysis_report_does_not_include_unrelated_comparison(self):
        w=self.window;c=self.add();w.dashboard.assign([c.id]);w.scorecard_data=pd.DataFrame({'match_percent':[90]})
        with patch.object(QtWidgets.QFileDialog,'getSaveFileName',return_value=('/tmp/report.pdf','PDF summary (*.pdf)')),patch('app_reporting.export_report') as export:
            w.report();self.assertIsNone(export.call_args.args[3])
            w.tabs.setCurrentIndex(1);w.comparison.assign([c.id]);w.report();self.assertIs(export.call_args.args[3],w.scorecard_data)

    def test_free_cursor_positions_survive_workspace_restore(self):
        from app_workspace_io import save_workspace
        w=self.window;c=self.add();w.dashboard.assign([c.id]);w.snap_checkbox.setChecked(False)
        pane=w.dashboard.active;pane.cursor_lines[0].setValue(3.25);pane.cursor_lines[1].setValue(7.75)
        with tempfile.TemporaryDirectory() as directory:
            path=save_workspace(Path(directory)/'session.json',w.store,[workspace.state() for workspace in w.workspaces],w.ui_state())
            w.snap_checkbox.setChecked(True)
            w.restore_path(path);pane=w.dashboard.active
            self.assertFalse(pane.snap);self.assertFalse(w.snap_checkbox.isChecked())
            self.assertEqual([line.value() for line in pane.cursor_lines],[3.25,7.75])
            w.snap_checkbox.setChecked(True);self.assertEqual([line.value() for line in pane.cursor_lines],[3,8])


if __name__=='__main__':unittest.main()
