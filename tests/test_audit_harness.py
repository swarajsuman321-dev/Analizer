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
from app_release_acceptance import AcceptanceRecorder, MANUAL_WINDOWS_CHECKS, REQUIRED_CHECK_IDS, isolated_environment
from scripts.check_packaged_workflows import REQUIRED_CATEGORIES, capture_runtime, validate_packaged_report
from tools.audit_user_workflows import observe_processing


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
