"""Approved numerical chart contracts; geometry is exercised offscreen.

Native Windows mouse/DPI acceptance remains a separate release gate. These
tests intentionally assert source identity and numerical limits, rather than
assuming a successful render proves the plotted readings are correct.
"""
import unittest
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from app_channel_store import Channel, ChannelStore
from app_plot_workspace import PlotWorkspace, install_graph_navigation
from app_reporting import interval_tables


class AuditPlotAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.store=ChannelStore()
        self.a=self.store.add(Channel('Temperature',np.arange(101.),np.arange(101.)+20,unit='°C',coordinate_unit='min'))
        self.b=self.store.add(Channel('Pressure',np.arange(101.),np.arange(101.)*100000,unit='Pa',coordinate_unit='min'))
        self.w=PlotWorkspace(self.store);self.w.resize(1024,680);self.w.show()
        self.w.assign([self.a.id]);self.w.set_layout('Horizontal split');self.w.panes[1].bind([self.b.id]);self.w.link();self.app.processEvents()

    def tearDown(self):
        self.w.close();self.w.deleteLater();self.app.processEvents()

    def test_time_lock_uses_exact_numbers_across_unequal_axis_geometry(self):
        p,q=self.w.visible_panes();self.w.set_time_lock(False)
        p.setXRange(0,20,padding=0);q.setXRange(40,80,padding=0)
        self.w.set_active(q);self.w.set_time_lock(True)
        for pane in (p,q):np.testing.assert_allclose(pane.viewRange()[0],[40,80],rtol=0,atol=1e-10)
        for size in ((1024,680),(1600,1000),(1100,760)):
            self.w.resize(*size);self.app.processEvents()
            for pane in (p,q):np.testing.assert_allclose(pane.viewRange()[0],[40,80],rtol=0,atol=1e-10)
        self.w.navigate('in');self.app.processEvents()
        np.testing.assert_allclose(p.viewRange()[0],q.viewRange()[0],rtol=0,atol=1e-10)
        self.w.set_time_lock(False);p.setXRange(1,3,padding=0)
        self.assertFalse(np.allclose(p.viewRange()[0],q.viewRange()[0]))

    def test_non_temporal_panes_never_join_time_lock(self):
        f=self.store.add(Channel('Spectrum',[0,1,2],[1,3,1],unit='V',coordinate_kind='frequency',coordinate_unit='Hz'))
        self.w.panes[1].bind([f.id]);self.w.link();q=self.w.panes[1]
        q.setXRange(.5,1.5,padding=0);self.w.panes[0].setXRange(40,80,padding=0)
        np.testing.assert_allclose(q.viewRange()[0],[.5,1.5])

    def test_duplicate_lock_identity_is_shared_by_marker_summary_export_restore(self):
        c=self.store.add(Channel('Duplicate sensor',[0,1,1,1,2,3],[0,10,20,30,40,50],unit='V',coordinate_unit='min'))
        self.w.set_layout('Single');p=self.w.active;p.bind([c.id]);p.cursor_lines[0].setValue(1);p.lock_cursor(0,c.id)
        p.step_cursor(0,-1);self.assertEqual(p.cursor_locks[0]['index'],2)
        p.lock_cursor(0,c.id)  # Reapplying unchanged selections keeps the row.
        self.assertEqual(p.cursor_locks[0]['index'],2)
        p.cursor_lines[1].setValue(1);p.lock_cursor(1,c.id)
        self.assertEqual(p.cursor_value(c.id,0),20)
        np.testing.assert_equal(p.cursor_markers[0].getData()[1],[20])
        reading=p.measurements()[c.id];self.assertEqual(reading['A'],20);self.assertEqual(reading['B'],30);self.assertEqual(reading['ΔY'],10);self.assertEqual(reading['ΔX'],0)
        data,summary=interval_tables(self.store,self.w.state())
        self.assertEqual(summary.iloc[0]['A'],20);self.assertEqual(summary.iloc[0]['B'],30)
        self.assertEqual(list(data.source_sample_index),[2,3]);self.assertEqual(len(c.x),6)
        state=self.w.state();self.w.restore(state);p=self.w.active
        self.assertEqual(p.cursor_locks[0]['index'],2);self.assertEqual(p.cursor_value(c.id,0),20)
        p.step_cursor(0,-1);self.assertEqual(p.cursor_locks[0]['index'],1);self.assertEqual(p.cursor_value(c.id,0),10)
        p.step_cursor(0,1);self.assertEqual(p.cursor_locks[0]['index'],2)

    def test_viewport_wheel_and_box_honor_axis_mode_for_independent_y_axes(self):
        self.w.set_layout('Single');pane=self.w.active;pane.bind([self.a.id,self.b.id]);pane.set_cursor_mode('off')
        for mode in ('x','y','xy'):
            for gesture in ('wheel','box'):
                with self.subTest(mode=mode,gesture=gesture):
                    self.w.navigate('reset');self.w.navigate(mode);self.app.processEvents();QtTest.QTest.qWait(25)
                    before_x=np.array(pane.viewRange()[0]);before_y=[np.array(view.viewRange()[1]) for view in pane.y_views()]
                    bounds=pane.getViewBox().sceneBoundingRect()
                    if gesture=='wheel':
                        position=pane.mapFromScene(bounds.center())
                        event=QtGui.QWheelEvent(QtCore.QPointF(position),QtCore.QPointF(pane.viewport().mapToGlobal(position)),
                            QtCore.QPoint(),QtCore.QPoint(0,120),QtCore.Qt.MouseButton.NoButton,
                            QtCore.Qt.KeyboardModifier.NoModifier,QtCore.Qt.ScrollPhase.NoScrollPhase,False)
                        self.app.sendEvent(pane.viewport(),event)
                    else:
                        start=pane.mapFromScene(bounds.topLeft()+QtCore.QPointF(bounds.width()*.25,bounds.height()*.25))
                        end=pane.mapFromScene(bounds.topLeft()+QtCore.QPointF(bounds.width()*.75,bounds.height()*.75))
                        QtTest.QTest.mouseMove(pane.viewport(),start);QtTest.QTest.qWait(25)
                        QtTest.QTest.mousePress(pane.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=start);QtTest.QTest.qWait(25)
                        QtTest.QTest.mouseMove(pane.viewport(),start+(end-start)/2);QtTest.QTest.qWait(25)
                        QtTest.QTest.mouseMove(pane.viewport(),end);QtTest.QTest.qWait(25)
                        QtTest.QTest.mouseRelease(pane.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=end)
                    self.app.processEvents()
                    after_x=pane.viewRange()[0];after_y=[view.viewRange()[1] for view in pane.y_views()]
                    if mode=='y':np.testing.assert_allclose(after_x,before_x,rtol=0,atol=1e-7)
                    else:self.assertLess(np.ptp(after_x),np.ptp(before_x)*.95)
                    for first,last in zip(before_y,after_y):
                        if mode=='x':np.testing.assert_allclose(last,first,rtol=0,atol=1e-7)
                        else:self.assertLess(np.ptp(last),np.ptp(first)*.95)

    def test_playback_steps_the_locked_trace_and_keeps_duplicate_rows(self):
        from types import SimpleNamespace
        from app_compact_controls import CompactControls
        channel=self.store.add(Channel('Repeated pressure',[0,1,1,1,2],[0,10,20,30,40],unit='Pa',coordinate_unit='min'))
        pane=self.w.active;pane.bind([self.a.id,channel.id]);pane.cursor_lines[0].setValue(1);pane.lock_cursor(0,channel.id)
        pane.step_cursor(0,-1);pane.step_cursor(0,-1)
        self.assertEqual(pane.cursor_locks[0]['index'],1)
        controls=SimpleNamespace(w=SimpleNamespace(studio=SimpleNamespace(seek=pane.cursor_lines[0].setValue)))
        CompactControls.step(controls,pane,1)
        self.assertEqual(pane.cursor_locks[0]['index'],2)
        self.assertEqual(pane.cursor_value(channel.id,0),20)
        np.testing.assert_equal(pane.cursor_markers[0].getData()[1],[20])

    def test_pointer_navigation_selects_its_pane_before_followup_toolbar_action(self):
        first,second=self.w.visible_panes();self.w.set_active(first);self.w.navigate('y')
        position=second.mapFromScene(second.getViewBox().sceneBoundingRect().center())
        event=QtGui.QWheelEvent(QtCore.QPointF(position),QtCore.QPointF(second.viewport().mapToGlobal(position)),
            QtCore.QPoint(),QtCore.QPoint(0,120),QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.NoModifier,QtCore.Qt.ScrollPhase.NoScrollPhase,False)
        self.app.sendEvent(second.viewport(),event)
        self.assertIs(self.w.active,second)

    def test_locked_masks_crossing_and_out_of_range_indices_stay_safe(self):
        p=self.w.active;p.lock_cursor(0,self.a.id);p.lock_cursor(1,self.a.id)
        p.cursor_locks[0]['index']=80;p.cursor_locks[1]['index']=20;p._cursor_changed()
        self.assertEqual(p.measurements()[self.a.id]['ΔX'],60)
        self.assertEqual(p.measurements()[self.a.id]['ΔY'],-60)
        self.store.update(self.a.id,masks=[(79,81)]);p.bind(p.ids,fit=False)
        self.assertTrue(np.isnan(p.cursor_value(self.a.id,0)));self.assertFalse(p.cursor_markers[0].isVisible())
        saved=p.state();saved['cursor_locks'][0]['index']=999;p.restore(saved)
        self.assertEqual(p.cursor_locks[0]['index'],100);self.assertEqual(p.cursor_lines[0].value(),100)

    def test_context_menu_avoids_native_transform_callbacks_and_preserves_fft(self):
        p=self.w.active;menu=p.create_context_menu()
        self.assertEqual([a.text() for a in menu.actions()[:5]],['Hand / Pan','Cursor','Zoom XY','Zoom X','Zoom Y'])
        cycles=next(a for a in menu.actions() if a.text()=='Snap to Cycles')
        self.assertFalse(cycles.isEnabled());self.assertIn('Configure',cycles.toolTip())
        control=p.getPlotItem().ctrl.fftCheck;control.setChecked(True);self.app.processEvents();self.assertFalse(control.isChecked())
        control.setChecked(False);self.app.processEvents();self.assertEqual(p.coordinate,('time','min'))
        from app_signal_processing import transform
        spectrum=transform(self.a,'FFT');self.assertEqual(spectrum.coordinate_kind,'frequency');self.assertEqual(spectrum.coordinate_unit,'Hz')
        self.assertTrue(any(a.text()=='Calculate Channel' for a in menu.actions()))

    def test_revert_is_previous_view_not_fit_and_cycles_require_reviewed_positions(self):
        p=self.w.active;p.setXRange(40,80,padding=0);p.remember_view();self.w.navigate('in')
        zoomed=list(p.viewRange()[0]);p.navigate_history(-1)
        np.testing.assert_allclose(p.viewRange()[0],[40,80]);self.assertNotEqual(zoomed,p.viewRange()[0])
        with self.assertRaises(ValueError):p.set_cycle_boundaries([2,1])
        p.set_cycle_boundaries([0,25,50,75,100]);p.cycle_snap=True;p.cursor_lines[0].setValue(48)
        self.assertEqual(p.cursor_lines[0].value(),50)

    def test_split_layouts_allocate_drawing_height_and_scroll_instead_of_collapsing(self):
        for layout in ('Single','Horizontal split','Vertical split','2×2','10 panels','Single'):
            self.w.set_layout(layout);self.app.processEvents()
            for p in self.w.visible_panes():self.assertGreaterEqual(p.getViewBox().height(),150)
        self.w.set_layout('Vertical split');self.w.set_pane_proportions(rows=[1,2]);saved=self.w.state();self.w.restore(saved)
        self.assertEqual(self.w.grid.rowStretch(1),2*self.w.grid.rowStretch(0))

    def test_one_navigation_presentation_lives_beside_graph_tabs_with_overflow(self):
        tabs=QtWidgets.QTabWidget();other=PlotWorkspace(self.store)
        self.w.hide();tabs.addTab(self.w,'Analysis');tabs.addTab(other,'Comparison')
        header=install_graph_navigation(tabs,[self.w,other]);tabs.resize(600,500);tabs.show();self.app.processEvents()
        self.assertIs(tabs.cornerWidget(QtCore.Qt.Corner.TopRightCorner),header)
        self.assertIs(self.w.navigation_bar.parentWidget(),header)
        self.assertEqual(header.count(),2);self.assertTrue(tabs.tabBar().isVisible())
        self.assertLessEqual(header.width(),tabs.width()-tabs.tabBar().sizeHint().width())
        self.assertLessEqual(header.geometry().right(),tabs.rect().right())
        self.assertGreaterEqual(tabs.tabBar().height(),header.height())
        # A widget minimumHeight is insufficient: styles position the page
        # using the actual tab rectangle and can let a taller corner overlap.
        self.assertGreaterEqual(tabs.tabBar().tabRect(0).height(),header.height())
        page_top=self.w.mapTo(tabs,QtCore.QPoint(0,0)).y()
        self.assertGreater(page_top,header.geometry().bottom())
        tabs.setCurrentIndex(1);self.app.processEvents();self.assertIs(header.currentWidget(),other.navigation_bar)
        tabs.removeTab(0);self.w.setParent(None);tabs.close();other.close();tabs.deleteLater()

    def test_long_inline_legend_resizes_without_covering_the_canvas(self):
        name='MCB_MotorControlBridge_sDataResourceTemperatureMeasurement_ucMotorTemperature_0_R_'*2
        channel=self.store.add(Channel(name,[0,1,2],[10,20,30],unit='°C',coordinate_unit='min'))
        self.w.set_layout('Single');pane=self.w.active;pane.bind([channel.id]);self.app.processEvents()
        for width in (1400,600,1100):
            self.w.resize(width,680);self.app.processEvents()
            sample,label=pane.legend.items[0]
            self.assertIn('…',label.text)
            self.assertIn(name,label.toolTip());self.assertIn(name,label.item.toolTip())
            self.assertIn(name,sample.toolTip())
            self.assertLessEqual(pane.legend.width(),max(100,min(460,pane.getViewBox().width()*.55))+12)
            self.assertEqual(sample.item.opts['pen'].color(),pane.curves[channel.id][1].pen.color())


if __name__=='__main__':unittest.main()
