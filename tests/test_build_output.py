"""Build failures must preserve Unicode and the real child exit status."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import build_exe


class BuildOutputTests(unittest.TestCase):
    def test_legacy_windows_console_is_configured_for_unicode(self):
        buffer=io.BytesIO();stream=io.TextIOWrapper(buffer,encoding='cp1252')
        with patch.object(build_exe.sys,'stdout',stream):
            build_exe.configure_console();stream.write('Temperature °C · Ω · 阀');stream.flush()
        self.assertEqual(buffer.getvalue().decode('utf-8'),'Temperature °C · Ω · 阀')
        stream.detach()

    def test_unicode_child_output_and_failure_remain_in_log(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(build_exe,'BUILD',Path(directory)):
            capture=io.StringIO()
            # ASCII command text remains valid even under a legacy outer shell.
            code="import sys; print('Temperature '+chr(176)+'C '+chr(937)+' '+chr(38400)); sys.exit(7)"
            with contextlib.redirect_stdout(capture),self.assertRaisesRegex(RuntimeError,'exited with 7'):
                build_exe.run([sys.executable,'-c',code],env={'PYTHONIOENCODING':'cp1252'})
            self.assertIn('Temperature °C Ω 阀',capture.getvalue())
            self.assertIn('Temperature °C Ω 阀',(Path(directory)/'build.log').read_text(encoding='utf-8'))
