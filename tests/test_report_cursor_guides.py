"""Observe actual export artists and evidence, not just preference plumbing."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from matplotlib.axes import Axes
from PySide6 import QtWidgets

from app_channel_store import Channel, ChannelStore
from app_report_details import ReportDetailsDialog, update_report_details
from app_reporting import export_report


class ReportCursorGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def fixture(self):
        store = ChannelStore()
        channel = store.add(Channel('Voltage', np.arange(5.), np.arange(5.)+2,
                                    unit='V', coordinate_unit='min'))
        pane = {'ids': [channel.id], 'bindings': {}, 'cursors': [1., 3.],
                'cursor_mode': 'dual', 'snap': True,
                'cursor_locks': [{'channel': channel.id, 'index': 1}, None]}
        return store, {'layout': 'Single', 'panes': [pane]}

    def test_analysis_and_comparison_exports_hide_guides_but_keep_evidence(self):
        original_line = Axes.axvline
        original_scatter = Axes.scatter
        with tempfile.TemporaryDirectory() as directory:
            for kind, suffix in [('analysis', '.png'), ('analysis', '.pdf'), ('comparison', '.pdf')]:
                for enabled in (False, True):
                    with self.subTest(kind=kind, suffix=suffix, enabled=enabled):
                        store, workspace = self.fixture()
                        workspace['report_kind'] = kind
                        before = deepcopy(workspace)
                        lines, markers = [], []
                        def line(axis, position, *args, **kwargs):
                            lines.append(position)
                            return original_line(axis, position, *args, **kwargs)
                        def scatter(axis, x, y, *args, **kwargs):
                            markers.append((x, y))
                            return original_scatter(axis, x, y, *args, **kwargs)
                        path = Path(directory)/(kind+str(enabled)+suffix)
                        with patch.object(Axes, 'axvline', line), patch.object(Axes, 'scatter', scatter):
                            _, summary = export_report(path, store, workspace,
                                metadata={'show_cursor_guides': True} if enabled else {})
                        self.assertEqual(lines, [1., 3.] if enabled else [])
                        self.assertEqual(len(markers), int(enabled))
                        self.assertEqual(workspace, before)
                        self.assertGreater(path.stat().st_size, 100)
                        self.assertEqual(summary.iloc[0]['cursor_A_X'], 1.)
                        self.assertEqual(summary.iloc[0]['cursor_B_X'], 3.)
                        self.assertEqual(summary.iloc[0]['A'], 3.)
                        self.assertEqual(summary.iloc[0]['B'], 5.)

    def test_engineering_export_uses_same_default_and_retains_cursor_evidence(self):
        import test_engineering_report_details as fixtures
        from app_engineering_reports import export_engineering
        import json
        original = Axes.axvline
        with tempfile.TemporaryDirectory() as directory:
            store, runs, comparison, ids = fixtures.EngineeringReportDetailsTests().fixture(count=1)
            for enabled in (False, True):
                lines = []
                def line(axis, position, *args, **kwargs):
                    lines.append(position)
                    return original(axis, position, *args, **kwargs)
                path = Path(directory)/f'engineering-{enabled}.pdf'
                with patch.object(Axes, 'axvline', line):
                    export_engineering(path, store, runs, comparison,
                        metadata={'show_cursor_guides': enabled},
                        view={'cursors': [1., 3.], 'snap': True}, selected_ids=ids)
                self.assertEqual(bool(lines), enabled)
                if enabled:
                    self.assertEqual(set(lines), {1., 3.})
                evidence = json.loads(path.with_suffix('.evidence.json').read_text())
                self.assertEqual(len(evidence['metadata']['Cursor interval evidence']), len(ids))

    def test_dialog_preference_survives_metadata_edit_without_mutating_original(self):
        original = {'custom': 'kept'}
        dialog = ReportDetailsDialog(original)
        try:
            self.assertFalse(dialog.cursor_guides.isChecked())
            dialog.cursor_guides.setChecked(True)
            saved = update_report_details(original, dialog.values())
            self.assertTrue(saved['show_cursor_guides'])
            self.assertEqual(original, {'custom': 'kept'})
        finally:
            dialog.close()
        restored = ReportDetailsDialog(saved)
        try:
            self.assertTrue(restored.cursor_guides.isChecked())
        finally:
            restored.close()


if __name__ == '__main__':
    unittest.main()
