"""Selected graph fullscreen retains real pane identity and usable live tools."""
import os
from pathlib import Path
import sys
import tempfile
import traceback
import unittest
from unittest.mock import patch

import numpy as np
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from shiboken6 import isValid

from app_channel_store import Channel, Dataset
from app_graph_fullscreen import GraphFullscreenController
from app_plot_workspace import PlotPane
from app_workbench import AdvancedStudioWindow
import pandas as pd


class GraphFullscreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        environment = patch.dict(os.environ, {'ANALIZER_SETTINGS_DIR': str(root/'settings'),
            'ANALIZER_OUTPUT_DIR': str(root/'outputs'), 'MPLCONFIGDIR': str(root/'matplotlib'),
            'XDG_CACHE_HOME': str(root/'cache')})
        environment.start()
        self.addCleanup(environment.stop)
        self.callback_errors = []
        exceptions = patch.object(sys, 'excepthook', lambda kind, value, tb:
            self.callback_errors.append(''.join(traceback.format_exception(kind, value, tb))))
        exceptions.start()
        self.addCleanup(exceptions.stop)
        self.window = AdvancedStudioWindow()
        # Keep post-close state inspectable in most tests. A separate case below
        # exercises the real DeleteOnClose lifecycle and checks orphan cleanup.
        self.window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.window.resize(1280, 900)
        self.window.show()
        self.controller = getattr(self.window, 'graph_fullscreen', None) or GraphFullscreenController(self.window)
        self.window.graph_fullscreen = self.controller
        dataset = Dataset('Recorded run', pd.DataFrame({'x': [0., 1., 1., 2., 3.]}))
        self.window.store.datasets[dataset.id] = dataset
        self.temperature = self.window.store.add(Channel('Temperature', [0, 1, 1, 2, 3], [10, 20, 30, 40, 50],
            unit='°C', coordinate_unit='min', dataset_id=dataset.id, attributes={'match_percent': 93}))
        self.pressure = self.window.store.add(Channel('Pressure', [0, 1, 1, 2, 3], [100, 200, 300, 400, 500],
            unit='Pa', coordinate_unit='min', dataset_id=dataset.id))
        self.workspace = self.window.dashboard
        self.workspace.set_layout('3 stacked')
        for pane in self.workspace.visible_panes():
            pane.bind([self.temperature.id, self.pressure.id])
        self.pane = self.workspace.panes[1]
        self.workspace.set_active(self.pane)
        self.pane.setXRange(.5, 2.5, padding=0)
        self.pane.cursor_lines[0].setValue(1)
        self.pane.cursor_lines[1].setValue(2)
        self.events()

    def events(self):
        for _ in range(3):
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

    def row(self, channel):
        return next(row for row in range(self.controller.readout.rowCount())
            if self.controller.readout.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole) == channel.id)

    def test_detaches_only_selected_real_pane_and_reuses_shared_navigation(self):
        pane, parent = self.pane, self.pane.parentWidget()
        curves = dict(pane.curves)
        originals = {channel.id: (channel.x, channel.y) for channel in self.window.store.channels.values()}
        original_range = np.array(pane.getViewBox().viewRange())
        host = self.controller.enter(pane)
        self.events()
        self.assertTrue(host.isFullScreen())
        self.assertIs(self.controller.pane, pane)
        self.assertEqual(host.findChildren(PlotPane), [pane])
        self.assertIsNot(pane.parentWidget(), parent)
        self.assertEqual(self.workspace.panes[1], pane)
        self.assertEqual(pane.curves, curves)
        np.testing.assert_allclose(pane.getViewBox().viewRange(), original_range, rtol=0, atol=1e-7)
        for channel_id, (x, y) in originals.items():
            self.assertIs(self.window.store.channels[channel_id].x, x)
            self.assertIs(self.window.store.channels[channel_id].y, y)
        for key in ('x', 'y', 'xy', 'pan', 'in', 'out', 'reset'):
            self.assertIn(self.workspace.navigation_actions[key], self.controller.navigation_bar.actions())
        self.assertIn('Ctrl+L', [action.shortcut().toString() for action in host.actions()])
        self.workspace.navigation_actions['y'].trigger()
        self.assertEqual(self.workspace.navigation_mode, 'y')
        self.assertEqual(list(pane.getViewBox().state['mouseEnabled']), [False, True])
        before_x = list(pane.getViewBox().viewRange()[0])
        self.workspace.navigation_actions['in'].trigger()
        self.events()
        np.testing.assert_allclose(pane.getViewBox().viewRange()[0], before_x, rtol=0, atol=1e-7)
        self.assertTrue(self.controller.exit_button.isVisible())
        self.assertTrue(self.controller.readout.isVisible())

    def test_pointer_hover_and_clear_keep_fullscreen_graph_geometry_stable(self):
        self.controller.enter(self.pane)
        self.workspace.navigate('x')
        self.events()
        label = self.controller.hover_readout
        for larger_font in (False, True):
            with self.subTest(larger_font=larger_font):
                if larger_font:
                    font = label.font()
                    font.setPointSizeF(font.pointSizeF()+4)
                    label.setFont(font)
                    self.events()
                # The whole two-line reading fits at the effective font/DPI;
                # text contents never participate in the allocated row height.
                metrics = label.fontMetrics()
                self.assertEqual(label.minimumHeight(), label.maximumHeight())
                self.assertGreaterEqual(label.contentsRect().height(), metrics.height()+metrics.lineSpacing())
                viewport = self.pane.viewport()
                original_geometry = QtCore.QRect(viewport.mapToGlobal(QtCore.QPoint()), viewport.size())
                original_ranges = np.array(self.pane.getViewBox().viewRange())
                original_split = self.controller.splitter.sizes()
                for fraction in (.2, .65, .35):
                    rectangle = self.pane.getViewBox().sceneBoundingRect()
                    point = rectangle.topLeft()+QtCore.QPointF(rectangle.width()*fraction, rectangle.height()*.45)
                    QtTest.QTest.mouseMove(viewport, self.pane.mapFromScene(point))
                    # Offscreen Qt does not always emit QGraphicsScene motion
                    # for a synthetic viewport move. Deliver that same scene
                    # input to the real coalescer; it resolves actual QCursor
                    # position/widget ownership rather than trusting this point.
                    self.pane.scene().sigMouseMoved.emit(point)
                    self.events()
                    self.assertIsNotNone(self.pane.hover_state,
                        f'pointer={QtWidgets.QApplication.widgetAt(viewport.mapToGlobal(self.pane.mapFromScene(point)))} '
                        f'viewport={viewport} position={viewport.mapToGlobal(self.pane.mapFromScene(point))} cursor={QtGui.QCursor.pos()}')
                    self.assertEqual(len(label.text().splitlines()), 2)
                    self.assertIn('Mouse X', label.text())
                    self.assertEqual(QtCore.QRect(viewport.mapToGlobal(QtCore.QPoint()), viewport.size()), original_geometry)
                    self.assertEqual(self.controller.splitter.sizes(), original_split)
                    np.testing.assert_allclose(self.pane.getViewBox().viewRange(), original_ranges, rtol=0, atol=1e-9)
                    QtTest.QTest.mouseMove(self.controller.exit_button, self.controller.exit_button.rect().center())
                    self.pane.scene().sigMouseMoved.emit(point)
                    self.events()
                    self.assertIsNone(self.pane.hover_state)
                    self.assertEqual(len(label.text().splitlines()), 1)
                    self.assertEqual(QtCore.QRect(viewport.mapToGlobal(QtCore.QPoint()), viewport.size()), original_geometry)
                    self.assertEqual(self.controller.splitter.sizes(), original_split)
                    np.testing.assert_allclose(self.pane.getViewBox().viewRange(), original_ranges, rtol=0, atol=1e-9)

    def test_live_duplicate_locked_source_values_units_statistics_and_colors(self):
        self.pane.lock_cursor(0, self.pressure.id)
        self.pane.cursor_locks[0]['index'] = 1
        self.pane.restore_ranges(self.pane.state())
        self.controller.enter(self.pane)
        self.events()
        row = self.row(self.pressure)
        self.assertEqual(self.controller.readout.item(row, 1).text(), 'Pa')
        self.assertEqual(float(self.controller.readout.item(row, 2).text()), 200)
        self.assertIn('200 Pa', self.controller.cursor_cards[0].toolTip())
        self.assertIn('Pressure', self.controller.cursor_cards[0].toolTip())
        self.pane.step_cursor(0, 1)
        self.events()
        self.assertEqual(self.pane.cursor_locks[0]['index'], 2)
        self.assertEqual(float(self.controller.readout.item(row, 2).text()), 300)
        self.assertIn('300 Pa', self.controller.cursor_cards[0].toolTip())
        self.assertIn('sample 2', self.controller.cursor_cards[0].toolTip())
        self.assertIn('Δ time', self.controller.interval_caption.text())
        self.assertIn('min', self.controller.interval_caption.text().splitlines()[0])
        self.assertEqual(self.controller.readout.item(row, 2).foreground().color().name().upper(), '#00D2FF')
        self.assertEqual(self.controller.readout.item(row, 3).foreground().color().name().upper(), '#FF9F1C')
        match_row = self.row(self.temperature)
        self.assertEqual(self.controller.readout.item(match_row, 9).text(), '93.0%')
        self.assertNotEqual(self.controller.readout.item(match_row, 9).background().style(), QtCore.Qt.BrushStyle.NoBrush)
        self.assertTrue(self.controller.readout.item(row, 5).text())

    def test_initial_values_fit_final_fullscreen_geometry_and_splitter_stays_resizable(self):
        actuator = self.window.store.add(Channel('Inlet valve', [0, 1, 1, 2, 3], [0, 1, 1, 0, 0],
            unit='state', kind='discrete', coordinate_unit='min', dataset_id=self.pressure.dataset_id,
            attributes={'actuator_binary': True}))
        self.pane.bind([self.temperature.id, self.pressure.id, actuator.id])
        self.events()
        self.controller._build_window()
        table = self.controller.readout
        for native_chrome in (False, True):
            with self.subTest(native_chrome=native_chrome):
                if native_chrome:
                    # Exercise real Qt viewport overhead beyond header/frame
                    # estimates: styled padding and an overflowing value table.
                    table.setStyleSheet('QTableWidget { border: 3px solid #536b84; padding: 4px; }')
                    screen_width = self.controller.fullscreen_window.screen().geometry().width()
                    table.horizontalHeader().setMinimumSectionSize(max(150, screen_width // 2))
                host = self.controller.enter(self.pane)
                self.events()
                self.assertTrue(host.isFullScreen())
                rows_height = sum(table.rowHeight(row) for row in range(table.rowCount()))
                self.assertEqual(table.verticalScrollBar().maximum(), 0)
                if native_chrome:
                    self.assertTrue(table.horizontalScrollBar().isVisible())
                # A short source list should leave at most one spare row, even
                # when native fullscreen resize/header layout arrives late.
                self.assertLessEqual(table.viewport().height(), rows_height + table.verticalHeader().defaultSectionSize())
                splitter = self.controller.splitter
                initial = splitter.sizes()
                splitter.moveSplitter(initial[0] - 60, 1)
                self.events()
                resized = splitter.sizes()
                self.assertGreater(resized[1], initial[1] + 40)
                self.pane.cursor_lines[1].setValue(2.25 if native_chrome else 2.5)
                self.events()
                self.assertEqual(splitter.sizes(), resized)
                self.controller.exit()
                self.events()

    def test_non_temporal_interval_caption_reports_coordinate_distance(self):
        for coordinate_kind, coordinate_unit in [('frequency', 'Hz'), ('sample', 'sample')]:
            with self.subTest(coordinate_kind=coordinate_kind):
                channel = self.window.store.add(Channel('Coordinate example', [0, 1, 2], [10, 20, 30],
                    coordinate_kind=coordinate_kind, coordinate_unit=coordinate_unit,
                    dataset_id=self.pressure.dataset_id))
                self.pane.bind([channel.id])
                self.controller.enter(self.pane)
                self.events()
                caption = self.controller.interval_caption.text().splitlines()[0]
                self.assertTrue(caption.startswith('Δ X '), caption)
                self.assertIn(coordinate_unit, caption)
                self.controller.exit()
                self.events()

    def test_escape_restores_original_grid_focus_docks_and_keeps_navigation_changes(self):
        parent = self.pane.parentWidget()
        position = self.workspace.grid.getItemPosition(self.workspace.grid.indexOf(self.pane))
        self.window.portal.search.setFocus()
        self.events()
        state, geometry = self.window.saveState(), self.window.saveGeometry()
        self.controller.enter(self.pane)
        self.pane.setXRange(1, 2, padding=0)
        self.events()
        QtTest.QTest.keyClick(self.pane, QtCore.Qt.Key.Key_Escape)
        self.events()
        self.assertFalse(self.controller.is_active)
        self.assertFalse(self.controller.fullscreen_window.isVisible())
        self.assertIs(self.pane.parentWidget(), parent)
        self.assertEqual(self.workspace.grid.getItemPosition(self.workspace.grid.indexOf(self.pane)), position)
        self.assertEqual(self.window.saveState(), state)
        self.assertEqual(self.window.saveGeometry(), geometry)
        self.assertIs(self.app.focusWidget(), self.window.portal.search)
        np.testing.assert_allclose(self.pane.getViewBox().viewRange()[0], [1, 2], rtol=0, atol=1e-7)
        self.assertFalse(self.controller.action.isChecked())
        self.assertFalse(self.workspace._canvas_alignment_timer.signalsBlocked())

    def test_repeated_action_host_close_maximized_restore_and_empty_graph(self):
        self.window.showMaximized()
        self.events()
        normal = self.window.normalGeometry()
        state = self.window.saveState()
        for attempt in range(3):
            self.controller.action.trigger()
            self.events()
            self.assertTrue(self.controller.is_active)
            if attempt == 0:
                QtTest.QTest.keyClick(self.pane, QtCore.Qt.Key.Key_F11)
            else:
                self.controller.fullscreen_window.close()
            self.events()
            self.assertFalse(self.controller.is_active)
            self.assertTrue(self.window.isMaximized())
            self.assertEqual(self.window.normalGeometry(), normal)
            self.assertEqual(self.window.saveState(), state)
            self.assertTrue(all(isValid(action) for action in self.workspace.navigation_actions.values()))
        self.pane.bind([])
        self.controller.enter(self.pane)
        self.events()
        self.assertEqual(self.controller.readout.rowCount(), 0)
        self.assertIn('No channels selected', self.controller.readout.accessibleDescription())
        self.controller.exit_action.trigger()
        self.events()
        self.assertFalse(self.controller.is_active)

    def test_main_window_close_returns_pane_without_altering_existing_focus_graph(self):
        self.window.compact.focus_action.setChecked(True)
        self.events()
        saved_focus = QtCore.QByteArray(self.window.compact.focus_state)
        self.controller.enter(self.pane)
        self.events()
        self.window.close()
        self.events()
        self.assertFalse(self.controller.is_active)
        self.assertTrue(self.window.compact.focus_action.isChecked())
        self.assertEqual(self.window.compact.focus_state, saved_focus)
        self.assertIs(self.workspace.grid.itemAtPosition(1, 0).widget(), self.pane)

    def test_external_layout_change_and_dataset_removal_exit_without_reinserting_hidden_pane(self):
        original_parent = self.pane.parentWidget()
        self.controller.enter(self.pane)
        self.workspace.set_layout('Single')
        self.events()
        self.assertFalse(self.controller.is_active)
        self.assertIs(self.pane.parentWidget(), original_parent)
        self.assertTrue(self.pane.isHidden())
        self.assertEqual(self.workspace.grid.indexOf(self.pane), -1)
        self.assertIs(self.workspace.grid.itemAtPosition(0, 0).widget(), self.workspace.panes[0])
        self.controller.enter(self.workspace.panes[0])
        self.events()
        self.window.drop_recordings([self.temperature.dataset_id])
        self.events()
        self.assertFalse(self.controller.is_active)
        self.assertFalse(self.controller.fullscreen_window.isVisible())
        self.assertNotIn(self.temperature.id, self.window.store.channels)

    def test_real_mainwindow_delete_leaves_no_orphan_fullscreen_window(self):
        self.window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        host = self.controller.enter(self.pane)
        self.events()
        self.window.close()
        self.events()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(self.window))
        self.assertFalse(isValid(host))

    def test_workspace_restore_exits_before_replacing_detached_panes(self):
        from app_workspace_io import save_workspace
        path = save_workspace(Path(self.directory.name)/'saved.json', self.window.store,
            [workspace.state() for workspace in self.window.workspaces], self.window.ui_state())
        previous = self.pane
        self.controller.enter(previous)
        self.events()
        self.window.restore_path(path)
        self.events()
        self.assertFalse(self.controller.is_active)
        self.assertIsNone(self.controller.graph_scroll.widget())
        self.assertFalse(self.controller.fullscreen_window.isVisible())
        self.assertIsNot(self.workspace.panes[1], previous)
        self.assertEqual(self.workspace.panes[1].ids, [self.temperature.id, self.pressure.id])
        np.testing.assert_array_equal(self.window.store.channels[self.pressure.id].y, self.pressure.y)
        self.assertFalse(self.window.findChildren(QtWidgets.QWidget, 'fullscreenGraphPlaceholder'))


if __name__ == '__main__':
    unittest.main()
