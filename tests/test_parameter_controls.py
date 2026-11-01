"""User workflows retain source identity and never silently confirm meaning."""
from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from PySide6 import QtWidgets

from app_channel_store import ChannelStore, Dataset
from app_ingestion import ingest
from app_parameter_controls import ParameterAnalysisDialog, ParameterReviewDialog, ParameterResultsDialog
from app_parameter_inventory import inventory_runs
from app_parameter_semantics import resolve_mapping
from app_report_appearance import CURSOR_LINES_OPTION
from app_report_details import ReportDetailsDialog, update_report_details
from app_workbench import AdvancedStudioWindow


class ParameterWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_cursor_export_checkbox_is_persistent_and_does_not_change_live_cursors(self):
        window = AdvancedStudioWindow()
        try:
            before = deepcopy(window.dashboard.state())
            dialog = ReportDetailsDialog(window.report_metadata(), window)
            self.assertFalse(dialog.cursor_lines.isChecked())
            dialog.cursor_lines.setChecked(True)
            window.engineering.session['metadata'] = update_report_details(window.report_metadata(), dialog.values())
            self.assertTrue(window.report_metadata()[CURSOR_LINES_OPTION])
            self.assertTrue(ReportDetailsDialog(window.report_metadata(), window).cursor_lines.isChecked())
            self.assertEqual(window.dashboard.state(), before)
            with self.assertRaises(ValueError):
                update_report_details({}, {CURSOR_LINES_OPTION: 'true'})
        finally:
            window.close()

    def test_text_only_recording_import_remains_removable_and_in_inventory(self):
        other = ChannelStore()
        ds = Dataset('Controller log', pd.DataFrame({'state': ['idle', 'run'], 'note': ['start', 'stop']}), 'synthetic.txt')
        other.datasets[ds.id] = ds
        window = AdvancedStudioWindow()
        try:
            with patch.object(window, 'review_tdms_import', return_value=True):
                window.finish_import(other)
            self.assertIn(ds.id, window.store.datasets)
            dialog = ParameterAnalysisDialog(window.parameter_analysis)
            self.assertEqual(dialog.inventory.rowCount(), 2)
            self.assertEqual(len(dialog.fields), 2)
            self.assertTrue(all(not m['authority']['reviewed'] for m in dialog.mappings.values()))
            self.assertEqual(window.store.removal_plan([ds.id])['dataset_ids'], {ds.id})
            dialog.close()
        finally:
            window.close()

    def test_review_fields_and_confirmed_pairings_are_explicit_and_session_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChannelStore()
            for number in (1, 2):
                path = Path(directory)/f'run-{number}.csv'
                path.write_text('time[s],sensor\n0,1\n1,2\n2,3\n', encoding='utf-8')
                ingest(store, path)
            window = AdvancedStudioWindow()
            try:
                window.merge_store(store)
                dialog = ParameterAnalysisDialog(window.parameter_analysis)
                self.assertEqual(dialog.pair_table.rowCount(), 0, 'Names must never confirm a pairing')
                fields = [f for f in dialog.fields if f['original_name'] == 'sensor']
                review = ParameterReviewDialog(fields[0], resolve_mapping(fields[0]), dialog)
                review.fields['structure'].setCurrentText('analog')
                review.fields['stored_values'].setCurrentText('raw')
                review.confirm.setChecked(True)
                review.authority.setText('Synthetic fixture review')
                mapping = review.values()
                self.assertEqual(mapping['structure'], 'analog')
                self.assertTrue(mapping['authority']['reviewed'])
                self.assertEqual(mapping['encoding']['stored_values'], 'raw')
                dialog.add_pair({'reference_field_id': fields[0]['id'], 'candidate_field_id': fields[1]['id']})
                options, pairings = dialog.settings()
                self.assertFalse(pairings[0]['confirmed'])
                self.assertEqual(options['alignment'], 'elapsed')
                dialog.pair_table.cellWidget(0, 2).setChecked(True)
                options, pairings = dialog.settings()
                window.parameter_analysis.save_state(mappings={fields[0]['id']: mapping}, pairings=pairings, options=options)
                saved = window.ui_state()['engineering_session']['parameter_analysis']
                self.assertEqual(saved['pairings'], pairings)
                self.assertEqual(saved['mappings'][fields[0]['id']], mapping)
                dialog.close()
                review.close()
            finally:
                window.close()

    def test_results_show_exact_unavailable_reasons_and_source_record_without_recalculation(self):
        result = {'schema_version': 2, 'kind': 'analysis', 'status': 'partial',
            'inventory': [{'original_name': 'Unknown x', 'run_id': 'r', 'disposition': 'needs review'}],
            'metrics': [{'field_id': 'f', 'metric_id': 'supported_duration', 'value': None,
                         'unit': 's', 'status': 'needs_mapping', 'reasons': ['Clock is not established']}],
            'readiness': [{'field_id': 'f', 'status': 'needs_mapping', 'reasons': ['Clock is not established']}],
            'plot_series': []}
        before = deepcopy(result)
        window = AdvancedStudioWindow()
        try:
            dialog = ParameterResultsDialog(window, result)
            dialog.tables['metrics'].setCurrentCell(0, 0)
            self.assertIn('Clock is not established', dialog.details.toPlainText())
            self.assertEqual(dialog.tables['metrics'].item(0, 2).text(), 'Not Available')
            self.assertEqual(result, before)
            dialog.close()
        finally:
            window.close()

    def test_import_options_require_explicit_text_adapter_and_preserve_locale(self):
        from app_import_options import ImportOptionsDialog
        dialog = ImportOptionsDialog('custom.payload', unsupported=True)
        dialog.delimiter.setText(';')
        dialog.decimal.setCurrentText(',')
        dialog.time_column.setText('Elapsed')
        dialog.unit.setCurrentText('s')
        options = dialog.options()
        self.assertEqual(options['reader_id'], 'tabular')
        self.assertEqual(options['delimiter'], ';')
        self.assertEqual(options['time_column'], 'Elapsed')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'custom.payload'
            path.write_text('Elapsed;Pressure\n0;1,5\n1;2,5\n', encoding='utf-8')
            store = ChannelStore()
            ingest(store, path, reader_options=options)
            field = next(f for r in inventory_runs(store) for f in r['fields'] if f['original_name'] == 'Pressure')
            from app_parameter_inventory import source_field
            np.testing.assert_array_equal(source_field(store, field)['values'], [1.5, 2.5])
        dialog.close()
