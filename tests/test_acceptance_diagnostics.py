"""A killed native check must retain its identity and last real progress stage."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_release_acceptance import AcceptanceRecorder, acceptance_stack_diagnostics


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

    def test_stack_watchdog_is_cancelled_on_error_before_file_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('app_release_acceptance.faulthandler.dump_traceback_later') as start, \
                    patch('app_release_acceptance.faulthandler.cancel_dump_traceback_later') as stop:
                with self.assertRaisesRegex(RuntimeError, 'failed'):
                    with acceptance_stack_diagnostics(Path(directory)):
                        handle = start.call_args.kwargs['file']
                        self.assertFalse(handle.closed)
                        start.assert_called_once_with(120, repeat=True, file=handle)
                        raise RuntimeError('failed')
                stop.assert_called_once_with()
                self.assertTrue(handle.closed)
            self.assertTrue((Path(directory)/'acceptance-stacks.txt').is_file())


if __name__ == '__main__':
    unittest.main()
