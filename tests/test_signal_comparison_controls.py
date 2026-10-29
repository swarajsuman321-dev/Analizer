"""User-facing one-click two-recording comparison selection and worker flow."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from app_channel_store import Channel, Dataset
from app_dialog_history import remember_path
from app_operation_context import checkpoint
from app_signal_comparison_controls import SignalComparisonControls, SignalComparisonDialog


class SignalComparisonControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ, {
            'ANALIZER_SETTINGS_DIR': str(self.root/'settings'),
            'ANALIZER_OUTPUT_DIR': str(self.root/'outputs')})
        self.env.start()
        self.errors = []
        self.warnings = patch.object(QtWidgets.QMessageBox, 'warning',
            side_effect=lambda parent, title, text, *args: self.errors.append(str(text)))
        self.warnings.start()
        from app_workbench import AdvancedStudioWindow
        self.window = AdvancedStudioWindow()
        self.window.resize(1280, 900)
        self.window.show()
        self.controls = SignalComparisonControls(self.window)
        self.app.processEvents()
        self.a = self.dataset('Reference appliance.csv')
        self.b = self.dataset('Candidate appliance.csv')
        self.reference = self.channel(self.a, x=[4, 5, 6], y=[0, 120, 0])
        self.candidate = self.channel(self.b, x=[20, 21, 22], y=[0, 100, 0])
        self.calls = []
        self.gui_thread = threading.get_ident()

    def tearDown(self):
        if self.window.busy:
            self.window.cancel_operation()
            self.finish()
        self.window.close()
        self.app.processEvents()
        self.warnings.stop()
        self.env.stop()
        self.temp.cleanup()

    def dataset(self, name):
        ds = Dataset(name, pd.DataFrame({'Raw': [1, 2, 3]}), str(self.root/name))
        self.window.store.datasets[ds.id] = ds
        return ds

    def channel(self, dataset, name='Drum speed', x=None, y=None):
        return self.window.store.add(Channel(name, x if x is not None else [0, 1, 2],
            y if y is not None else [1, 2, 3], unit='RPM', coordinate_unit='min',
            dataset_id=dataset.id, source=dataset.source))

    def result(self, status='compared'):
        return {'schema': 1, 'status': status,
            'reason': '' if status == 'compared' else 'The channels have no joint supported time.',
            'reference': {'channel_id': self.reference.id, 'name': self.reference.name,
                          'dataset': self.a.name, 'source': self.a.source},
            'candidate': {'channel_id': self.candidate.id, 'name': self.candidate.name,
                          'dataset': self.b.name, 'source': self.b.source},
            'alignment': {'mode': 'elapsed', 'description': 'Elapsed time from each recording start'},
            'metrics': {'unit': 'RPM', 'mean_bias': -10., 'mean_absolute_difference': 10.,
                        'rmse': 12., 'max_absolute_difference': 20.,
                        'compared_duration_min': 2., 'coverage_fraction': 1.},
            'summary': ['Candidate peak speed is 20 RPM below the reference.'],
            'limitations': ['No acceptance limits were configured.']}

    def engine(self, store, reference, candidate, **kwargs):
        self.calls.append(('engine', reference, candidate, kwargs, threading.get_ident()))
        return self.result()

    def bundle(self, path, store, workspace, metadata=None, **kwargs):
        self.calls.append(('bundle', str(path), deepcopy(workspace), deepcopy(metadata), threading.get_ident()))
        path = Path(path)
        result = {'pdf': str(path), 'workbook': str(path.with_suffix('.xlsx')),
                  'evidence': str(path.with_suffix('.evidence.json')), 'report_id': 'test-report'}
        for key in ('pdf', 'workbook', 'evidence'):
            Path(result[key]).write_text('complete '+key, encoding='utf-8')
        return result

    def modules(self, engine=None, bundle=None):
        return patch.dict('sys.modules', {
            'app_signal_comparison': SimpleNamespace(compare_signals=engine or self.engine),
            'app_comparison_report': SimpleNamespace(export_comparison_bundle=bundle or self.bundle)})

    def finish(self):
        for _ in range(1000):
            self.app.processEvents()
            if not self.window.busy:
                self.app.processEvents()
                return
            QtTest.QTest.qWait(5)
        self.fail('Two-signal comparison worker did not finish')

    def test_two_selected_sources_compare_directly_and_write_full_bundle_without_save_wizard(self):
        self.window.dashboard.assign([self.reference.id, self.candidate.id])
        self.app.processEvents()
        before = deepcopy([view.state() for view in self.window.workspaces])
        arrays = [(c, c.x, c.y, c.x.copy(), c.y.copy()) for c in (self.reference, self.candidate)]
        self.window.report_metadata = lambda: {'Conclusions': 'Reviewed observation', 'Prepared by': 'Engineer'}
        with self.modules(), patch.object(self.window.portal, 'selected', return_value=[self.reference.id, self.candidate.id]), \
                patch.object(QtWidgets.QFileDialog, 'getSaveFileName', side_effect=AssertionError('No save wizard expected')):
            self.assertTrue(self.controls.compare_selected())
            self.assertTrue(self.window.busy)
            self.finish()
        self.assertEqual(self.errors, [])
        engine, export = self.calls
        self.assertEqual(engine[1:4], (self.reference.id, self.candidate.id, {'alignment': 'elapsed'}))
        self.assertNotEqual(engine[-1], self.gui_thread)
        self.assertNotEqual(export[-1], self.gui_thread)
        self.assertEqual(export[2]['layout'], 'Horizontal split')
        self.assertEqual(export[2]['panes'][0]['cursors'], [4., 6.])
        self.assertEqual(export[2]['panes'][1]['cursors'], [20., 22.])
        self.assertEqual(export[3]['Conclusions'], 'Reviewed observation')
        self.assertEqual(export[3]['Signal comparison']['metrics']['mean_bias'], -10.)
        self.assertEqual([view.state() for view in self.window.workspaces], before)
        for c, x, y, old_x, old_y in arrays:
            self.assertIs(c.x, x); self.assertIs(c.y, y)
            np.testing.assert_equal(c.x, old_x); np.testing.assert_equal(c.y, old_y)
        for key in ('pdf', 'workbook', 'evidence'):
            self.assertTrue(Path(self.controls.last_bundle[key]).is_file())
        self.assertEqual(self.window.last_export, Path(self.controls.last_bundle['pdf']))
        self.assertIn(self.a.name, self.controls.result_dialog.sources.text())
        self.assertIn(self.b.name, self.controls.result_dialog.sources.text())
        self.assertEqual(self.controls.result_dialog.metrics.item(0, 1).text(), '-10 RPM')

    def test_exactly_two_visible_channels_are_used_when_rows_are_not_selected(self):
        self.window.dashboard.assign([self.reference.id, self.candidate.id])
        with self.modules(), patch.object(self.window.portal, 'selected', return_value=[]):
            self.controls.compare_selected()
            self.finish()
        self.assertEqual(self.calls[0][1:3], (self.reference.id, self.candidate.id))
        self.assertIsNone(self.controls.dialog)

    def test_more_than_two_selected_channels_requires_explicit_pair_and_cancel_starts_nothing(self):
        extra = self.channel(self.a, name='Speed feedback')
        with patch.object(self.window.portal, 'selected', return_value=[self.reference.id, self.candidate.id, extra.id]):
            dialog = self.controls.compare_selected()
        self.assertIsInstance(dialog, SignalComparisonDialog)
        self.assertIsNone(dialog.reference.currentData())
        self.assertIsNone(dialog.candidate.currentData())
        self.assertFalse(dialog.compare_button.isEnabled())
        dialog.reject()
        self.app.processEvents()
        self.assertFalse(self.window.busy)
        self.assertFalse(self.window.workers)
        self.assertIsNone(self.controls.dialog)
        self.assertEqual(list((self.root/'outputs').rglob('*.pdf')), [])

    def test_chooser_excludes_same_recording_and_keeps_source_qualified_names(self):
        extra = self.channel(self.a, name='Speed feedback')
        with patch.object(self.window.portal, 'selected', return_value=[self.reference.id, extra.id]):
            dialog = self.controls.compare_selected()
        self.assertIsInstance(dialog, SignalComparisonDialog)
        dialog.reference.setCurrentIndex(dialog.reference.findData(self.reference.id))
        self.assertEqual([dialog.candidate.itemData(i) for i in range(dialog.candidate.count())], [None, self.candidate.id])
        self.assertIn('Candidate appliance', dialog.candidate.itemText(1))
        dialog.candidate.setCurrentIndex(1)
        self.assertTrue(dialog.compare_button.isEnabled())
        with self.modules():
            dialog.compare_button.click()
            self.finish()
        self.assertEqual(self.calls[0][1:3], (self.reference.id, self.candidate.id))

    def test_blocked_comparison_explains_reason_without_exporting(self):
        exporter = Mock(side_effect=AssertionError('Blocked data must not export'))
        with self.modules(engine=lambda *args, **kwargs: self.result('blocked'), bundle=exporter):
            self.controls.start(self.reference.id, self.candidate.id)
            self.finish()
        exporter.assert_not_called()
        self.assertEqual(self.controls.last_result['status'], 'blocked')
        self.assertIsNone(self.controls.last_bundle)
        self.assertIsNone(self.window.last_export)
        self.assertIn('no joint supported time', self.window.statusBar().currentMessage())
        self.assertEqual(list((self.root/'outputs').rglob('*.pdf')), [])
        self.assertTrue(self.controls.action.isEnabled())

    def test_export_failure_restores_action_and_keeps_previous_complete_result(self):
        previous = self.root/'previous.pdf'; previous.write_bytes(b'previous complete output')
        self.window.last_export = previous
        self.controls.last_result = {'status': 'previous'}
        with self.modules(bundle=Mock(side_effect=OSError('Disk full'))):
            self.controls.start(self.reference.id, self.candidate.id)
            self.finish()
        self.assertEqual(self.errors, ['Disk full'])
        self.assertEqual(previous.read_bytes(), b'previous complete output')
        self.assertEqual(self.window.last_export, previous)
        self.assertEqual(self.controls.last_result, {'status': 'previous'})
        self.assertTrue(self.controls.action.isEnabled())

    def test_cancellation_before_export_writes_no_bundle_and_reenables_action(self):
        gate = threading.Event(); started = threading.Event()
        def engine(*args, **kwargs):
            started.set()
            if not gate.wait(5):raise RuntimeError('Cancellation gate timed out')
            checkpoint('Compare cancelled')
            return self.result()
        exporter = Mock(side_effect=AssertionError('Cancelled data must not export'))
        try:
            with self.modules(engine=engine, bundle=exporter):
                self.controls.start(self.reference.id, self.candidate.id)
                for _ in range(100):
                    if started.is_set():break
                    QtTest.QTest.qWait(5)
                self.assertTrue(started.is_set())
                self.window.cancel_operation(); gate.set(); self.finish()
        finally:
            gate.set()
        exporter.assert_not_called()
        self.assertEqual(self.errors, [])
        self.assertIn('cancel', self.window.statusBar().currentMessage().lower())
        self.assertIsNone(self.controls.last_result)
        self.assertTrue(self.controls.action.isEnabled())

    def test_auto_reports_reuse_the_purpose_folder_and_are_unique(self):
        folder = self.root/'Reviewed reports'; folder.mkdir()
        remember_path('SignalComparisonReport', folder)
        with self.modules():
            self.controls.start(self.reference.id, self.candidate.id); self.finish()
            first = self.window.last_export
            self.controls.start(self.reference.id, self.candidate.id); self.finish()
            second = self.window.last_export
        self.assertEqual(first.parent.resolve(), folder)
        self.assertEqual(second.parent.resolve(), folder)
        self.assertNotEqual(first, second)
        self.assertEqual(len(list(folder.glob('*.pdf'))), 2)

    def test_busy_operation_does_not_start_a_chooser_or_comparison(self):
        self.window.busy = True
        try:
            with self.assertRaisesRegex(ValueError, 'Wait for the current operation'):
                self.controls.compare_selected()
        finally:
            self.window.busy = False
        self.assertIsNone(self.controls.dialog)
        self.assertEqual(self.calls, [])

    def test_report_open_actions_use_the_committed_paths(self):
        with self.modules():
            self.controls.start(self.reference.id, self.candidate.id); self.finish()
        dialog = self.controls.result_dialog
        buttons = {button.text(): button for button in dialog.findChildren(QtWidgets.QPushButton)}
        with patch.object(QtGui.QDesktopServices, 'openUrl', return_value=True) as open_url:
            buttons['Open Report'].click()
            self.assertEqual(Path(open_url.call_args.args[0].toLocalFile()).resolve(), self.window.last_export.resolve())
            buttons['Open Workbook'].click()
            self.assertEqual(Path(open_url.call_args.args[0].toLocalFile()).suffix, '.xlsx')
            buttons['Open Folder'].click()
            self.assertEqual(Path(open_url.call_args.args[0].toLocalFile()).resolve(), self.window.last_export.parent.resolve())


if __name__ == '__main__':
    unittest.main()
