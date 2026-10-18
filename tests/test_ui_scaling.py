"""Each scale uses a new process because Qt caches display scaling at startup."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ScalingTests(unittest.TestCase):
    def test_three_qt_scaling_levels(self):
        script=Path(__file__).resolve().parents[1]/'scripts/check_ui_scaling.py'
        with tempfile.TemporaryDirectory() as root:
            for scale in ('1','1.25','1.5'):
                with self.subTest(scale=scale):
                    env={**os.environ,'QT_SCALE_FACTOR':scale,'ANALIZER_OUTPUT_DIR':root,'ANALIZER_SETTINGS_DIR':root}
                    result=subprocess.run([sys.executable,str(script)],env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertIn('"dialogs": "passed"',result.stdout)
