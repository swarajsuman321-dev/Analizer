"""Real diagonal gestures must respect the selected zoom dimension."""
import unittest
import numpy as np
from PySide6 import QtCore,QtWidgets,QtGui,QtTest
from app_workbench import AdvancedStudioWindow
from app_channel_store import Channel

class ZoomModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        self.window=AdvancedStudioWindow();self.window.resize(1280,850);self.window.show()
        for name,unit,factor in [('Probe','°C',1),('Power','W',100)]:
            self.window.store.add(Channel(name,np.arange(101.),np.arange(101.)*factor,unit=unit,coordinate_unit='min'))
        self.window.dashboard.assign(list(self.window.store.channels));self.app.processEvents();self.pane=self.window.dashboard.active;self.pane.set_cursor_mode('off')
    def tearDown(self):self.window.close();self.app.processEvents();self.app.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
    def ranges(self):return np.array(self.pane.getViewBox().viewRange()[0]),[np.array(view.viewRange()[1]) for view in self.pane.y_views()]
    def drag_rectangle(self):
        p=self.pane;rect=p.getViewBox().sceneBoundingRect();start=p.mapFromScene(rect.topLeft()+QtCore.QPointF(rect.width()*.25,rect.height()*.25));end=p.mapFromScene(rect.topLeft()+QtCore.QPointF(rect.width()*.75,rect.height()*.75))
        QtTest.QTest.mouseMove(p.viewport(),start);QtTest.QTest.qWait(50);QtTest.QTest.mousePress(p.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=start)
        QtTest.QTest.mouseMove(p.viewport(),start+(end-start)/2,delay=40);QtTest.QTest.mouseMove(p.viewport(),end,delay=40);QtTest.QTest.mouseRelease(p.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=end);self.app.processEvents()
    def verify_mode(self,mode,operation):
        self.pane.fit();self.window.studio.navigation(mode);self.app.processEvents();bx,by=self.ranges();operation();ax,ay=self.ranges()
        if mode=='y':np.testing.assert_allclose(ax,bx,rtol=0,atol=1e-9)
        else:self.assertLess(np.ptp(ax),np.ptp(bx)*.95)
        for before,after in zip(by,ay):
            if mode=='x':np.testing.assert_allclose(after,before,rtol=0,atol=1e-8)
            else:self.assertLess(np.ptp(after),np.ptp(before)*.95)
    def test_rectangle_x_only(self):self.verify_mode('x',self.drag_rectangle)
    def test_rectangle_y_only(self):self.verify_mode('y',self.drag_rectangle)
    def test_rectangle_xy(self):self.verify_mode('xy',self.drag_rectangle)
    def test_zoom_buttons_respect_mode(self):
        for mode in ('x','y','xy'):
            with self.subTest(mode=mode):self.verify_mode(mode,lambda:self.window.studio.zoom(.5))
    def test_wheel_respects_mode(self):
        def wheel():
            p=self.pane;pos=p.mapFromScene(p.getViewBox().sceneBoundingRect().center());event=QtGui.QWheelEvent(QtCore.QPointF(pos),QtCore.QPointF(p.viewport().mapToGlobal(pos)),QtCore.QPoint(),QtCore.QPoint(0,120),QtCore.Qt.MouseButton.NoButton,QtCore.Qt.KeyboardModifier.NoModifier,QtCore.Qt.ScrollPhase.NoScrollPhase,False)
            self.app.sendEvent(p.viewport(),event);self.app.processEvents()
        for mode in ('x','y','xy'):
            with self.subTest(mode=mode):self.verify_mode(mode,wheel)
    def test_selection_band_spans_disabled_axis(self):
        view=self.pane.getViewBox();bounds=view.viewRect();small=QtCore.QRectF(20,20,10,10)
        self.window.studio.navigation('x');band=view.constrained_rectangle(small);self.assertEqual(band.top(),bounds.top());self.assertEqual(band.bottom(),bounds.bottom())
        self.window.studio.navigation('y');band=view.constrained_rectangle(small);self.assertEqual(band.left(),bounds.left());self.assertEqual(band.right(),bounds.right())
