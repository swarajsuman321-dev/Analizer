"""Arbitrary imported data comparison reuses stable channels and ordinary plots."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtWidgets, QtTest

from app_channel_store import Channel, Dataset
from app_compact_forms import CollapsibleHelp
from app_data_comparison import DataComparisonControls
from app_ingestion import ingest
from app_trace_colors import channel_colors


class DataComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ANALIZER_SETTINGS_DIR': self.temp.name,
                                          'ANALIZER_OUTPUT_DIR': self.temp.name})
        self.env.start()
        from app_workbench import AdvancedStudioWindow
        self.window = AdvancedStudioWindow()
        self.window.resize(1280, 900)
        self.window.show()
        self.controls = DataComparisonControls(self.window)
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.env.stop()
        self.temp.cleanup()

    def dataset(self, name):
        dataset = Dataset(name, pd.DataFrame({'Original': [10, 20]}), str(Path(self.temp.name) / name))
        self.window.store.datasets[dataset.id] = dataset
        return dataset

    def channel(self, dataset=None, name='Pressure', unit='Pa', x=None, y=None, **kwargs):
        x = [0., 1., 2., 3.] if x is None else x
        y = [10., 20., 15., 25.] if y is None else y
        return self.window.store.add(Channel(name, x, y, unit=unit, coordinate_unit=kwargs.pop('coordinate_unit', 'min'),
                                             dataset_id=dataset.id if dataset else '',
                                             source=dataset.source if dataset else '', **kwargs))

    def wait_until(self, predicate):
        for _ in range(500):
            self.app.processEvents()
            if predicate():
                return
            QtTest.QTest.qWait(10)
        self.fail('Comparison operation did not settle')

    def plotted_ids(self):
        return [id for pane in self.window.comparison.panes for id in pane.ids]

    def test_two_recordings_overlay_original_ids_without_changing_analysis_or_data(self):
        a = self.dataset('Bench.csv'); b = self.dataset('Measurements.tdms')
        first = self.channel(a); second = self.channel(b)
        self.window.dashboard.assign([first.id, second.id])
        pane = self.window.dashboard.active
        pane.setXRange(.5, 2.5, padding=0); pane.cursor_lines[0].setValue(1)
        pane.lock_cursor(0, first.id)
        self.app.processEvents()
        analysis = deepcopy(self.window.dashboard.state())
        colors = channel_colors(self.window.store)
        ids = list(self.window.store.channels)
        arrays = [(channel, channel.x, channel.y, channel.x.copy(), channel.y.copy()) for channel in (first, second)]
        result = self.controls.add_channels([first.id, second.id])
        self.app.processEvents()
        self.assertEqual(result, {'added': 2, 'already_present': 0, 'total': 2, 'datasets': 2})
        self.assertEqual(self.plotted_ids(), [first.id, second.id])
        self.assertEqual(list(self.window.store.channels), ids)
        self.assertIs(self.window.tabs.currentWidget(), self.window.comparison)
        self.assertEqual(self.window.dashboard.state(), analysis)
        self.assertEqual(channel_colors(self.window.store), colors)
        self.assertEqual(set(self.window.portal.visible_ids), {first.id, second.id})
        for channel, x, y, expected_x, expected_y in arrays:
            self.assertIs(self.window.store.channels[channel.id], channel)
            self.assertIs(channel.x, x); self.assertIs(channel.y, y)
            np.testing.assert_array_equal(channel.x, expected_x); np.testing.assert_array_equal(channel.y, expected_y)
        self.assertEqual(set(self.window.store.datasets), {a.id, b.id})

    def test_repeated_and_duplicate_selections_add_each_stable_id_once(self):
        channel = self.channel(self.dataset('Run.csv'))
        first = self.controls.add_channels(channel.id)
        self.assertEqual(first['added'], 1)
        self.window.tabs.setCurrentIndex(0)
        result = self.controls.add_channels([channel.id, channel.id])
        self.assertEqual(result, {'added': 0, 'already_present': 1, 'total': 1, 'datasets': 1})
        self.assertEqual(self.plotted_ids(), [channel.id])
        self.assertIs(self.window.tabs.currentWidget(), self.window.comparison)

    def test_append_preserves_existing_comparison_range_binding_annotations_and_locks(self):
        dataset = self.dataset('Run.csv')
        existing = self.channel(dataset)
        added = self.channel(dataset, 'Temperature', '°C', y=[30, 32, 34, 36])
        self.controls.add_channels([existing.id])
        pane = self.window.comparison.active
        pane.setXRange(.7, 2.3, padding=0); pane.setYRange(11, 18, padding=0)
        pane.cursor_lines[0].setValue(1); pane.cursor_lines[1].setValue(2)
        pane.lock_cursor(0, existing.id); pane.annotate('Marker', 1, text='Reviewed observation')
        self.app.processEvents(); before = deepcopy(pane.state())
        history = deepcopy(pane.history); history_index = pane.history_index
        result = self.controls.add_channels([existing.id, added.id])
        self.app.processEvents(); after = pane.state()
        self.assertEqual(result['added'], 1); self.assertEqual(result['already_present'], 1)
        self.assertEqual(after['ids'], [existing.id, added.id])
        for key in ('range', 'cursors', 'cursor_locks', 'annotations', 'snap', 'cursor_mode'):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after['bindings'][existing.id], before['bindings'][existing.id])
        self.assertIn('°C', pane.axes)
        self.assertEqual(pane.history, history); self.assertEqual(pane.history_index, history_index)

    def test_empty_missing_and_busy_inputs_fail_before_plot_mutation(self):
        channel = self.channel(self.dataset('Run.csv'))
        before = deepcopy(self.window.comparison.state())
        for ids, message in [([], 'at least one'), (None, 'at least one'),
                             ([channel.id, 'missing-id'], 'no longer loaded')]:
            with self.assertRaisesRegex(ValueError, message):
                self.controls.add_channels(ids)
            self.assertEqual(self.window.comparison.state(), before)
        self.window.busy = True
        try:
            with self.assertRaisesRegex(ValueError, 'current operation'):
                self.controls.add_channels([channel.id])
        finally:
            self.window.busy = False
        self.assertEqual(self.window.comparison.state(), before)
        self.assertIsNone(self.controls.last_result)

    def test_generated_empty_nonfinite_and_duplicate_timestamp_channels_are_retained(self):
        first = self.channel(x=[0, 1, 1, 2], y=[0, np.nan, np.inf, 3])
        second = self.channel(name='Empty source', unit='', x=[], y=[])
        result = self.controls.add_channels([first.id, second.id])
        self.assertEqual(result['added'], 2)
        np.testing.assert_array_equal(first.x, [0, 1, 1, 2])
        np.testing.assert_array_equal(first.y, [0, np.nan, np.inf, 3])
        self.assertEqual(self.plotted_ids(), [first.id, second.id])
        self.window.comparison.active.measurements()

    def test_mixed_units_and_coordinate_families_keep_exact_original_clocks(self):
        dataset = self.dataset('Mixed.tdms')
        channels = [self.channel(dataset),
                    self.channel(dataset, 'Temperature', '°C'),
                    self.channel(dataset, 'Seconds', 'W', coordinate_unit='s', x=[0, 20, 40, 60]),
                    self.channel(dataset, 'Spectrum', 'V', coordinate_unit='Hz', coordinate_kind='frequency'),
                    self.channel(dataset, 'Samples', '', coordinate_unit='sample', coordinate_kind='sample')]
        arrays = [channel.x.copy() for channel in channels]
        result = self.controls.add_channels([channel.id for channel in channels])
        self.assertEqual(result['added'], 5)
        for pane in self.window.comparison.visible_panes():
            families = {(self.window.store.channels[id].coordinate_kind,
                         self.window.store.channels[id].coordinate_unit) for id in pane.ids}
            self.assertLessEqual(len(families), 1)
        self.assertEqual(len({pane.coordinate for pane in self.window.comparison.visible_panes() if pane.ids}), 4)
        for channel, original in zip(channels, arrays): np.testing.assert_array_equal(channel.x, original)

    def test_coordinate_capacity_rejection_is_atomic(self):
        channels = [self.channel(name='Coordinate '+str(index), coordinate_kind='sample', coordinate_unit=str(index))
                    for index in range(11)]
        before = deepcopy(self.window.comparison.state())
        with self.assertRaisesRegex(ValueError, 'ten graph panes'):
            self.controls.add_channels([channel.id for channel in channels])
        self.assertEqual(self.window.comparison.state(), before)
        self.assertEqual(len(self.window.store.channels), 11)

    def test_repeated_hidden_channel_becomes_visible_without_duplicate(self):
        channel = self.channel(self.dataset('Run.csv'))
        workspace = self.window.comparison
        workspace.set_layout('Horizontal split'); workspace.panes[1].bind([channel.id])
        workspace.set_layout('Single')
        result = self.controls.add_channels([channel.id])
        self.assertEqual(result['added'], 0)
        self.assertEqual(result['already_present'], 1)
        self.assertIn(workspace.panes[1], workspace.visible_panes())
        self.assertEqual(self.plotted_ids(), [channel.id])

    def test_layout_expansion_preserves_visible_and_hidden_pane_cursor_controls(self):
        first = self.channel()
        second = self.channel(name='Spectrum', coordinate_kind='frequency', coordinate_unit='Hz')
        added = self.channel(name='Samples', coordinate_kind='sample', coordinate_unit='sample')
        hidden = self.channel(name='Hidden trace')
        controls = self.window.data_comparison
        controls.add_channels([first.id, second.id])
        workspace = self.window.comparison
        workspace.set_layout('10 panels')
        workspace.panes[9].bind([hidden.id])
        workspace.set_layout('Horizontal split')
        workspace.set_active(workspace.panes[0])
        QtTest.QTest.keyClick(workspace.panes[0], QtCore.Qt.Key.Key_C)
        workspace.panes[0].snap = False
        workspace.panes[9].set_cursor_mode('point')
        workspace.panes[9].snap = False
        workspace.set_active(workspace.panes[1])
        self.app.processEvents()
        original_panes = list(workspace.panes)
        before = [(pane.cursor_mode, pane.snap) for pane in original_panes]
        self.assertEqual(before[0], ('off', False))
        self.assertTrue(workspace.panes[9].isHidden())

        controls.add_channels([added.id])
        self.app.processEvents()

        self.assertEqual(workspace.layout_name, '2×2')
        self.assertEqual(workspace.panes, original_panes)
        self.assertEqual([(pane.cursor_mode, pane.snap) for pane in workspace.panes], before)
        self.assertTrue(workspace.panes[9].isHidden())
        self.assertEqual(workspace.panes[9].ids, [hidden.id])

    def test_unexpected_plot_failure_restores_prior_comparison(self):
        first = self.channel(); second = self.channel(name='New channel')
        self.controls.add_channels([first.id]); before = deepcopy(self.window.comparison.state())
        original_pane = self.window.comparison.active
        def fail(ids, visible):
            self.window.comparison.active.bind([first.id, second.id])
            raise ValueError('Plot could not be prepared')
        with patch.object(self.window.comparison, 'set_visible', side_effect=fail):
            with self.assertRaisesRegex(ValueError, 'could not be prepared'):
                self.controls.add_channels([second.id])
        self.assertEqual(self.window.comparison.state(), before)
        self.assertIs(self.window.comparison.active, original_pane)

    def test_fullscreen_exits_only_after_selection_validation(self):
        channel = self.channel()
        with patch.object(self.window, 'exit_graph_fullscreen', wraps=self.window.exit_graph_fullscreen) as exit_fullscreen:
            with self.assertRaises(ValueError): self.controls.add_channels([])
            with self.assertRaises(ValueError): self.controls.add_channels(['missing'])
            self.assertEqual(exit_fullscreen.call_count, 0)
            self.controls.add_channels([channel.id])
            self.assertEqual(exit_fullscreen.call_count, 1)

    def test_dialog_partitions_files_and_file_checkbox_includes_hidden_search_results(self):
        a = self.dataset('First.csv'); b = self.dataset('Second.xlsx')
        first = self.channel(a); other = self.channel(a, 'Temperature', '°C'); second = self.channel(b)
        dialog = self.controls.show_dialog(); self.app.processEvents()
        self.assertEqual(dialog.tree.topLevelItemCount(), 2)
        self.assertEqual(dialog.tree.headerItem().text(1), 'Unit')
        self.assertEqual(dialog.items[first.id].text(1), 'Pa')
        self.assertIn(a.source, dialog.items[first.id].toolTip(0))
        dialog.search.setText('Pressure')
        self.assertNotIn(other.id, dialog.items)
        dialog.roots[a.id].setCheckState(0, QtCore.Qt.CheckState.Checked)
        self.assertEqual(set(dialog.selected_ids()), {first.id, other.id})
        self.assertNotIn(second.id, dialog.selected_ids())
        self.assertIn('1 matches', dialog.roots[a.id].text(0))
        dialog.search.clear(); self.assertEqual(dialog.items[other.id].checkState(0), QtCore.Qt.CheckState.Checked)
        self.assertEqual(dialog.findChildren(QtWidgets.QCheckBox), [])
        self.assertTrue(dialog.findChild(CollapsibleHelp).details.isHidden())
        self.assertIs(self.controls.show_dialog(), dialog)
        dialog.reject(); self.assertEqual(self.plotted_ids(), [])

    def test_dialog_empty_state_and_add_button_use_existing_identity(self):
        dialog = self.controls.show_dialog(); self.app.processEvents()
        self.assertFalse(dialog.add_button.isEnabled()); self.assertTrue(dialog.open_button.isEnabled())
        self.assertIn('No channels loaded', dialog.status.text())
        dialog.reject(); self.app.processEvents()
        channel = self.channel(self.dataset('Any file.txt'))
        dialog = self.controls.show_dialog(); self.app.processEvents()
        dialog.items[channel.id].setCheckState(0, QtCore.Qt.CheckState.Checked)
        dialog.add_button.click(); self.app.processEvents()
        self.assertIsNone(self.controls.dialog)
        self.assertEqual(self.plotted_ids(), [channel.id])
        self.assertEqual(len(self.window.store.channels), 1)

    def test_open_more_cancel_returns_to_chooser_with_selection_without_nested_worker(self):
        channel = self.channel(self.dataset('Existing.csv'))
        dialog = self.controls.show_dialog()
        dialog.items[channel.id].setCheckState(0, QtCore.Qt.CheckState.Checked)
        with patch.object(self.window, 'open_data', return_value=False) as opener:
            self.controls.open_more_files()
        opener.assert_called_once_with(plot_import=False)
        self.assertIsNone(self.controls.dialog)
        self.wait_until(lambda: self.controls.dialog is not None)
        self.assertEqual(self.controls.dialog.selected_ids(), [channel.id])
        self.assertFalse(self.controls._resume.isActive()); self.assertFalse(self.window.workers)
        self.assertEqual(self.plotted_ids(), [])

    def test_open_more_uses_single_normal_background_import_without_autoplot(self):
        path = Path(self.temp.name) / 'ordinary.csv'
        pd.DataFrame({'time [s]': [0, 30, 60], 'Pressure [Pa]': [3, 4, 5]}).to_csv(path, index=False)
        self.controls.show_dialog()
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileNames', return_value=([str(path)], 'Data')):
            with patch.object(self.window, 'background', wraps=self.window.background) as background:
                self.controls.open_more_files()
                self.wait_until(lambda: not self.window.busy and self.controls.dialog is not None)
        self.assertEqual(background.call_count, 1)
        self.assertEqual(len(self.window.store.datasets), 1)
        self.assertEqual(len(self.window.store.channels), 1)
        self.assertEqual(self.plotted_ids(), [])
        self.assertEqual(self.window.dashboard.active.ids, [])
        self.assertFalse(self.controls._resume.isActive())
        dialog = self.controls.dialog
        id = next(iter(self.window.store.channels))
        dialog.items[id].setCheckState(0, QtCore.Qt.CheckState.Checked)
        dialog.add_button.click(); self.assertEqual(self.plotted_ids(), [id])

    def test_open_resume_waits_for_modal_review_and_stops_on_cancelled_close(self):
        self.controls.show_dialog()
        with patch.object(self.window, 'open_data', return_value=True): self.controls.open_more_files()
        review = QtWidgets.QDialog(self.window); review.setModal(True); review.show(); self.app.processEvents()
        self.controls._resume_after_open()
        self.assertIsNone(self.controls.dialog); self.assertTrue(self.controls._resume.isActive())
        review.reject(); self.wait_until(lambda: self.controls.dialog is not None)
        with patch.object(self.window, 'open_data', return_value=True): self.controls.open_more_files()
        self.assertTrue(self.controls._resume.isActive())
        # A close event must stop re-entry even if the actual close handler
        # later waits for a worker or rejects the close.
        self.controls.eventFilter(self.window, QtCore.QEvent(QtCore.QEvent.Type.Close))
        self.assertFalse(self.controls._resume.isActive()); self.assertFalse(self.controls._pending_open)

    def test_open_failure_returns_to_selection_and_does_not_poll_forever(self):
        channel = self.channel(self.dataset('Existing.csv'))
        self.controls.show_dialog()
        with patch.object(self.window, 'open_data', side_effect=ValueError('Cannot open file')):
            with self.assertRaisesRegex(ValueError, 'Cannot open file'):
                self.controls.open_more_files()
        self.assertIsNotNone(self.controls.dialog)
        self.assertFalse(self.controls._resume.isActive()); self.assertFalse(self.controls._pending_open)
        self.assertIn(channel.id, self.window.store.channels); self.assertEqual(self.plotted_ids(), [])

    def test_background_open_failure_keeps_originals_and_returns_to_selection(self):
        channel = self.channel(self.dataset('Existing.csv'))
        self.window.dashboard.assign([channel.id]); before = deepcopy(self.window.dashboard.state())
        self.controls.show_dialog(); failures = []
        def report_error(fn):
            try:
                return fn()
            except Exception as exc:
                failures.append(str(exc))
        missing = str(Path(self.temp.name) / 'missing.csv')
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileNames', return_value=([missing], 'Data')):
            with patch.object(self.window, 'guard', side_effect=report_error):
                self.controls.open_more_files()
                self.wait_until(lambda: not self.window.busy and self.controls.dialog is not None)
        self.assertTrue(failures); self.assertEqual(list(self.window.store.channels), [channel.id])
        self.assertEqual(self.window.dashboard.state(), before)
        self.assertEqual(self.plotted_ids(), []); self.assertFalse(self.controls._resume.isActive())

    def test_real_tdms_review_finishes_before_chooser_reopens(self):
        from nptdms import TdmsWriter, ChannelObject
        from app_tdms_templates import ParameterReview
        path = Path(self.temp.name) / 'new parameters.tdms'
        with TdmsWriter(path) as writer:
            writer.write_segment([ChannelObject('Sensors', 'Any temperature', np.array([20., 21., 22.]),
                                                properties={'unit_string': '°C', 'wf_increment': 1.})])
        controls = self.controls; observations = []
        class ReviewedParameters(ParameterReview):
            def exec(self):
                self.setModal(True); self.show(); DataComparisonTests.app.processEvents()
                controls._resume_after_open()
                observations.append((controls.dialog is None, QtWidgets.QApplication.activeModalWidget() is self))
                QtCore.QTimer.singleShot(0, self.accept)
                return super().exec()
        self.controls.show_dialog()
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileNames', return_value=([str(path)], 'Data')):
            with patch('app_tdms_templates.ParameterReview', ReviewedParameters):
                with patch.object(self.window, 'background', wraps=self.window.background) as background:
                    self.controls.open_more_files()
                    self.wait_until(lambda: not self.window.busy and self.controls.dialog is not None)
        self.assertEqual(observations, [(True, True)])
        self.assertEqual(background.call_count, 1)
        self.assertEqual(len(self.window.store.channels), 1)
        self.assertEqual(self.plotted_ids(), []); self.assertFalse(self.controls._resume.isActive())

    def test_loaded_csv_excel_and_tdms_are_compared_without_format_specific_mapping(self):
        from nptdms import TdmsWriter, ChannelObject
        root = Path(self.temp.name)
        csv = root / 'arbitrary.csv'; excel = root / 'arbitrary.xlsx'; tdms = root / 'arbitrary.tdms'
        pd.DataFrame({'time [s]': [0, 1, 2], 'Signal [V]': [1, 2, 3]}).to_csv(csv, index=False)
        pd.DataFrame({'time [s]': [0, 2, 4], 'Other [°C]': [20, 21, 22]}).to_excel(excel, index=False)
        with TdmsWriter(tdms) as writer:
            writer.write_segment([ChannelObject('Any sensors', 'Measurements', np.array([10., 12., 11.]),
                                                properties={'unit_string': 'bar', 'wf_increment': .5})])
        for path in (csv, excel, tdms): ingest(self.window.store, path)
        ids = list(self.window.store.channels); before = {id: self.window.store.channels[id].x.copy() for id in ids}
        result = self.controls.add_channels(ids)
        self.assertEqual(result['added'], 3); self.assertEqual(result['datasets'], 3)
        self.assertEqual(set(self.plotted_ids()), set(ids))
        for id in ids: np.testing.assert_array_equal(self.window.store.channels[id].x, before[id])


if __name__ == '__main__':
    unittest.main()
