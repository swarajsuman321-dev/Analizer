"""Direct colors preserve source identity, view state and exported appearance."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from app_actuators import interpret_channel
from app_channel_store import Channel, Dataset
from app_studio_state import channel_preset
from app_trace_colors import channel_colors
from app_trace_controls import TraceColorControls
from app_workbench import AdvancedStudioWindow
from app_workspace_io import load_workspace, render_report, save_workspace


class DirectTraceColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            'ANALIZER_OUTPUT_DIR': self.temp.name,
            'ANALIZER_SETTINGS_DIR': self.temp.name,
        })
        self.env.start()
        self.window = AdvancedStudioWindow()
        self.window.resize(1536, 960)
        self.window.show()
        self.controls = TraceColorControls(self.window)
        self.datasets = [Dataset('Run A.csv', pd.DataFrame(), 'Run A.csv'),
                         Dataset('Run B.csv', pd.DataFrame(), 'Run B.csv')]
        self.window.store.datasets.update({dataset.id: dataset for dataset in self.datasets})
        self.x = np.array([0., 1., 2., 2., 3., 4., 5.])
        self.a = self.add('Pressure', 'Pa', [0, 100, 200, 215, 300, 400, 500], self.datasets[0])
        self.b = self.add('Pressure', 'Pa', [10, 110, 210, 225, 310, 410, 510], self.datasets[1])
        self.temperature = self.add('Temperature', '°C', np.arange(7) + 20, self.datasets[0])
        self.inlet = self.add('Inlet Valve', 'state', [0, 1, 0, 1, 1, 0, 0], self.datasets[0], True)
        self.drain = self.add('Drain Valve', 'state', [1, 0, 1, 0, 0, 1, 0], self.datasets[0], True)
        workspace = self.window.dashboard
        workspace.set_layout('Vertical split')
        workspace.set_time_lock(False)
        workspace.panes[0].bind([self.a.id, self.temperature.id])
        workspace.panes[1].bind([self.b.id, self.inlet.id, self.drain.id])
        workspace.active = workspace.panes[1]
        self.window.comparison.assign([self.a.id, self.b.id])
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.env.stop()
        self.temp.cleanup()

    def add(self, name, unit, values, dataset, actuator=False):
        channel = Channel(name, self.x, values, unit=unit, coordinate_unit='min',
                          dataset_id=dataset.id, source=dataset.source)
        if actuator:
            channel = interpret_channel(channel, 'actuator')
        return self.window.store.add(channel)

    def all_panes(self):
        return [pane for workspace in self.window.workspaces for pane in workspace.panes]

    def view_snapshot(self):
        return [(deepcopy(pane.state()), deepcopy(pane.history), pane.history_index)
                for pane in self.all_panes()]

    def select(self, channel_id):
        tree = self.window.portal.tree
        tree.clearSelection()
        iterator = QtWidgets.QTreeWidgetItemIterator(tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, QtCore.Qt.ItemDataRole.UserRole) == channel_id:
                item.setSelected(True)
                break
            iterator += 1
        self.app.processEvents()

    def metadata_item(self, key):
        table = self.window.prop_metadata
        for row in range(table.rowCount()):
            if table.item(row, 0).text() == key:
                return table.item(row, 1)
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QtWidgets.QTableWidgetItem(key))
        table.setItem(row, 1, QtWidgets.QTableWidgetItem())
        return table.item(row, 1)

    def test_selected_color_updates_properties_and_survives_rename_apply(self):
        window = self.window
        self.select(self.a.id)
        with patch.object(window, 'selection', wraps=window.selection) as selection:
            self.controls.set_color([self.a.id], '#cc1144')
            selection.assert_not_called()
        self.assertEqual(window.structured_metadata()['plot_style']['color'], '#cc1144')
        self.assertEqual(json.loads(window.prop_attrs.toPlainText())['plot_style']['color'],
                         '#cc1144')
        window.prop_name.setText('Renamed Pressure')
        window.apply_properties()
        updated = window.store.channels[self.a.id]
        self.assertEqual(updated.name, 'Renamed Pressure')
        self.assertEqual(updated.attributes['plot_style']['color'], '#cc1144')
        self.assertEqual(window.dashboard.panes[0].curves[self.a.id][1].pen.color().name(),
                         '#cc1144')

    def test_color_refresh_preserves_unsaved_structured_fields_and_nested_style(self):
        window = self.window
        attributes = {**window.store.channels[self.a.id].attributes,
                      'plot_style': {'color': '#225588', 'width': 2},
                      'review': {'author': 'original', 'details': {'accepted': False}}}
        window.store.update(self.a.id, attributes=attributes)
        self.select(self.a.id)
        draft_style = {'color': '#225588', 'width': 4, 'marker': {'size': 7}}
        draft_review = {'author': 'reviewer', 'details': {'accepted': True, 'note': 'Keep me'}}
        self.metadata_item('plot_style').setText(json.dumps(draft_style))
        self.metadata_item('review').setText(json.dumps(draft_review))
        self.metadata_item('new_property').setText(json.dumps({'nested': [1, 2, 3]}))
        window.prop_name.setText('Draft Pressure')
        window.prop_unit.setText('kPa')
        window.prop_group.setText('Draft group')
        window.warning_max.setText('900')

        self.controls.set_color([self.a.id], '#cc1144')
        expected_style = {**draft_style, 'color': '#cc1144'}
        self.assertEqual(window.structured_metadata()['plot_style'], expected_style)
        self.assertEqual(window.structured_metadata()['review'], draft_review)
        self.assertEqual(window.prop_name.text(), 'Draft Pressure')
        self.assertEqual(window.prop_unit.text(), 'kPa')
        self.assertEqual(window.prop_group.text(), 'Draft group')
        self.assertEqual(window.warning_max.text(), '900')
        self.assertEqual(window.prop_attrs.toPlainText(), window._metadata_snapshot)
        window.apply_properties()
        updated = window.store.channels[self.a.id]
        self.assertEqual((updated.name, updated.unit, updated.group),
                         ('Draft Pressure', 'kPa', 'Draft group'))
        self.assertEqual(updated.attributes['plot_style'], expected_style)
        self.assertEqual(updated.attributes['review'], draft_review)
        self.assertEqual(updated.attributes['new_property'], {'nested': [1, 2, 3]})
        self.assertEqual(updated.attributes['warning_max'], 900)

    def test_color_refresh_preserves_advanced_json_draft_after_editor_toggle(self):
        window = self.window
        attributes = {**window.store.channels[self.a.id].attributes,
                      'plot_style': {'color': '#225588', 'width': 2}}
        window.store.update(self.a.id, attributes=attributes)
        self.select(self.a.id)
        self.metadata_item('plot_style').setText(json.dumps({'color': '#225588', 'width': 5}))
        window.metadata_advanced.setChecked(True)
        draft = json.loads(window.prop_attrs.toPlainText())
        draft['review'] = {'details': {'note': 'Draft ✓'}, 'tags': ['retain', 'nested']}
        draft['plot_style']['marker'] = {'size': 8}
        window.prop_attrs.setPlainText(json.dumps(draft, indent=2, ensure_ascii=False))
        window.prop_name.setText('Advanced draft')
        self.controls.set_color([self.a.id], '#cc1144')
        draft['plot_style']['color'] = '#cc1144'
        self.assertEqual(json.loads(window.prop_attrs.toPlainText()), draft)
        self.assertEqual(window.prop_name.text(), 'Advanced draft')
        window.apply_properties()
        updated = window.store.channels[self.a.id]
        self.assertEqual(updated.name, 'Advanced draft')
        self.assertEqual(updated.attributes['plot_style'], draft['plot_style'])
        self.assertEqual(updated.attributes['review'], draft['review'])

    def test_invalid_advanced_json_is_preserved_and_repair_keeps_latest_color(self):
        window = self.window
        attributes = {**window.store.channels[self.a.id].attributes,
                      'plot_style': {'color': '#225588', 'width': 2}}
        window.store.update(self.a.id, attributes=attributes)
        self.select(self.a.id)
        window.metadata_advanced.setChecked(True)
        original = window.prop_attrs.toPlainText()
        invalid = original + '\nunfinished draft'
        window.prop_attrs.setPlainText(invalid)
        window.prop_name.setText('Repaired draft')
        self.controls.set_color([self.a.id], '#cc1144')
        self.assertEqual(window.prop_attrs.toPlainText(), invalid)
        self.assertEqual(window.prop_name.text(), 'Repaired draft')
        self.assertEqual(window.structured_metadata()['plot_style']['color'], '#cc1144')
        # Repairing an old draft must retain an external color edit even though
        # its original color text was never replaced while JSON was invalid.
        repaired = json.loads(original)
        repaired['plot_style']['width'] = 6
        window.prop_attrs.setPlainText(json.dumps(repaired))
        window.apply_properties()
        updated = window.store.channels[self.a.id]
        self.assertEqual(updated.name, 'Repaired draft')
        self.assertEqual(updated.attributes['plot_style'], {'color': '#cc1144', 'width': 6})

    def test_color_for_unselected_channel_leaves_properties_draft_untouched(self):
        window = self.window
        self.select(self.b.id)
        window.prop_name.setText('Other channel draft')
        window.metadata_advanced.setChecked(True)
        window.prop_attrs.setPlainText('{"notes": {"draft": true}}')
        def editor_state():
            return (window.prop_name.text(), window.prop_attrs.toPlainText(),
                    window.structured_metadata(), window._metadata_snapshot)
        before = editor_state()
        self.controls.set_color([self.a.id], '#cc1144')
        self.assertEqual(editor_state(), before)
        window.portal.tree.clearSelection()
        self.assertEqual(window.portal.selected(), [])
        self.controls.set_color([self.b.id], '#4499cc')
        self.assertEqual(editor_state(), before)

    def test_color_edit_retains_layout_ranges_duplicate_sample_locks_and_history(self):
        window = self.window
        workspace = window.dashboard
        pane = workspace.panes[0]
        # A saved style limit differs from the current user zoom: a color edit
        # must keep the zoom instead of resetting to the preset's limits.
        attrs = {**window.store.channels[self.a.id].attributes,
                 'plot_style': {'color': '#225588', 'ymin': 0, 'ymax': 900, 'width': 2}}
        window.store.update(self.a.id, attributes=attrs)
        pane.setXRange(1, 4, padding=0)
        pane.setYRange(120, 350, padding=0)
        pane.axes['°C'][1].setYRange(20.5, 25.5, padding=0)
        workspace.panes[1].setXRange(2, 5, padding=0)
        workspace.panes[1].axes['Actuators'][1].setYRange(-.2, 1.2, padding=0)
        pane.cursor_lines[0].setValue(2)
        pane.lock_cursor(0, self.a.id)
        pane.cursor_locks[0]['index'] = 2
        pane.restore_ranges(pane.state())
        pane.cursor_lines[1].setValue(3)
        pane.annotate('Marker', 2.5, text='Reviewed event')
        pane.remember_view()
        self.app.processEvents()
        before = self.view_snapshot()
        layout = workspace.layout_name
        active = workspace.active
        panes = self.all_panes()
        originals = {channel_id: (channel.x.copy(), channel.y.copy())
                     for channel_id, channel in window.store.channels.items()}
        with patch.object(workspace, 'set_layout', wraps=workspace.set_layout) as change_layout:
            changed = self.controls.set_color([self.a.id], '#df3355')
        self.app.processEvents()
        self.assertEqual(changed, [self.a.id])
        change_layout.assert_not_called()
        self.assertEqual(workspace.layout_name, layout)
        self.assertIs(workspace.active, active)
        self.assertEqual(self.all_panes(), panes)
        self.assertEqual(self.view_snapshot(), before)
        self.assertEqual(pane.cursor_locks[0]['index'], 2)
        self.assertEqual(pane.measurements()[self.a.id]['A'], 200)
        self.assertEqual(pane.cursor_markers[0].getData()[1][0], 200)
        for channel_id, (x, y) in originals.items():
            np.testing.assert_array_equal(window.store.channels[channel_id].x, x)
            np.testing.assert_array_equal(window.store.channels[channel_id].y, y)
        for graph in (workspace.panes[0], window.comparison.active):
            self.assertEqual(graph.curves[self.a.id][1].pen.color().name(), '#df3355')
        self.assertNotEqual(window.comparison.active.curves[self.b.id][1].pen.color().name(), '#df3355')

    def test_selected_stable_ids_disambiguate_same_names_and_leave_actuators_distinct(self):
        original = channel_colors(self.window.store)
        with patch.object(self.window.portal, 'selected', return_value=[self.b.id]), \
                patch.object(QtWidgets.QColorDialog, 'getColor', return_value=QtGui.QColor('#228844')):
            self.assertEqual(self.controls.choose(), [self.b.id])
        colors = channel_colors(self.window.store)
        self.assertEqual(colors[self.b.id], '#228844')
        self.assertEqual(colors[self.a.id], original[self.a.id])
        self.assertEqual(colors[self.inlet.id], original[self.inlet.id])
        self.assertEqual(colors[self.drain.id], original[self.drain.id])
        self.assertNotEqual(colors[self.inlet.id], colors[self.drain.id])
        self.controls.set_color([self.inlet.id], '#9040c0')
        self.assertNotEqual(channel_colors(self.window.store)[self.inlet.id],
                            channel_colors(self.window.store)[self.drain.id])
        pane = self.window.dashboard.panes[1]
        matching = [(sample, label) for sample, label in pane.legend.items
                    if 'Inlet Valve' in getattr(label, 'full_channel_label', label.text)]
        self.assertEqual(matching[0][0].item.opts['pen'].color().name(), '#9040c0')

    def test_cancel_picker_and_channel_chooser_leave_metadata_and_views_untouched(self):
        # An unallocated automatic color must not be persisted just because a
        # picker was opened and cancelled.
        self.window.store.channels[self.a.id].attributes.pop('trace_color', None)
        before = {channel_id: deepcopy(channel.attributes)
                  for channel_id, channel in self.window.store.channels.items()}
        views = self.view_snapshot()
        with patch.object(QtWidgets.QColorDialog, 'getColor', return_value=QtGui.QColor()) as picker:
            self.assertEqual(self.controls.choose([self.a.id]), [])
            self.assertIs(picker.call_args.args[1], self.window)
        with patch.object(self.window.portal, 'selected', return_value=[]), \
                patch('app_trace_controls.choose_item', return_value=('', False)), \
                patch.object(QtWidgets.QColorDialog, 'getColor') as picker:
            self.assertEqual(self.controls.choose(), [])
            picker.assert_not_called()
        self.assertEqual({channel_id: channel.attributes for channel_id, channel in
                          self.window.store.channels.items()}, before)
        self.assertEqual(self.view_snapshot(), views)

    def test_fullscreen_picker_and_channel_chooser_use_the_fullscreen_parent(self):
        from app_graph_fullscreen import GraphFullscreenController
        controller = getattr(self.window, 'graph_fullscreen', None)
        if controller is None:
            controller = self.window.graph_fullscreen = GraphFullscreenController(self.window)
        pane = self.window.dashboard.active
        host = controller.enter(pane)
        self.app.processEvents()
        metadata = {channel_id: deepcopy(channel.attributes)
                    for channel_id, channel in self.window.store.channels.items()}
        views = self.view_snapshot()
        parent = pane.parentWidget()
        try:
            self.assertTrue(controller.is_active)
            with patch.object(QtWidgets.QColorDialog, 'getColor', return_value=QtGui.QColor()) as picker:
                self.assertEqual(self.controls.choose([self.a.id]), [])
                self.assertIs(picker.call_args.args[1], host)
            with patch.object(self.window.portal, 'selected', return_value=[]), \
                    patch('app_trace_controls.choose_item', return_value=('', False)) as chooser, \
                    patch.object(QtWidgets.QColorDialog, 'getColor') as picker:
                self.assertEqual(self.controls.choose(), [])
                self.assertIs(chooser.call_args.args[0], host)
                picker.assert_not_called()
            def select(dialog_parent, title, label, choices):
                self.assertIs(dialog_parent, host)
                return choices[0], True
            with patch.object(self.window.portal, 'selected', return_value=[]), \
                    patch('app_trace_controls.choose_item', side_effect=select), \
                    patch.object(QtWidgets.QColorDialog, 'getColor', return_value=QtGui.QColor()) as picker:
                self.assertEqual(self.controls.choose(), [])
                self.assertIs(picker.call_args.args[1], host)
            self.assertEqual({channel_id: channel.attributes for channel_id, channel in
                              self.window.store.channels.items()}, metadata)
            self.assertEqual(self.view_snapshot(), views)
            self.assertTrue(controller.is_active)
            self.assertIs(pane.parentWidget(), parent)
        finally:
            controller.exit()

    def test_explicit_multiple_selection_is_batched_and_repeating_color_is_a_noop(self):
        notifications = []
        self.window.store.observe(lambda ids: notifications.append(set(ids)))
        changed = self.controls.set_color([self.a.id, self.b.id, self.a.id], '#667722')
        self.assertEqual(changed, [self.a.id, self.b.id])
        self.assertEqual(notifications, [{self.a.id, self.b.id}])
        self.assertEqual(channel_colors(self.window.store)[self.a.id], '#667722')
        self.assertEqual(channel_colors(self.window.store)[self.b.id], '#667722')
        views = self.view_snapshot()
        self.assertEqual(self.controls.set_color([self.a.id, self.b.id], '#667722'), [])
        self.assertEqual(len(notifications), 1)
        self.assertEqual(self.view_snapshot(), views)

    def test_failed_observer_restores_metadata_view_state_and_synchronization_guards(self):
        before = {channel_id: deepcopy(channel.attributes)
                  for channel_id, channel in self.window.store.channels.items()}
        views = self.view_snapshot()
        def reject_new_color(ids):
            if self.window.store.channels[self.a.id].attributes.get('plot_style', {}).get('color') == '#667722':
                raise RuntimeError('An appearance observer failed')
        self.window.store.observe(reject_new_color)
        with self.assertRaisesRegex(RuntimeError, 'observer failed'):
            self.controls.set_color([self.a.id, self.b.id], '#667722')
        self.assertEqual({channel_id: channel.attributes for channel_id, channel in
                          self.window.store.channels.items()}, before)
        self.assertEqual(self.view_snapshot(), views)
        for workspace in self.window.workspaces:
            self.assertFalse(workspace._range_syncing)
            self.assertFalse(workspace._syncing)
        self.assertTrue(all(not pane._history_restoring for pane in self.all_panes()))

    def test_multi_trace_fallback_asks_for_one_source_qualified_channel(self):
        captured = []
        def select(parent, title, label, choices):
            captured.extend(choices)
            return choices[0], True
        with patch.object(self.window.portal, 'selected', return_value=[]), \
                patch('app_trace_controls.choose_item', side_effect=select), \
                patch.object(QtWidgets.QColorDialog, 'getColor', return_value=QtGui.QColor('#cc7722')):
            self.assertEqual(self.controls.choose(), [self.b.id])
        self.assertTrue(any('Run B' in label for label in captured))
        self.assertEqual(len(captured), 3)
        self.assertNotIn('plot_style', self.window.store.channels[self.inlet.id].attributes)

    def test_color_survives_preset_workspace_and_rendered_export(self):
        self.controls.set_color([self.a.id], '#c42b67')
        store = self.window.store
        preset = channel_preset(store, self.window.dashboard, {})
        entry = next(entry for entry in preset['signals'].values()
                     if entry.get('source_path') == self.a.source and entry['name'] == 'Pressure')
        self.assertEqual(entry['color'], '#c42b67')
        path = save_workspace(Path(self.temp.name) / 'colors.json', store,
                              [workspace.state() for workspace in self.window.workspaces])
        restored, views, _ = load_workspace(path)
        self.assertEqual(channel_colors(restored)[self.a.id], '#c42b67')
        # Capture the actual Matplotlib plot calls made by the normal export
        # renderer, rather than testing a second copy of its color lookup.
        from matplotlib.axes import Axes
        plot = Axes.plot
        calls = []
        def record(axis, *args, **kwargs):
            calls.append(kwargs.copy())
            return plot(axis, *args, **kwargs)
        target = Path(self.temp.name) / 'colored.png'
        with patch.object(Axes, 'plot', record):
            render_report(target, restored, views[0])
        self.assertGreater(target.stat().st_size, 1000)
        self.assertTrue(any(call.get('color') == '#c42b67' for call in calls))

    def test_invalid_or_stale_selection_is_atomic_and_busy_operations_are_rejected(self):
        before = {channel_id: deepcopy(channel.attributes)
                  for channel_id, channel in self.window.store.channels.items()}
        for ids, color in (([self.a.id, 'missing'], '#224466'),
                           ([self.a.id], 'bad color'),
                           ([self.a.id], '#00224466'),
                           ([], '#224466')):
            with self.assertRaises(ValueError):
                self.controls.set_color(ids, color)
        self.assertEqual({channel_id: channel.attributes for channel_id, channel in
                          self.window.store.channels.items()}, before)
        self.window.busy = True
        try:
            with self.assertRaisesRegex(ValueError, 'current operation'):
                self.controls.set_color([self.a.id], '#224466')
        finally:
            self.window.busy = False


if __name__ == '__main__':
    unittest.main()
