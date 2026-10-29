"""Numerically locked time panes must also align in visible screen geometry.

Each PlotWidget owns a separate scene. Comparing scene X ranges alone misses
the original defect: different left/right axes put the same timestamp in
different viewport pixels. These checks use the complete viewport transform.
"""
import unittest
import sys
import json
from unittest.mock import patch

import numpy as np
from PySide6 import QtCore, QtTest, QtWidgets

from app_channel_store import Channel, ChannelStore
from app_plot_workspace import LAYOUTS, PlotWorkspace


class PlotGeometryAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.store = ChannelStore()
        self.x = np.arange(101, dtype=float)
        self.temperature = self.channel('Temperature', '°C', 'left', 20+self.x/5)
        self.pressure = self.channel('Pressure', 'Pa', 'left', self.x*1300)
        self.power = self.channel('Power', 'W', 'right', self.x*30)
        self.flow = self.channel('Flow', 'L/min', 'left', self.x/7)
        self.speed = self.channel('Actual speed', 'RPM', 'right', self.x*12)
        self.work = PlotWorkspace(self.store)
        self.work.resize(1400, 1050)
        self.work.set_layout('3 stacked')
        self.work.show()
        self.bind_groups([[self.temperature], [self.pressure, self.power, self.flow], [self.speed]])

    def tearDown(self):
        self.work.close()
        self.work.deleteLater()
        self.app.processEvents()

    def channel(self, name, unit, side, values):
        return self.store.add(Channel(name, self.x.copy(), values, unit=unit,
            coordinate_unit='min', attributes={'plot_style': {'side': side}}))

    def settle(self):
        # AxisItem discovers tick text widths during painting. Let both that
        # paint and the queued gutter allocator run before measuring geometry.
        for _ in range(12):
            self.app.processEvents()
            self.work.grab()
            QtTest.QTest.qWait(15)
        self.app.processEvents()

    def bind_groups(self, groups):
        for pane, channels in zip(self.work.visible_panes(), groups):
            pane.bind([channel.id for channel in channels])
        self.work.link()
        self.work.active.setXRange(20, 80, padding=0)
        self.settle()

    def pixel_x(self, pane, value):
        scene = pane.getViewBox().mapViewToScene(QtCore.QPointF(float(value), 0))
        viewport = pane.viewportTransform().map(scene)
        return pane.viewport().mapToGlobal(QtCore.QPoint(0, 0)).x()+viewport.x()

    def drawing_edges(self, pane):
        return [self.pixel_x(pane, edge) for edge in pane.getViewBox().viewRange()[0]]

    def assert_column_geometry(self):
        _, columns = LAYOUTS[self.work.layout_name]
        for column in range(columns):
            panes = self.work.visible_panes()[column::columns]
            reference = self.drawing_edges(panes[0])
            for pane in panes[1:]:
                np.testing.assert_allclose(self.drawing_edges(pane), reference, rtol=0, atol=.5,
                    err_msg='Stacked drawing edges differ despite belonging to the same grid column')

    def assert_locked_time_geometry(self, bounds=(20, 80)):
        self.assert_column_geometry()
        _, columns = LAYOUTS[self.work.layout_name]
        for column in range(columns):
            panes = [pane for pane in self.work.visible_panes()[column::columns] if pane.ids]
            if not panes:
                continue
            for pane in panes:
                np.testing.assert_allclose(pane.getViewBox().viewRange()[0], bounds, rtol=0, atol=1e-7,
                    err_msg='Pixel alignment must never compensate by changing numeric time bounds')
            for time in (bounds[0], sum(bounds)/2, bounds[1]):
                np.testing.assert_allclose([self.pixel_x(pane, time) for pane in panes],
                    self.pixel_x(panes[0], time), rtol=0, atol=.5,
                    err_msg='The same timestamp is drawn in different horizontal pixels')

    def test_mixed_secondary_and_custom_sides_align_time_and_cursor_pixels(self):
        self.assert_locked_time_geometry()
        first = self.work.visible_panes()[0]
        first.cursor_lines[0].setValue(35)
        first.cursor_lines[1].setValue(65)
        self.settle()
        for index, expected in enumerate((35, 65)):
            positions = []
            for pane in self.work.visible_panes():
                self.assertEqual(pane.cursor_lines[index].value(), expected)
                positions.append(self.pixel_x(pane, pane.cursor_lines[index].value()))
            np.testing.assert_allclose(positions, positions[0], rtol=0, atol=.5)
        for pane in self.work.visible_panes():
            for axis in [pane.getAxis('left'), pane.getAxis('right'),
                         *[axis for axis, _ in pane.axes.values()]]:
                self.assertIsNone(axis.fixedWidth, 'Alignment must preserve automatic tick-label sizing')

    def test_tick_growth_then_channel_removal_releases_unused_gutters(self):
        panes = self.work.visible_panes()
        baseline = self.drawing_edges(panes[0])
        axis, view = panes[1].axes['L/min']
        view.setYRange(0, 100, padding=0)
        axis.setTicks([[(0, '0'), (50, '−12345678901234567890.123456789'), (100, '100')]])
        self.settle()
        expanded = self.drawing_edges(panes[0])
        self.assertGreater(expanded[0], baseline[0]+10, 'Wide secondary tick text did not expand the common left gutter')
        self.assert_locked_time_geometry()
        for pane in panes:
            pane.bind([self.temperature.id], fit=False)
        self.settle()
        self.assert_locked_time_geometry()
        reduced = self.drawing_edges(panes[0])
        self.assertLess(reduced[0], expanded[0]-10, 'Removed axes left a permanently oversized gutter')
        self.assertGreater(reduced[1], expanded[1]+10, 'Removed right axes left unused horizontal space')

    def test_pane_order_resize_theme_rebind_and_restore_keep_pixel_and_numeric_alignment(self):
        groups = [[self.speed], [self.pressure, self.power, self.flow], [self.temperature]]
        self.bind_groups(groups)
        self.assert_locked_time_geometry()
        for width in (900, 1600, 1100):
            self.work.resize(width, 900)
            for pane in self.work.visible_panes():
                pane.dark = not pane.dark
                pane.bind(pane.ids, pane.bindings, fit=False)
            self.settle()
            self.assert_locked_time_geometry()
        state = self.work.state()
        stacked_left = self.drawing_edges(self.work.active)[0]
        self.work.set_layout('Single')
        self.settle()
        self.assertLess(self.drawing_edges(self.work.active)[0], stacked_left-10,
                        'Returning to Single retained padding from hidden stacked panes')
        self.work.restore(state)
        self.settle()
        self.assert_locked_time_geometry()

    def test_new_unbound_panes_align_without_queued_callback_errors(self):
        errors=[]
        with patch.object(sys,'excepthook',side_effect=lambda *error:errors.append(error)):
            self.work.set_layout('10 panels')
            # The seven new panes have never passed through bind().
            self.settle()
            self.assert_column_geometry()
        self.assertEqual(errors,[], 'Queued alignment failed for a newly created empty pane')

    def test_grid_columns_align_independently_and_empty_unlocked_panes_keep_geometry(self):
        self.work.set_layout('2×2')
        self.bind_groups([[self.pressure, self.power, self.flow], [self.temperature], [self.speed], [self.temperature]])
        self.assert_locked_time_geometry()
        first, second, third, fourth = self.work.visible_panes()
        # The right column must not inherit the left column's extra axes.
        left_offset = self.drawing_edges(first)[0]-first.viewport().mapToGlobal(QtCore.QPoint()).x()
        right_offset = self.drawing_edges(second)[0]-second.viewport().mapToGlobal(QtCore.QPoint()).x()
        self.assertGreater(left_offset, right_offset+10)
        self.work.set_time_lock(False)
        first.setXRange(10, 30, padding=0)
        third.setXRange(50, 90, padding=0)
        fourth.bind([], fit=False)
        self.settle()
        self.assert_column_geometry()
        np.testing.assert_allclose(first.getViewBox().viewRange()[0], [10, 30], rtol=0, atol=1e-7)
        np.testing.assert_allclose(third.getViewBox().viewRange()[0], [50, 90], rtol=0, atol=1e-7)
        self.assertFalse(fourth.ids)

    def test_native_viewport_insets_keep_both_global_drawing_edges_aligned(self):
        self.work.set_layout('2×2')
        self.bind_groups([[self.pressure,self.power,self.flow],[self.temperature],
                          [self.speed],[self.temperature]])
        first,second,third,fourth=self.work.visible_panes()
        def observed(phase):
            # Retain safe, ordinary GUI-thread measurements if a native layout
            # blocks before the outer test supervisor can produce its result.
            print('GEOMETRY '+json.dumps({'phase':phase,'panes':[
                {'width':pane.width(),'minimum':pane.minimumWidth(),
                 'viewport_width':pane.viewport().width(),
                 'origin':pane.viewport().mapToGlobal(QtCore.QPoint()).x(),
                 'scene_width':pane.sceneRect().width(),'translate_x':pane.viewportTransform().dx(),
                 'padding':pane._canvas_padding,
                 'spacers':[spacer.geometry().width() for spacer in pane._canvas_spacers],
                 'edges':self.drawing_edges(pane)} for pane in self.work.visible_panes()]}),flush=True)
        # A native frame/inset can remove one logical viewport pixel without
        # changing the outer widget's grid-column width. Equal local gutters
        # used to leave the right drawing edge exactly one pixel out of line.
        observed('before native insets')
        third.setViewportMargins(0,0,1,0)
        fourth.setViewportMargins(1,0,0,0)
        observed('native insets applied')
        self.work.queue_canvas_alignment()
        self.settle()
        observed('native insets settled')
        self.assertEqual(first.width(),third.width())
        self.assertEqual(first.viewport().width(),third.viewport().width()+1)
        self.assert_locked_time_geometry()
        self.work.set_time_lock(False)
        first.setXRange(10,30,padding=0);third.setXRange(50,90,padding=0)
        self.settle()
        observed('independent ranges settled')
        self.assert_column_geometry()
        np.testing.assert_allclose(first.getViewBox().viewRange()[0],[10,30],rtol=0,atol=1e-7)
        np.testing.assert_allclose(third.getViewBox().viewRange()[0],[50,90],rtol=0,atol=1e-7)
        # Geometry must settle, rather than continually queuing zero-time work.
        alignment=QtTest.QSignalSpy(self.work._canvas_alignment_timer.timeout)
        for _ in range(30):self.app.processEvents()
        self.assertEqual(alignment.count(),0)
        self.assertFalse(self.work._canvas_alignment_timer.isActive())

    def test_subpixel_measurement_noise_does_not_toggle_integer_minimum_width(self):
        pane=self.work.visible_panes()[0]
        for residual in (0.,1e-10,-1e-10,4e-11,-4e-11):
            pane.set_canvas_padding(0,0,minimum_width=1000+residual)
            self.assertEqual(pane.minimumWidth(),1000)
        pane.set_canvas_padding(0,0,minimum_width=1000.01)
        self.assertEqual(pane.minimumWidth(),1001,
                         'A genuine fractional width must still reserve enough space')


if __name__ == '__main__':
    unittest.main()
