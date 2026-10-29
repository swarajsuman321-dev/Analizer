"""Report notes remain optional, literal and workspace-persistent."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6 import QtWidgets

from app_report_details import ReportDetailsDialog, update_report_details


class ReportDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_edit_keeps_unknown_legacy_metadata_and_explicit_blank_removes_note(self):
        original = {'Observations': 'old', 'custom': {'fixture': 7}, 'Report title': 'old title'}
        before = deepcopy(original)
        result = update_report_details(original, {'Conclusions': 'Speed differs by $5%\\n; review 測定',
                                                   'Report title': 'Two appliances'})
        self.assertEqual(original, before)
        self.assertEqual(result['custom'], before['custom'])
        self.assertNotIn('Observations', result)
        self.assertEqual(result['Conclusions'], 'Speed differs by $5%\\n; review 測定')
        self.assertEqual(result['Report title'], 'Two appliances')

    def test_dialog_is_plain_text_and_reject_does_not_mutate_metadata(self):
        original = {'Observations': '<b>literal $x</b>\nsecond line', 'custom': [1, 2]}
        before = deepcopy(original)
        dialog = ReportDetailsDialog(original)
        self.assertEqual(dialog.fields['Observations'].toPlainText(), original['Observations'])
        dialog.fields['Observations'].setPlainText('draft')
        dialog.reject()
        self.assertEqual(original, before)
        dialog.close()

    def test_shared_notes_roundtrip_and_legacy_session_title_keeps_generic_default(self):
        from app_workbench import AdvancedStudioWindow
        from app_workspace_io import load_workspace, save_workspace
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'ANALIZER_SETTINGS_DIR': directory+'/settings',
                'ANALIZER_OUTPUT_DIR': directory+'/outputs'}):
            window = AdvancedStudioWindow()
            try:
                self.assertNotIn('Report title', window.report_metadata())
                window.engineering.session['metadata'].update({
                    'Observations': 'Measured speed ripple', 'Conclusions': 'Review with test plan',
                    'Recommended actions': 'Repeat at matched load', 'custom': {'kept': True}})
                saved = Path(directory)/'session.json'
                save_workspace(saved, window.store, [view.state() for view in window.workspaces], window.ui_state())
                window.engineering.session['metadata'] = {}
                window.restore_loaded(*load_workspace(saved))
                self.assertEqual(window.report_metadata()['Conclusions'], 'Review with test plan')
                self.assertEqual(window.report_metadata(engineering=True)['custom'], {'kept': True})
                snapshot = window.report_metadata()
                snapshot['custom']['kept'] = False
                self.assertTrue(window.engineering.session['metadata']['custom']['kept'])
            finally:
                window.close()
                self.app.processEvents()

    def test_cancelled_optional_editor_leaves_shared_details_unchanged(self):
        from app_workbench import AdvancedStudioWindow
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'ANALIZER_SETTINGS_DIR': directory+'/settings',
                'ANALIZER_OUTPUT_DIR': directory+'/outputs'}):
            window = AdvancedStudioWindow()
            try:
                before = deepcopy(window.engineering.session['metadata'])
                with patch.object(ReportDetailsDialog, 'exec', return_value=QtWidgets.QDialog.DialogCode.Rejected):
                    self.assertFalse(window.edit_report_details())
                self.assertEqual(window.engineering.session['metadata'], before)
            finally:
                window.close()
                self.app.processEvents()

    def test_comparison_export_captures_scope_and_shared_notes_before_worker_runs(self):
        from app_channel_store import Channel
        from app_workbench import AdvancedStudioWindow
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'ANALIZER_SETTINGS_DIR': directory+'/settings',
                'ANALIZER_OUTPUT_DIR': directory+'/outputs'}):
            window = AdvancedStudioWindow()
            try:
                channel=window.store.add(Channel('Temperature',[0,1,2],[20,30,40],unit='°C',coordinate_unit='min'))
                window.comparison.assign([channel.id]);window.tabs.setCurrentIndex(1)
                window.engineering.session['metadata']['Conclusions']='Reviewed comparison'
                window.stats_scope.setCurrentText('Whole recording')
                tasks=[]
                with patch.object(QtWidgets.QFileDialog,'getSaveFileName',return_value=(directory+'/report.pdf','PDF plot and cursor summary (*.pdf)')), \
                        patch.object(window,'background',side_effect=lambda work,*a,**kw:tasks.append(work)), \
                        patch('app_reporting.export_report') as export:
                    window.report()
                    self.assertEqual(len(tasks),1)
                    window.engineering.session['metadata']['Conclusions']='later edit'
                    tasks[0]()
                    state=export.call_args.args[2]
                    self.assertEqual(state['report_kind'],'comparison')
                    self.assertEqual(state['workspace_name'],'Comparison')
                    self.assertEqual(state['statistics_scope'],'Whole recording')
                    self.assertEqual(export.call_args.kwargs['metadata']['Conclusions'],'Reviewed comparison')
            finally:
                window.close();self.app.processEvents()

    def test_engineering_preview_never_labels_frequency_cursors_as_minutes(self):
        from app_channel_store import Channel
        from app_engineering_reports import report_preview
        from app_workbench import AdvancedStudioWindow
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'ANALIZER_SETTINGS_DIR': directory+'/settings',
                'ANALIZER_OUTPUT_DIR': directory+'/outputs'}):
            window = AdvancedStudioWindow()
            dialog=None
            try:
                channel=window.store.add(Channel('Spectrum',[1,2,3],[4,8,2],unit='W',coordinate_kind='frequency',coordinate_unit='Hz'))
                window.dashboard.assign([channel.id])
                window.dashboard.active.cursor_lines[0].setValue(1.5)
                window.dashboard.active.cursor_lines[1].setValue(2.5)
                with patch('app_engineering_reports.report_preview',wraps=report_preview) as preview:
                    dialog=window.engineering.report()
                    self.assertEqual(preview.call_args.kwargs['view']['cursors'],[])
                    self.assertEqual(preview.call_args.kwargs['view']['cursor_locks'],[])
                    self.assertIn('no time-coordinate',preview.call_args.kwargs['view']['cursor_context_reason'])
                    self.assertIs(preview.call_args.kwargs['store'],window.store)
            finally:
                if dialog is not None:dialog.close()
                window.close();self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
