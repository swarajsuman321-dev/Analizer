"""One source-time A/B pair survives mixed split clocks and row locks."""
import unittest

import numpy as np
from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from app_channel_store import Channel, ChannelStore
from app_plot_workspace import PlotWorkspace


class SharedCursorPairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.store=ChannelStore()
        self.workspace=PlotWorkspace(self.store)
        self.workspace.resize(1200,820)
        self.workspace.show()
        self.app.processEvents()

    def tearDown(self):
        self.workspace.close()
        self.workspace.deleteLater()
        self.app.processEvents()

    def add(self,name,x,y=None,unit='min'):
        return self.store.add(Channel(name,np.asarray(x,float),np.asarray(x if y is None else y,float),
            coordinate_kind='time',coordinate_unit=unit,unit='V'))

    def plots(self,channels):
        self.workspace.set_layout('Vertical split')
        for pane,channel in zip(self.workspace.visible_panes(),channels):
            pane.bind([channel.id])
        self.workspace.link()
        self.app.processEvents()
        return self.workspace.visible_panes()

    def test_secondary_short_data_does_not_clamp_pair_to_its_own_support(self):
        long=self.add('Full run',np.arange(11))
        short=self.add('Late short sensor',[3,4,5,6])
        first,second=self.plots([long,short])
        first.setXRange(0,10,padding=0)
        second.cursor_lines[0].setValue(9)
        self.assertEqual([p.cursor_lines[0].value() for p in (first,second)],[9,9])
        self.assertTrue(np.isnan(second.measurements()[short.id]['A']))
        second._cursor_changed()
        self.app.processEvents()
        self.assertEqual([p.cursor_lines[0].value() for p in (first,second)],[9,9])

    def test_snap_uses_native_samples_across_splits_not_each_first_channel(self):
        fine=self.add('Fine',[0,1,2,3,4,5,6,7,8,9,10])
        slow=self.add('Slow',[0,3,6,9,10])
        first,second=self.plots([fine,slow])
        first.setXRange(0,10,padding=0)
        second.cursor_lines[0].setValue(4.2)
        self.assertEqual([p.cursor_lines[0].value() for p in (first,second)],[4,4])
        self.assertEqual(second.measurements()[slow.id]['A'],3)
        self.assertEqual(first.measurements()[fine.id]['A'],4)
        self.workspace.set_active(second)
        second._cursor_changed()
        self.assertEqual(self.workspace.shared_cursor_positions(),[4,first.cursor_lines[1].value()])

    def test_rebinding_and_reset_view_retain_existing_pair(self):
        first_channel=self.add('First',np.arange(11))
        second_channel=self.add('Second',np.arange(30,41))
        first,second=self.plots([first_channel,second_channel])
        first.setXRange(0,40,padding=0)
        first.cursor_lines[0].setValue(4)
        first.cursor_lines[1].setValue(8)
        second.bind([second_channel.id])
        self.assertEqual([line.value() for line in first.cursor_lines],[4,8])
        self.assertEqual([line.value() for line in second.cursor_lines],[4,8])
        first.fit()
        self.assertEqual([line.value() for line in first.cursor_lines],[4,8])

    def test_time_units_convert_shared_line_and_foreign_locked_sample(self):
        minutes=self.add('Minutes',[0,1,2,3,4])
        seconds=self.add('Seconds',[0,60,120,180,240],unit='s')
        first,second=self.plots([minutes,seconds])
        self.workspace.set_time_lock(False)
        first.setXRange(0,4,padding=0)
        second.setXRange(0,240,padding=0)
        first.cursor_lines[0].setValue(2)
        self.assertEqual(second.cursor_lines[0].value(),120)
        first.lock_cursor(0,minutes.id)
        second.cursor_lines[0].setValue(180)
        self.assertEqual(first.cursor_lines[0].value(),3)
        self.assertEqual(first.cursor_locks[0]['index'],3)
        self.assertEqual(second.cursor_locks[0],first.cursor_locks[0])
        second.step_cursor(0,-1)
        self.assertEqual(first.cursor_lines[0].value(),2)
        self.assertEqual(second.cursor_lines[0].value(),120)
        self.assertEqual(self.workspace.shared_cursor_positions('s')[0],120)

    def test_shared_lock_keeps_duplicate_row_identity_and_missing_masks(self):
        duplicate=self.add('Duplicate',[0,1,1,2,3],y=[0,10,20,np.nan,30])
        other=self.add('Other',[0,.5,1,1.5,2,2.5,3])
        first,second=self.plots([duplicate,other])
        first.setXRange(0,3,padding=0)
        first.cursor_lines[0].setValue(1)
        first.lock_cursor(0,duplicate.id)
        first.step_cursor(0,-1)
        self.assertEqual(first.cursor_locks[0]['index'],1)
        self.assertEqual(second.cursor_locks[0]['index'],1)
        self.assertEqual(first.measurements()[duplicate.id]['A'],10)
        second.step_cursor(0,1)
        self.assertEqual(first.cursor_locks[0]['index'],2)
        self.assertEqual(first.measurements()[duplicate.id]['A'],20)

    def test_frequency_plot_keeps_its_own_coordinate_cursors(self):
        time=self.add('Time',np.arange(11))
        frequency=self.store.add(Channel('Spectrum',np.arange(11),np.arange(11),
            coordinate_kind='frequency',coordinate_unit='Hz',unit='V'))
        first,second=self.plots([time,frequency])
        first.cursor_lines[0].setValue(4)
        first.cursor_lines[1].setValue(8)
        first.lock_cursor(0,time.id)
        second.bind([frequency.id])
        self.assertEqual([line.value() for line in first.cursor_lines],[4,8])
        self.assertEqual([line.value() for line in second.cursor_lines],[2,7])
        self.assertEqual(second.cursor_locks,[None,None])

    def test_actual_cursor_drag_in_secondary_split_updates_both(self):
        self.workspace.resize(720,650)
        self.workspace.move(0,0)
        self.workspace.activateWindow()
        self.workspace.raise_()
        a=self.add('A',np.arange(0,11,.1))
        b=self.add('B',np.arange(0,11,.3))
        first,second=self.plots([a,b])
        first.setXRange(0,10,padding=0)
        first.cursor_lines[0].setValue(3)
        self.app.processEvents()
        QtTest.QTest.qWait(60)
        line=second.cursor_lines[0]
        view=second.getViewBox()
        scene=view.mapViewToScene(QtCore.QPointF(line.value(),float(np.mean(view.viewRange()[1]))))
        start=second.mapFromScene(scene)
        end=start+QtCore.QPoint(110,0)
        QtTest.QTest.mouseMove(second.viewport(),QtCore.QPoint(0,0))
        QtTest.QTest.qWait(20)
        QtTest.QTest.mouseMove(second.viewport(),start)
        QtTest.QTest.qWait(80)
        self.app.processEvents()
        self.assertTrue(line.mouseHovering)
        QtTest.QTest.mousePress(second.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=start)
        for point in (start+QtCore.QPoint(40,0),end):
            event=QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove,QtCore.QPointF(point),
                QtCore.QPointF(second.viewport().mapToGlobal(point)),QtCore.Qt.MouseButton.NoButton,
                QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier)
            QtWidgets.QApplication.sendEvent(second.viewport(),event)
            self.app.processEvents()
        QtTest.QTest.mouseRelease(second.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=end)
        self.app.processEvents()
        self.assertNotEqual(first.cursor_lines[0].value(),3)
        self.assertEqual(first.cursor_lines[0].value(),second.cursor_lines[0].value())
