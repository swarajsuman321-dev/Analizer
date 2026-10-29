"""Fullscreen keeps every real split graph and shared navigation usable."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import traceback
import unittest
from unittest.mock import patch

import numpy as np
from PySide6 import QtCore, QtTest, QtWidgets
from shiboken6 import isValid

from app_channel_store import Channel
from app_plot_workspace import PlotPane
from app_workbench import AdvancedStudioWindow
from app_workspace_fullscreen import WorkspaceFullscreenController


class WorkspaceFullscreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        environment = patch.dict(os.environ, {
            'ANALIZER_SETTINGS_DIR': str(root/'settings'), 'ANALIZER_OUTPUT_DIR': str(root/'outputs'),
            'MPLCONFIGDIR': str(root/'matplotlib'), 'XDG_CACHE_HOME': str(root/'cache')})
        environment.start()
        self.addCleanup(environment.stop)
        self.callback_errors = []
        hook = patch.object(sys, 'excepthook', lambda kind, value, tb:
            self.callback_errors.append(''.join(traceback.format_exception(kind, value, tb))))
        hook.start()
        self.addCleanup(hook.stop)
        self.window = AdvancedStudioWindow()
        self.window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.window.resize(1400, 900)
        self.window.graph_fullscreen.action.setShortcut('Shift+F11')
        self.controller = getattr(self.window, 'workspace_fullscreen', None) or WorkspaceFullscreenController(self.window)
        self.window.workspace_fullscreen = self.controller
        self.window.show()
        self.workspace = self.window.dashboard
        self.first = self.window.store.add(Channel('Temperature', [0, 1, 1, 2, 3], [10, 20, 30, 40, 50],
            unit='°C', coordinate_unit='min', attributes={'match_percent': 94}))
        self.second = self.window.store.add(Channel('Pressure', [0, 1, 1, 2, 3], [100, 200, 300, 400, 500],
            unit='Pa', coordinate_unit='min'))
        self.workspace.set_layout('Vertical split')
        self.workspace.panes[0].bind([self.first.id])
        self.workspace.panes[1].bind([self.second.id])
        self.workspace.set_active(self.workspace.panes[1])
        self.events()

    def events(self):
        for _ in range(4):
            self.app.processEvents()
            QtTest.QTest.qWait(20)

    def tearDown(self):
        if isValid(self.controller):
            self.controller.exit(restore_focus=False)
        if isValid(self.window):
            self.window.close()
            self.window.deleteLater()
        self.events()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.assertEqual(self.callback_errors, [])

    def test_fullscreen_contains_original_two_and_four_pane_layouts(self):
        for name in ('Vertical split', '2×2'):
            with self.subTest(layout=name):
                self.workspace.set_layout(name)
                for index, pane in enumerate(self.workspace.visible_panes()):
                    pane.bind([self.first.id if index%2 == 0 else self.second.id])
                self.events()
                panes = tuple(self.workspace.visible_panes())
                container = self.workspace.container
                positions = [self.workspace.grid.getItemPosition(self.workspace.grid.indexOf(pane)) for pane in panes]
                curves = [dict(pane.curves) for pane in panes]
                ranges = [deepcopy(pane.getViewBox().viewRange()) for pane in panes]
                host = self.controller.enter(self.workspace)
                self.events()
                self.assertTrue(host.isFullScreen())
                self.assertEqual(set(host.findChildren(PlotPane)), set(panes))
                self.assertIs(self.controller.graph_scroll.widget(), container)
                self.assertIsNot(self.workspace.scroll.widget(), container)
                self.assertTrue(all(pane.isVisible() for pane in panes))
                for index, pane in enumerate(panes):
                    self.assertEqual(self.workspace.grid.getItemPosition(self.workspace.grid.indexOf(pane)), positions[index])
                    self.assertEqual(pane.curves, curves[index])
                    np.testing.assert_allclose(pane.getViewBox().viewRange(), ranges[index], rtol=0, atol=1e-7)
                self.controller.exit()
                self.events()
                self.assertIs(self.workspace.scroll.widget(), container)
                self.assertEqual(tuple(self.workspace.visible_panes()), panes)

    def test_clicking_another_graph_changes_live_values_without_hiding_other_panes(self):
        self.controller.enter()
        self.events()
        self.assertEqual(self.controller.pane_selector.currentIndex(), 1)
        self.assertEqual(self.controller.readout.item(0, 1).text(), 'Pa')
        first = self.workspace.panes[0]
        self.workspace.set_active(first)
        self.events()
        self.assertIs(self.controller.pane, first)
        self.assertEqual(self.controller.pane_selector.currentIndex(), 0)
        self.assertEqual(self.controller.readout.item(0, 1).text(), '°C')
        self.controller.pane_selector.setCurrentIndex(1)
        self.events()
        second = self.workspace.panes[1]
        self.assertIs(self.workspace.active, second)
        second.lock_cursor(0, self.second.id)
        second.cursor_locks[0]['index'] = 1
        second.restore_ranges(second.state())
        self.events()
        self.assertEqual(float(self.controller.readout.item(0, 2).text()), 200)
        second.step_cursor(0, 1)
        self.events()
        self.assertEqual(float(self.controller.readout.item(0, 2).text()), 300)
        self.assertIn('300 Pa', self.controller.cursor_cards[0].toolTip())
        self.assertTrue(all(pane.isVisible() for pane in self.workspace.visible_panes()))

    def test_shared_zoom_modes_and_time_lock_work_on_expanded_layout(self):
        self.controller.enter()
        self.events()
        for key in ('x', 'y', 'xy', 'pan', 'in', 'out', 'reset'):
            self.assertIn(self.workspace.navigation_actions[key], self.controller.navigation_bar.actions())
        self.workspace.navigation_actions['x'].trigger()
        self.assertTrue(all(tuple(p.getViewBox().state['mouseEnabled']) == (True, False)
                            for p in self.workspace.visible_panes()))
        before = [deepcopy(p.getViewBox().viewRange()) for p in self.workspace.visible_panes()]
        self.workspace.navigation_actions['in'].trigger()
        self.events()
        ranges = [pane.getViewBox().viewRange() for pane in self.workspace.visible_panes()]
        np.testing.assert_allclose(ranges[0][0], ranges[1][0], rtol=0, atol=1e-9)
        self.assertLess(np.ptp(ranges[0][0]), np.ptp(before[0][0]))
        for index in range(2):
            np.testing.assert_allclose(ranges[index][1], before[index][1], rtol=0, atol=1e-7)
        self.workspace.navigation_actions['y'].trigger()
        self.assertTrue(all(tuple(p.getViewBox().state['mouseEnabled']) == (False, True)
                            for p in self.workspace.visible_panes()))

    def test_workspace_entry_returns_selected_graph_before_expanding_all_panes(self):
        panes = tuple(self.workspace.visible_panes())
        selected = self.window.graph_fullscreen
        selected.enter(panes[0])
        self.events()
        self.assertTrue(selected.is_active)
        self.assertIs(panes[0].parentWidget(), selected.graph_scroll.viewport())
        self.controller.enter(self.workspace)
        self.events()
        self.assertFalse(selected.is_active)
        self.assertFalse(selected.fullscreen_window.isVisible())
        self.assertTrue(self.controller.is_active)
        self.assertEqual(set(self.controller.fullscreen_window.findChildren(PlotPane)), set(panes))
        for pane in panes:
            self.assertIs(pane.parentWidget(), self.workspace.container)
        self.assertTrue(all(pane.isVisible() for pane in panes))

    def test_escape_restores_docks_geometry_container_and_keeps_deliberate_navigation(self):
        container = self.workspace.container
        state, geometry = self.window.saveState(), self.window.saveGeometry()
        self.controller.enter()
        self.events()
        pane = self.workspace.panes[0]
        self.workspace.set_active(pane)
        pane.setXRange(.75, 2.25, padding=0)
        self.events()
        QtTest.QTest.keyClick(pane, QtCore.Qt.Key.Key_Escape)
        self.events()
        self.assertFalse(self.controller.is_active)
        self.assertFalse(self.controller.fullscreen_window.isVisible())
        self.assertIs(self.workspace.scroll.widget(), container)
        self.assertEqual(self.window.saveState(), state)
        self.assertEqual(self.window.saveGeometry(), geometry)
        self.assertIs(self.workspace.active, pane)
        for current in self.workspace.visible_panes():
            np.testing.assert_allclose(current.getViewBox().viewRange()[0], [.75, 2.25], rtol=0, atol=1e-7)
        self.assertFalse(self.controller.action.isChecked())

    def test_direct_layout_change_safely_returns_the_same_container(self):
        container = self.workspace.container
        self.controller.enter()
        self.events()
        self.workspace.set_layout('2×2')
        self.events()
        self.assertFalse(self.controller.is_active)
        self.assertIs(self.workspace.scroll.widget(), container)
        self.assertEqual(self.workspace.layout_name, '2×2')
        self.assertEqual(len(self.workspace.visible_panes()), 4)
        self.assertTrue(all(pane.isVisible() for pane in self.workspace.visible_panes()))

    def test_nontemporal_and_empty_panes_keep_their_own_readouts(self):
        frequency = self.window.store.add(Channel('FFT amplitude', [1, 2, 3], [4, 5, 6],
            unit='W', coordinate_kind='frequency', coordinate_unit='Hz'))
        self.workspace.panes[0].bind([frequency.id])
        self.workspace.panes[1].bind([])
        self.controller.enter()
        self.events()
        self.assertEqual(self.controller.readout.rowCount(), 0)
        self.assertIn('No channels selected', self.controller.pane_selector.currentText())
        self.controller.pane_selector.setCurrentIndex(0)
        self.events()
        self.assertEqual(self.controller.readout.rowCount(), 1)
        self.assertIn('Hz', self.controller.interval_caption.text())
        self.assertIn('Δ X', self.controller.interval_caption.text())

    def test_repeated_sessions_preserve_shared_actions_and_original_source_arrays(self):
        arrays = {c.id: (c.x, c.y) for c in self.window.store.channels.values()}
        for _ in range(3):
            self.controller.enter()
            self.events()
            self.controller.exit()
            self.events()
        for action in self.workspace.navigation_actions.values():
            self.assertTrue(isValid(action))
        self.workspace.navigation_actions['reset'].trigger()
        for channel_id, (x, y) in arrays.items():
            self.assertIs(self.window.store.channels[channel_id].x, x)
            self.assertIs(self.window.store.channels[channel_id].y, y)
        self.assertTrue(isValid(self.window.graph_fullscreen.action))

    def test_main_window_close_returns_container_before_delete(self):
        container = self.workspace.container
        self.controller.enter()
        self.events()
        self.window.close()
        self.events()
        self.assertFalse(self.controller.is_active)
        self.assertIs(self.workspace.scroll.widget(), container)
        self.assertFalse(self.controller.fullscreen_window.isVisible())

    def test_large_layout_retains_readable_panes_and_original_scroll_position(self):
        self.workspace.set_layout('10 panels')
        self.events()
        scroll = self.workspace.scroll
        self.assertGreater(scroll.verticalScrollBar().maximum(), 500)
        scroll.verticalScrollBar().setValue(500)
        self.controller.enter()
        self.events()
        self.assertEqual(len(self.controller.fullscreen_window.findChildren(PlotPane)), 10)
        self.assertTrue(all(pane.minimumHeight() >= 230 for pane in self.workspace.visible_panes()))
        self.assertGreater(self.controller.graph_scroll.verticalScrollBar().maximum(), 0)
        self.controller.exit()
        self.events()
        self.assertEqual(scroll.verticalScrollBar().value(), 500)

    def test_hover_between_graphs_and_clear_keeps_every_plot_geometry_stable(self):
        self.controller.enter()
        self.events()
        panes = self.workspace.visible_panes()
        original = [QtCore.QRect(pane.viewport().mapToGlobal(QtCore.QPoint()), pane.viewport().size()) for pane in panes]
        ranges = [deepcopy(pane.getViewBox().viewRange()) for pane in panes]
        active = self.workspace.active
        for index in (0, 1, 0):
            pane = panes[index]
            bounds = pane.getViewBox().sceneBoundingRect()
            point = bounds.topLeft()+QtCore.QPointF(bounds.width()*.4, bounds.height()*.45)
            QtTest.QTest.mouseMove(pane.viewport(), pane.mapFromScene(point))
            # Synthetic viewport moves need not generate QGraphicsScene motion
            # on the offscreen platform. Feed the same scene input into the
            # production coalescer, which still validates actual QCursor/widget
            # ownership instead of trusting this saved point.
            pane.scene().sigMouseMoved.emit(point)
            self.events()
            self.assertIsNotNone(pane.hover_state, 'graph '+str(index+1)+' viewport='+str(pane.viewport().geometry())+
                ' scroll='+str(self.controller.graph_scroll.verticalScrollBar().value())+
                ' global='+str(pane.viewport().mapToGlobal(pane.mapFromScene(point))))
            self.assertIn('Graph '+str(index+1), self.controller.hover_readout.text())
            self.assertEqual(len(self.controller.hover_readout.text().splitlines()), 2)
            self.assertIs(self.workspace.active, active)
            for number, current in enumerate(panes):
                self.assertEqual(QtCore.QRect(current.viewport().mapToGlobal(QtCore.QPoint()), current.viewport().size()), original[number])
                np.testing.assert_allclose(current.getViewBox().viewRange(), ranges[number], rtol=0, atol=1e-9)
            QtTest.QTest.mouseMove(self.controller.exit_button, self.controller.exit_button.rect().center())
            pane.scene().sigMouseMoved.emit(point)
            self.events()
            self.assertEqual(len(self.controller.hover_readout.text().splitlines()), 1)
            self.assertIs(self.workspace.active, active)

    def test_actual_window_deletion_leaves_no_orphan_fullscreen_host(self):
        self.window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        host = self.controller.enter()
        self.events()
        self.window.close()
        self.events()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(self.window))
        self.assertFalse(isValid(host))

    def test_reentry_does_not_reuse_a_previous_session_hover_reading(self):
        self.controller.enter()
        self.events()
        pane = self.workspace.panes[0]
        bounds = pane.getViewBox().sceneBoundingRect()
        point = bounds.center()
        QtTest.QTest.mouseMove(pane.viewport(), pane.mapFromScene(point))
        pane.scene().sigMouseMoved.emit(point)
        self.events()
        self.assertIsNotNone(pane.hover_state)
        self.assertIn('Graph 1', self.controller.hover_readout.text())
        self.controller.exit()
        QtTest.QTest.mouseMove(self.window.menuBar(), self.window.menuBar().rect().center())
        self.events()
        self.controller.enter()
        self.events()
        self.assertEqual(self.controller.hover_readout.text(),
                         'Mouse X/Y · Move over a graph to inspect values')

