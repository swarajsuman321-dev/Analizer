"""Audit failures and native acceptance evidence must not become false passes."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from app_channel_store import Channel
from app_release_acceptance import AcceptanceRecorder, MANUAL_WINDOWS_CHECKS, REQUIRED_CHECK_IDS, isolated_environment, time_pixel_alignment, viewport_time_x, verify_comparison_interval_metrics
from scripts.check_packaged_workflows import REQUIRED_CATEGORIES, capture_runtime, validate_packaged_report
from tools.audit_user_workflows import observe_processing


class PixelAlignmentDetectorTests(unittest.TestCase):
    """Equal numeric ranges cannot hide a real drawing-gutter displacement."""
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        from PySide6 import QtWidgets
        from app_channel_store import ChannelStore
        from app_plot_workspace import PlotPane
        self.store = ChannelStore()
        channel = self.store.add(Channel('Physical signal', np.arange(101.), np.arange(101.),
                                       unit='°C', coordinate_unit='min'))
        self.window = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout(self.window)
        self.panes = []
        for index in range(4):
            pane = PlotPane(self.store)
            pane.bind([channel.id])
            pane.setMinimumSize(450, 220)
            pane.getAxis('left').setWidth(50+index % 2*40)
            pane.setXRange(20, 80, padding=0)
            self.layout.addWidget(pane, index//2, index % 2)
            self.panes.append(pane)
        self.window.resize(1100, 600)
        self.window.show()
        self.settle()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def settle(self):
        from PySide6 import QtTest
        for _ in range(4):
            self.app.processEvents()
            self.window.grab()
            QtTest.QTest.qWait(10)
        self.app.processEvents()

    def test_uses_floating_global_viewport_mapping_and_independent_grid_columns(self):
        groups = time_pixel_alignment(self.panes, 2)
        self.assertEqual([group['column'] for group in groups], [0, 1])
        self.assertTrue(all(group['maximum_pixel_spread'] <= .5 for group in groups))
        self.assertGreater(viewport_time_x(self.panes[1], 50)-viewport_time_x(self.panes[0], 50), 100)
        position = viewport_time_x(self.panes[0], 43.12345)
        self.assertNotAlmostEqual(position, round(position), places=4)

    def test_equal_time_limits_but_offset_canvas_pixels_fail_acceptance(self):
        self.panes[2].getAxis('left').setWidth(130)
        self.settle()
        np.testing.assert_allclose(self.panes[0].getViewBox().viewRange()[0],
                                   self.panes[2].getViewBox().viewRange()[0], rtol=0, atol=1e-7)
        with self.assertRaisesRegex(AssertionError, 'numeric bounds agree but the drawing gutters do not'):
            time_pixel_alignment(self.panes, 2)


class ProcessingAuditTests(unittest.TestCase):
    def test_cutoff_retry_does_not_turn_irregular_clock_into_runner_error(self):
        irregular = Channel('Observed irregular clock', [0, 1, 1, 2, 4], [1, 2, 3, 4, 5],
                            coordinate_unit='s')
        first = observe_processing(irregular, 'Butterworth low-pass')
        retry = observe_processing(irregular, 'Butterworth low-pass', cutoff=.1)
        later = observe_processing(irregular, 'Descriptive statistics')
        self.assertEqual(first['status'], 'expected_safety_rejection')
        self.assertEqual(retry['status'], 'expected_safety_rejection')
        self.assertEqual(retry['rejection_category'], 'clock')
        self.assertEqual(later['status'], 'passed')
        self.assertEqual(later['samples'], 7)

    def test_regular_clock_invalid_cutoff_remains_parameter_rejection(self):
        channel = Channel('One Hz clock', np.arange(100.), np.sin(np.arange(100.)/10),
                          coordinate_unit='s')
        rejected = observe_processing(channel, 'Butterworth low-pass', cutoff=1)
        corrected = observe_processing(channel, 'Butterworth low-pass', cutoff=.1)
        self.assertEqual(rejected['status'], 'expected_safety_rejection')
        self.assertEqual(rejected['rejection_category'], 'parameters')
        self.assertFalse(rejected['known_clock_or_support_requirement'])
        self.assertEqual(corrected['status'], 'passed')

    def test_unexpected_processing_exception_still_reaches_runner(self):
        def broken(*args, **kwargs):
            raise AttributeError('application callback defect')
        with self.assertRaisesRegex(AttributeError, 'callback defect'):
            observe_processing(None, 'FFT', transform_fn=broken)


class ComparisonEvidenceDetectorTests(unittest.TestCase):
    """Corrupted complete difference evidence cannot inherit a green summary."""
    def evidence(self):
        return {'status': 'compared', 'scope': {'start_min': 0., 'end_min': 3., 'span_min': 3.},
            'metrics': {'compared_duration_min': 2., 'coverage_fraction': 2/3,
                'mean_bias': 1., 'mean_absolute_difference': 1.5,
                'rmse': np.sqrt(8/3), 'max_absolute_difference': 2.},
            'differences': [
                {'start_min': 0., 'end_min': 1., 'duration_min': 1.,
                 'supported': True, 'delta_start': -2., 'delta_end': 2.},
                {'start_min': 1., 'end_min': 2., 'duration_min': 1.,
                 'supported': False, 'delta_start': None, 'delta_end': None},
                {'start_min': 2., 'end_min': 3., 'duration_min': 1.,
                 'supported': True, 'delta_start': 2., 'delta_end': 2.}]}

    def test_sign_crossing_absolute_error_and_gap_use_supported_time_only(self):
        observed = verify_comparison_interval_metrics(self.evidence())
        self.assertEqual(observed['complete_intervals'], 3)
        self.assertEqual(observed['supported_intervals'], 2)
        self.assertEqual(observed['compared_duration_min'], 2.)
        self.assertEqual(observed['mean_absolute_difference'], 1.5)

    def test_missing_or_overlapping_intervals_cannot_pass_complete_evidence(self):
        for change in ('missing', 'overlap', 'unsupported_value'):
            result = self.evidence()
            if change == 'missing':
                result['differences'].pop(1)
            elif change == 'overlap':
                result['differences'][1]['start_min'] = .5
            else:
                result['differences'][1]['delta_start'] = 0.
            with self.subTest(change=change), self.assertRaises(AssertionError):
                verify_comparison_interval_metrics(result)

    def test_summary_numbers_must_agree_with_independent_interval_integration(self):
        for metric in self.evidence()['metrics']:
            result = self.evidence()
            result['metrics'][metric] += .1
            with self.subTest(metric=metric), self.assertRaisesRegex(AssertionError, metric):
                verify_comparison_interval_metrics(result)


class AcceptanceRecorderTests(unittest.TestCase):
    def test_unmet_expected_rejection_runner_error_and_callback_remain_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = AcceptanceRecorder(Path(directory)/'result.json')
            recorder.check('good', lambda: {'value': 42}, 'example')
            def unmet():
                raise AssertionError('The numeric intervals differ')
            recorder.check('contract', unmet, 'example')
            recorder.result['expected_safety_rejections'].append({'message': 'Explicit resampling required'})
            def error():
                raise RuntimeError('Runner initialization failed')
            recorder.check('runner', error, 'example')
            recorder.result['callback_errors'].append({'error': 'Qt callback failed'})
            result = recorder.finish()
            self.assertFalse(result['ok'])
            self.assertEqual(result['summary'], {'checks': 3, 'passed': 1, 'unmet': 1,
                'unrun': 0,
                'runner_errors': 1, 'application_callback_errors': 1,
                'expected_safety_rejections': 1, 'manual_unrun': 5})
            self.assertEqual(json.loads(recorder.path.read_text())['summary'], result['summary'])

    def test_failed_prerequisite_is_unrun_instead_of_a_false_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = AcceptanceRecorder(Path(directory)/'result.json')
            executed = []
            row = recorder.check('dependent', lambda: executed.append(True), 'source', requires=('failed-import',))
            self.assertEqual(row['status'], 'unrun')
            self.assertEqual(row['blocked_by'], ['failed-import'])
            self.assertEqual(executed, [])
            self.assertFalse(recorder.finish()['ok'])

    def test_required_contract_inventory_exposes_unexecuted_work(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = AcceptanceRecorder(Path(directory)/'result.json')
            recorder.check('done', lambda: True, 'example')
            result = recorder.finish(required_checks=('done', 'never-executed'))
            self.assertFalse(result['ok'])
            self.assertEqual(result['summary']['unrun'], 1)
            self.assertEqual(result['checks'][-1]['id'], 'never-executed')

    def test_environment_is_restored_after_error(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'ANALIZER_SETTINGS_DIR': 'existing'}):
            previous_output = os.environ.pop('ANALIZER_OUTPUT_DIR', None)
            try:
                with self.assertRaises(ValueError), isolated_environment(Path(directory)):
                    self.assertEqual(os.environ['ANALIZER_SETTINGS_DIR'], str(Path(directory)/'settings'))
                    raise ValueError('test')
                self.assertEqual(os.environ['ANALIZER_SETTINGS_DIR'], 'existing')
                self.assertNotIn('ANALIZER_OUTPUT_DIR', os.environ)
            finally:
                if previous_output is not None:
                    os.environ['ANALIZER_OUTPUT_DIR'] = previous_output


class PackagedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.exe = Path(self.directory.name)/'real-application.exe'
        self.exe.write_bytes(b'fixture for evidence identity validation; never executed')
        categories = sorted(REQUIRED_CATEGORIES)
        self.rows = [{'id': identity, 'category': categories[index % len(categories)], 'status': 'passed'}
                     for index, identity in enumerate(sorted(REQUIRED_CHECK_IDS))]
        self.report = {'schema': 1, 'frozen': True, 'version': '2.3.3',
                       'executable': str(self.exe), 'edition': 'standalone',
                       'checks': self.rows, 'inputs': [{} for _ in range(4)], 'ok': True,
                       'callback_errors': [], 'runner_errors': [],
                       'distribution_form': 'standalone-folder', 'run_id': 'fresh-invocation',
                       'manual_checks_unrun': list(MANUAL_WINDOWS_CHECKS),
                       'summary': {'checks': len(self.rows), 'passed': len(self.rows)}}

    def validate(self, report):
        return validate_packaged_report(report, executable=self.exe, version='2.3.3', edition='standalone')

    def test_complete_matching_report_accepted(self):
        self.assertIs(self.validate(self.report), self.report)

    def test_source_stub_stale_version_other_edition_and_missing_categories_rejected(self):
        for field, value in [('frozen', False), ('version', '2.3.2'), ('edition', 'installed'),
                             ('checks', self.rows[:-1]), ('inputs', []),
                             ('executable', str(self.exe.parent/'other.exe'))]:
            with self.subTest(field=field):
                altered = copy.deepcopy(self.report)
                altered[field] = value
                with self.assertRaises(ValueError):
                    self.validate(altered)

    def test_crash_replaces_stale_process_logs_with_current_diagnostics(self):
        output = Path(self.directory.name)
        (output/'process-stderr.txt').write_text('old successful invocation')
        code = capture_runtime([sys.executable, '-c', 'import sys; sys.stderr.write("current crash"); sys.exit(3)'],
                               dict(os.environ), output, timeout=10, run_id='current-run')
        self.assertEqual(code, 3)
        self.assertEqual((output/'process-stderr.txt').read_text(), 'current crash')
        result = json.loads((output/'process-result.json').read_text())
        self.assertEqual(result['run_id'], 'current-run')
        self.assertEqual(result['returncode'], 3)
        self.assertFalse(result['timed_out'])

    def test_timed_out_process_is_stopped_and_its_partial_stderr_retained(self):
        output = Path(self.directory.name)
        command = [sys.executable, '-c', 'import sys,time; sys.stderr.write("before timeout"); sys.stderr.flush(); time.sleep(30)']
        with self.assertRaises(subprocess.TimeoutExpired):
            capture_runtime(command, dict(os.environ), output, timeout=2, run_id='timed-out-run')
        self.assertEqual((output/'process-stderr.txt').read_text(), 'before timeout')
        result = json.loads((output/'process-result.json').read_text())
        self.assertTrue(result['timed_out'])
        self.assertIsNotNone(result['returncode'])
        self.assertEqual(result['run_id'], 'timed-out-run')

    def test_hidden_callback_failed_contract_or_incomplete_summary_rejected(self):
        for change in ('callback', 'unmet', 'summary'):
            with self.subTest(change=change):
                altered = copy.deepcopy(self.report)
                if change == 'callback':
                    altered['callback_errors'] = [{'error': 'FFT slot failed'}]
                elif change == 'unmet':
                    altered['checks'][0]['status'] = 'unmet'
                else:
                    altered['summary']['passed'] -= 1
                with self.assertRaises(ValueError):
                    self.validate(altered)

    def test_green_category_labels_cannot_replace_missing_or_duplicate_contracts(self):
        for change in ('missing', 'duplicate'):
            altered = copy.deepcopy(self.report)
            altered['checks'][0]['id'] = ('arbitrary-green-check' if change == 'missing'
                                         else altered['checks'][1]['id'])
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'missing or duplicated'):
                self.validate(altered)

    def test_each_new_quick_analysis_contract_is_mandatory_for_every_packaged_edition(self):
        new_checks = {
            'DEFAULT-PANEL-FOLDS-EXPAND-PRESERVE-READOUT',
            'REAL-TRACE-COLOR-SCOPE-PRESET-EXPORT',
            'REAL-LOADED-DATA-COMPARISON-ISOLATION',
            'REAL-SELECTED-GRAPH-FULLSCREEN-VALUES-RESTORE',
        }
        workspace_comparison_checks = {'REAL-WORKSPACE-FULLSCREEN-SPLITS-HOVER-RESTORE',
                                       'REAL-TWO-SIGNAL-COMPARISON-EVIDENCE'}
        self.assertTrue(new_checks <= REQUIRED_CHECK_IDS)
        # Preserve the entire pre-existing 42-contract release gate.
        original_checks = {
            'REAL-FIXTURE-INTEGRITY-IMPORT', 'ALL-15-FILE-COMBINATIONS',
            'PER-FILE-CHECKBOX-AND-CLOSE-DATASET', 'TDMS-FIRST-REVIEW-REUSE-UNKNOWN-ONLY',
            'SYNTHETIC-SOURCE-EDGE-CASES', 'LOCKED-SAMPLE-MARKER-HUD-EXPORT-RESTORE',
            'GRAPH-HEADER-CONTEXT-SAFE-NATIVE-FFT', 'NON-TEMPORAL-AND-UNLOCKED-INDEPENDENCE',
            'NUMERICAL-UNITS-AND-SAFETY-REJECTIONS',
            'PROCESSING-PREFLIGHT-VALID-DEFAULT-AND-EXPLANATIONS',
            'QT-WHEEL-BOX-KEYBOARD-SHARED-MODES',
            'EXACT-REAL-SOURCE-WORKSPACE-ROUNDTRIP',
            'REAL-INTERVAL-EXPORT-FORMATS-AND-AGREEMENT', 'SOURCE-FILES-UNCHANGED',
        } | {f'LAYOUT-{layout}-{theme}-{width}'
             for layout in ('Single', 'Horizontal split', 'Vertical split', '2×2', 'Stacked', '3 stacked', '10 panels')
             for theme in ('Dark', 'Light') for width in (1024, 1536)}
        self.assertEqual(len(original_checks), 42)
        self.assertEqual(REQUIRED_CHECK_IDS, original_checks | new_checks |
                         {'PERSISTENT-DIALOG-FOLDERS-RESTART-CANCEL-SCOPES'} | workspace_comparison_checks)
        for edition in ('standalone', 'installed'):
            for missing in new_checks | workspace_comparison_checks:
                with self.subTest(edition=edition, missing=missing):
                    altered = copy.deepcopy(self.report)
                    altered['edition'] = edition
                    altered['checks'] = [row for row in altered['checks'] if row['id'] != missing]
                    altered['summary'] = {'checks': len(altered['checks']), 'passed': len(altered['checks'])}
                    with self.assertRaisesRegex(ValueError, 'missing or duplicated'):
                        validate_packaged_report(altered, executable=self.exe, version='2.3.3', edition=edition)

    def test_persistent_dialog_folders_contract_is_mandatory_for_every_packaged_edition(self):
        identity = 'PERSISTENT-DIALOG-FOLDERS-RESTART-CANCEL-SCOPES'
        self.assertIn(identity, REQUIRED_CHECK_IDS)
        self.assertEqual(len(REQUIRED_CHECK_IDS), 49)
        for edition in ('standalone', 'installed'):
            with self.subTest(edition=edition):
                altered = copy.deepcopy(self.report)
                altered['edition'] = edition
                altered['checks'] = [row for row in altered['checks'] if row['id'] != identity]
                altered['summary'] = {'checks': len(altered['checks']), 'passed': len(altered['checks'])}
                with self.assertRaisesRegex(ValueError, 'missing or duplicated'):
                    validate_packaged_report(altered, executable=self.exe, version='2.3.3', edition=edition)

    def test_old_invocation_wrong_packaging_and_hidden_manual_limits_rejected(self):
        for field, value in [('run_id', 'stale-run'), ('distribution_form', 'standalone-onefile'),
                             ('manual_checks_unrun', [])]:
            altered = copy.deepcopy(self.report)
            altered[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_packaged_report(altered, executable=self.exe, version='2.3.3', edition='standalone',
                                         form='standalone-folder', run_id='fresh-invocation')

    def test_fixture_digest_and_successful_source_import_are_required(self):
        fixtures = [{'role': str(index), 'filename': f'{index}.csv', 'bytes': 10, 'sha256': str(index)*64}
                    for index in range(4)]
        self.report['inputs'] = [{**item, 'channels': 1, 'source_rows': [10]} for item in fixtures]
        validate_packaged_report(self.report, executable=self.exe, version='2.3.3', edition='standalone',
                                 fixtures=fixtures)
        for field, value in [('sha256', 'changed-source'), ('channels', 0), ('source_rows', [])]:
            altered = copy.deepcopy(self.report)
            altered['inputs'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_packaged_report(altered, executable=self.exe, version='2.3.3', edition='standalone',
                                         fixtures=fixtures)


if __name__ == '__main__':
    unittest.main()
