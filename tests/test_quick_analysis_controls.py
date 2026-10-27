"""Exercise the user-facing routes shared by every delivery form."""
from copy import deepcopy
import gc
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtWidgets
from shiboken6 import isValid

from app_channel_store import Channel, ChannelStore, Dataset
from app_workbench import AdvancedStudioWindow


class QuickAnalysisControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.action_errors = []
        warnings = patch.object(QtWidgets.QMessageBox, 'warning',
                                side_effect=lambda parent, title, text, *args: self.action_errors.append((title, text)))
        warnings.start()
        self.addCleanup(warnings.stop)
        self.window = AdvancedStudioWindow()
        self.window.resize(1400, 900)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.assertEqual(self.action_errors, [])

    def channels(self):
        store = ChannelStore()
        ids = []
        for name, source in [('File A', 'a.csv'), ('File B', 'b.csv')]:
            dataset = Dataset(name, pd.DataFrame({'Time': [0, 1, 2, 3]}), source)
            store.datasets[dataset.id] = dataset
            channel = Channel('Water Pressure', np.arange(4.), np.arange(4.) + len(ids),
                              'Pa', coordinate_unit='min', dataset_id=dataset.id, source=source)
            store.add(channel)
            ids.append(channel.id)
        self.window.merge_store(store)
        self.app.processEvents()
        return ids

    def test_channel_menu_survives_collection_and_direct_controls_are_reachable(self):
        w = self.window
        gc.collect()
        self.app.processEvents()
        self.assertTrue(isValid(w.channel_menu))
        self.assertIs(w.compact.channel_source_menu, w.channel_menu)
        self.assertIn('Change Trace Color…', [a.text() for a in w.channel_menu.actions()])
        self.assertIn('Rename Channel', [a.text() for a in w.channel_menu.actions()])
        self.assertIn(w.compare_data_action, w.main_toolbar.actions())
        self.assertIn(w.graph_fullscreen.action, w.view_menu.actions())
        self.assertTrue(all(w.graph_fullscreen.action in p.navigation_bar.actions() for p in w.workspaces))
        self.assertTrue(any(w.main_toolbar.widgetForAction(a) is w.panel_folding.button
                            for a in w.main_toolbar.actions()))
        self.assertTrue(w.panel_folding.button.isVisible())
        expand=w.dashboard.navigation_bar.widgetForAction(w.graph_fullscreen.action)
        self.assertTrue(expand.isVisible())
        header_actions=w.dashboard.navigation_bar.actions()
        self.assertLess(header_actions.index(w.graph_fullscreen.action),
                        header_actions.index(w.dashboard.time_lock_action))
        self.assertFalse(w.graph_fullscreen.action.icon().isNull())
        previous_theme=w.theme.mode
        for theme,dark in [('Dark',True),('Light',False)]:
            w.theme.apply(theme)
            icon=w.graph_fullscreen.action.icon().pixmap(24,24).toImage()
            strokes=[icon.pixelColor(x,y).lightness() for y in range(24) for x in range(24)
                     if icon.pixelColor(x,y).alpha()>150]
            self.assertTrue(strokes)
            self.assertGreater(max(strokes),160) if dark else self.assertLess(min(strokes),100)
        w.theme.apply(previous_theme)
        expected = {'Properties', 'Channel Math', 'Channel Table', 'Interval Measurements'}
        self.assertEqual({name for name, dock in w.docks.items() if dock.isHidden()}, expected)
        self.assertFalse(w.docks['Engineering Controls'].isHidden())
        self.assertFalse(w.docks['Readout'].isHidden())

    def test_portal_color_and_comparison_use_the_clicked_source_identity(self):
        w = self.window
        first, second = self.channels()
        w.show_dock('Data Portal')
        self.app.processEvents()
        iterator = QtWidgets.QTreeWidgetItemIterator(w.portal.tree)
        items = {}
        while iterator.value():
            item = iterator.value()
            identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if identity:
                items[identity] = item
            iterator += 1
        items[first].setSelected(True)
        position = w.portal.tree.visualItemRect(items[second]).center()
        def trigger(label):
            class SourceMenu(QtWidgets.QMenu):
                def exec(self, *_args):
                    next(action for action in self.actions() if action.text() == label).trigger()
            return SourceMenu
        with patch.object(w.trace_colors, 'choose') as color, \
                patch.object(QtWidgets, 'QMenu', trigger('Change Trace Color…')):
            w.portal.context_menu(position)
            color.assert_called_once_with([second])
        with patch.object(w.data_comparison, 'add_channels') as compare, \
                patch.object(QtWidgets, 'QMenu', trigger('Add Selected Channels to Comparison')):
            w.portal.context_menu(position)
            compare.assert_called_once_with([second])

    def test_chart_actions_scope_color_and_fullscreen_to_the_clicked_pane(self):
        w = self.window
        first, second = self.channels()
        w.dashboard.set_layout('Vertical split')
        pane = w.dashboard.panes[1]
        pane.bind([second])
        menu = pane.create_context_menu()
        colors = next(action.menu() for action in menu.actions() if action.text() == 'Change Trace Color')
        with patch.object(w.trace_colors, 'choose') as choose:
            colors.actions()[0].trigger()
            choose.assert_called_once_with([second])
        with patch.object(w.graph_fullscreen, 'enter') as expand:
            next(action for action in menu.actions() if action.text() == 'Full Screen Graph').trigger()
            expand.assert_called_once_with(pane)
        self.assertIs(w.dashboard.active, pane)
        self.assertIn(first, w.store.channels)

    def test_normal_open_still_plots_but_comparison_import_leaves_selection_to_the_user(self):
        w = self.window
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recording.csv'
            path.write_text('Time (s),Power (W)\n0,1\n60,2\n120,3\n')
            with patch.object(QtWidgets.QFileDialog, 'getOpenFileNames', return_value=([str(path)], '')):
                self.assertTrue(w.open_data())
            deadline = time.monotonic() + 10
            while (w.busy or w.workers) and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.005)
            self.assertFalse(w.busy)
            self.assertEqual({id for pane in w.dashboard.visible_panes() for id in pane.ids}, set(w.store.channels))
            before = deepcopy(w.dashboard.state())
            extra = ChannelStore()
            extra.add(Channel('Not selected yet', np.arange(3.), np.arange(3.), 'Pa', coordinate_unit='min'))
            w.studio.pending_preset = {'signals': {}}
            with patch.object(w.studio, 'apply_preset') as apply:
                w.finish_import(extra, w.comparison, plot_import=False)
                apply.assert_not_called()
            self.assertEqual(w.dashboard.state(), before)
            self.assertFalse(any(pane.ids for pane in w.comparison.panes))
            self.assertTrue(set(extra.channels).issubset(w.store.channels))

    def test_restore_exits_fullscreen_before_replacing_the_workspace(self):
        w = self.window
        self.channels()
        views = deepcopy([workspace.state() for workspace in w.workspaces])
        ui = w.ui_state()
        pane = w.dashboard.active
        w.graph_fullscreen.enter(pane)
        self.app.processEvents()
        self.assertTrue(w.graph_fullscreen.is_active)
        w.restore_loaded(w.store, views, ui)
        self.app.processEvents()
        self.assertFalse(w.graph_fullscreen.is_active)
        self.assertFalse(w.graph_fullscreen.fullscreen_window.isVisible())
        self.assertTrue(w.dashboard.active.ids)
        self.assertFalse(w.docks['Readout'].isHidden())

    def test_long_interval_details_scroll_without_expanding_the_value_dock(self):
        w = self.window
        w.interval_card.setText('<br>'.join('Detailed interval statistic '+str(i) for i in range(18)))
        w.resizeDocks([w.docks['Readout']], [180], QtCore.Qt.Orientation.Vertical)
        for _ in range(4):
            self.app.processEvents()
        scroll = w.interval_scroll
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
        self.assertGreaterEqual(w.interval_card.height(), w.interval_card.heightForWidth(w.interval_card.width()))
        self.assertLess(w.docks['Readout'].height(), 260)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        self.assertGreater(scroll.verticalScrollBar().value(), 0)


if __name__ == '__main__':
    unittest.main()
