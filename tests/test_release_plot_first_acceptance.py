"""The new finite packaged contracts are executable against the real Qt app."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_release_acceptance import (AcceptanceRecorder, PLOT_FIRST_CHECK_IDS,
                                    REQUIRED_CHECK_IDS, isolated_environment,
                                    _run_plot_first_acceptance)


class PlotFirstExecutableAcceptanceTests(unittest.TestCase):
    def test_all_new_contracts_exercise_actual_gui_and_saved_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            recorder = AcceptanceRecorder(output/'acceptance.json')
            callbacks = []
            with isolated_environment(output), patch('sys.excepthook',
                    side_effect=lambda kind, value, tb: callbacks.append(str(value))):
                _run_plot_first_acceptance(recorder, output/'workflows')
            result = recorder.finish(required_checks=PLOT_FIRST_CHECK_IDS)
            self.assertTrue(PLOT_FIRST_CHECK_IDS <= REQUIRED_CHECK_IDS)
            self.assertEqual(len(result['checks']), len(PLOT_FIRST_CHECK_IDS))
            self.assertEqual(callbacks, [])
            self.assertTrue(result['ok'], [row for row in result['checks'] if row['status'] != 'passed'])
            self.assertTrue((output/'workflows/cursor-free.png').is_file())
            self.assertTrue((output/'workflows/three-signals.pdf').is_file())
            self.assertTrue((output/'workflows/three-signals.xlsx').is_file())
