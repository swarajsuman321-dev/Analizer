"""A stuck test cannot hide its last output until the entire Windows job expires."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import build_exe


class BoundedBuildPhaseTests(unittest.TestCase):
    def test_hung_test_is_stopped_and_partial_unicode_output_survives(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(build_exe, 'BUILD', Path(directory)):
            output = io.StringIO()
            code = ('import sys,time; '
                    'print("last_test_before_hang "+chr(176)+"C",flush=True); '
                    'time.sleep(60)')
            with contextlib.redirect_stdout(output), \
                    patch.object(build_exe, 'stop_process_tree', wraps=build_exe.stop_process_tree) as stopped, \
                    self.assertRaises(subprocess.TimeoutExpired):
                # Allow a cold Windows interpreter to initialize before the
                # intentional hang; this checks supervision, not spawn speed.
                build_exe.run([sys.executable, '-c', code], timeout=5)
            stopped.assert_called_once()
            self.assertIsNotNone(stopped.call_args.args[0].poll())
            self.assertIn('last_test_before_hang °C', output.getvalue())
            self.assertIn('last_test_before_hang °C', (Path(directory)/'build.log').read_text(encoding='utf-8'))

    def test_bounded_phase_retains_real_failure_status_and_existing_log(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(build_exe, 'BUILD', Path(directory)):
            log = Path(directory)/'build.log'
            log.write_text('previous build phase\n', encoding='utf-8')
            output = io.StringIO()
            command = [sys.executable, '-c', 'import sys;print("current failing test");sys.exit(7)']
            with contextlib.redirect_stdout(output), self.assertRaisesRegex(RuntimeError, 'exited with 7'):
                build_exe.run(command, timeout=10)
            self.assertIn('previous build phase\ncurrent failing test\n', log.read_text(encoding='utf-8'))
            self.assertIn('current failing test', output.getvalue())
            self.assertNotIn('previous build phase', output.getvalue())

    def test_windows_timeout_uses_tree_cleanup_before_fallback_kill(self):
        process = Mock(pid=1234)
        process.poll.return_value = None
        with patch.object(build_exe.sys, 'platform', 'win32'), \
                patch.object(build_exe.subprocess, 'run') as taskkill:
            build_exe.stop_process_tree(process)
        taskkill.assert_called_once_with(['taskkill.exe', '/PID', '1234', '/T', '/F'],
                                        timeout=30, capture_output=True, check=False)
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=30)

    def test_failed_windows_tree_cleanup_cannot_defeat_finite_fallback(self):
        process = Mock(pid=1234)
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired('stuck process', 30)
        with patch.object(build_exe.sys, 'platform', 'win32'), \
                patch.object(build_exe.subprocess, 'run', side_effect=OSError('taskkill unavailable')):
            build_exe.stop_process_tree(process)
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=30)


if __name__ == '__main__':
    unittest.main()
