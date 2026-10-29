"""A killed native check must retain its identity and last real progress stage."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from app_release_acceptance import AcceptanceRecorder, acceptance_stack_diagnostics, _acceptance_stack_snapshot


class AcceptanceDiagnosticsTests(unittest.TestCase):
    def test_check_identity_and_stage_are_on_disk_before_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = AcceptanceRecorder(Path(directory)/'acceptance.json')

            def operation():
                current = json.loads(recorder.path.read_text())
                self.assertEqual(current['current_check'], 'slow-export')
                self.assertTrue(current['check_started_at_utc'])
                self.assertEqual(current['checks'], [])
                recorder.stage('Writing complete workbook')
                current = json.loads(recorder.path.read_text())
                self.assertEqual(current['current_stage'], 'Writing complete workbook')
                self.assertTrue(current['stage_updated_at_utc'])
                return True

            self.assertEqual(recorder.check('slow-export', operation, 'exports')['status'], 'passed')

    def test_repeated_progress_does_not_rewrite_report(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = AcceptanceRecorder(Path(directory)/'acceptance.json')
            with patch.object(recorder, 'save') as save:
                recorder.stage('Writing complete workbook')
                recorder.stage('Writing complete workbook')
            save.assert_called_once()

    def test_real_stack_snapshot_and_watchdog_shutdown_on_error(self):
        with tempfile.TemporaryDirectory() as directory:
            captured = threading.Event()
            def snapshot(path):
                _acceptance_stack_snapshot(path)
                captured.set()
            with patch('app_release_acceptance._acceptance_stack_snapshot', side_effect=snapshot):
                with self.assertRaisesRegex(RuntimeError, 'failed'):
                    with acceptance_stack_diagnostics(Path(directory), interval=.01) as watcher:
                        self.assertTrue(captured.wait(5), 'The actual diagnostic thread did not capture a snapshot')
                        self.assertTrue(watcher.is_alive())
                        raise RuntimeError('failed')
                self.assertFalse(watcher.is_alive())
            text = (Path(directory)/'acceptance-stacks.txt').read_text()
            self.assertIn('Snapshot at ', text)
            self.assertIn('MainThread', text)
            self.assertIn('test_real_stack_snapshot_and_watchdog_shutdown_on_error', text)

    def test_snapshot_failure_is_diagnostic_and_does_not_interrupt_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            attempted = threading.Event()
            def fail_snapshot(path):
                attempted.set()
                raise RuntimeError('Diagnostic frame unavailable')
            with patch('app_release_acceptance._acceptance_stack_snapshot', side_effect=fail_snapshot):
                with acceptance_stack_diagnostics(Path(directory), interval=.01) as watcher:
                    self.assertTrue(attempted.wait(5))
                    recorder = AcceptanceRecorder(Path(directory)/'acceptance.json')
                    recorder.check('real-check', lambda: 42, 'example')
                    self.assertTrue(recorder.finish()['ok'])
                self.assertFalse(watcher.is_alive())
            text = (Path(directory)/'acceptance-stacks.txt').read_text()
            self.assertIn('Diagnostic snapshot failed: RuntimeError', text)


if __name__ == '__main__':
    unittest.main()
