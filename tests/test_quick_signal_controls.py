"""Real worker, PDF/workbook/JSON and three-signal chooser integration."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from PySide6 import QtWidgets

from app_channel_store import Channel, ChannelStore, Dataset
from app_quick_signal_analysis import QuickSignalAnalysisControls, QuickSignalDialog


class QuickSignalControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            'ANALIZER_SETTINGS_DIR': self.temp.name+'/settings',
            'ANALIZER_OUTPUT_DIR': self.temp.name+'/output'})
        self.environment.start()
        self.errors = []
        self.warnings = patch.object(QtWidgets.QMessageBox, 'warning',
            side_effect=lambda parent, title, message, *args: self.errors.append(str(message)))
        self.warnings.start()
        from app_workbench import AdvancedStudioWindow
        self.window = AdvancedStudioWindow()
        store = ChannelStore()
        dataset = Dataset('Synthetic Controller', pd.DataFrame({'raw': [1, 2, 3]}), 'synthetic://controller')
        store.datasets[dataset.id] = dataset
        self.ids = []
        for index in range(3):
            channel = store.add(Channel('Sensor '+str(index), [0, 1, 2], [index, index+1, index+2],
                unit='W', coordinate_unit='s', dataset_id=dataset.id))
            self.ids.append(channel.id)
        self.window.merge_store(store)
        self.controls = QuickSignalAnalysisControls(self.window)

    def tearDown(self):
        if self.window.busy:
            self.window.cancel_operation()
            self.finish()
        self.window.close()
        self.app.processEvents()
        self.warnings.stop()
        self.environment.stop()
        self.temp.cleanup()

    def finish(self):
        deadline = time.monotonic()+60
        while self.window.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.02)
        self.app.processEvents()
        self.assertFalse(self.window.busy, 'Selected-signal worker did not finish')

    def test_three_selected_same_file_signals_compare_directly_and_preserve_analysis(self):
        before = deepcopy(self.window.dashboard.state())
        arrays = [(channel.x.copy(), channel.y.copy()) for channel in self.window.store.channels.values()]
        with patch.object(self.window.portal, 'selected', return_value=self.ids), \
             patch.object(QtWidgets.QFileDialog, 'getSaveFileName', side_effect=AssertionError('No report wizard expected')):
            self.controls.compare_selected()
            self.finish()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.controls.last_result['kind'], 'comparison')
        self.assertEqual(len(self.controls.last_result['pairings']), 2)
        self.assertEqual(self.window.active_workspace, self.window.comparison)
        self.assertEqual(self.window.dashboard.state(), before)
        for channel, (x, y) in zip(self.window.store.channels.values(), arrays):
            np.testing.assert_array_equal(channel.x, x)
            np.testing.assert_array_equal(channel.y, y)
        for key in ('pdf', 'workbook', 'evidence'):
            self.assertTrue(Path(self.controls.last_bundle[key]).is_file())
        evidence = json.loads(Path(self.controls.last_bundle['evidence']).read_text(encoding='utf-8'))
        self.assertEqual(evidence['metrics'], self.controls.last_result['metrics'])
        self.assertEqual(evidence['comparisons'], self.controls.last_result['comparisons'])
        self.assertEqual(self.controls.result_dialog.tabs.tabText(0), 'Summary')

    def test_analysis_is_distinct_and_does_not_switch_or_fill_comparison(self):
        self.window.tabs.setCurrentWidget(self.window.dashboard)
        comparison_before = deepcopy(self.window.comparison.state())
        with patch.object(self.window.portal, 'selected', return_value=self.ids):
            self.controls.analyse_selected()
            self.finish()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.controls.last_result['kind'], 'analysis')
        self.assertEqual(self.controls.last_result['comparisons'], [])
        self.assertEqual(self.controls.last_result['provenance']['scope']['kind'], 'interval')
        self.assertEqual(self.window.active_workspace, self.window.dashboard)
        self.assertEqual(self.window.comparison.state(), comparison_before)

    def test_chooser_can_choose_three_and_change_reference_without_cross_file_requirement(self):
        dialog = QuickSignalDialog(self.controls, self.ids)
        self.assertEqual(dialog.selected(), self.ids)
        self.assertEqual(dialog.reference.count(), 3)
        dialog.reference.setCurrentIndex(2)
        with patch.object(self.controls, 'start') as start:
            dialog._start()
        self.assertEqual(start.call_args.args[0], self.ids)
        self.assertEqual(start.call_args.args[1], self.ids[2])
        self.assertEqual(start.call_args.kwargs['alignment'], 'elapsed')
        dialog.close()

    def test_chooser_file_checkboxes_never_select_another_recording(self):
        from PySide6 import QtCore
        dataset = Dataset('Another recording', pd.DataFrame(), 'synthetic://other')
        self.window.store.datasets[dataset.id] = dataset
        extra = self.window.store.add(Channel('Extra sensor', [0, 1], [1, 2], dataset_id=dataset.id))
        dialog = QuickSignalDialog(self.controls)
        first = dialog.tree.topLevelItem(0)
        first.setCheckState(0, QtCore.Qt.CheckState.Checked)
        self.assertEqual(set(dialog.selected()), set(self.ids))
        self.assertNotIn(extra.id, dialog.selected())
        first.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        self.assertEqual(dialog.selected(), [])
        dialog.close()
