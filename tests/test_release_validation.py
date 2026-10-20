"""Public release evidence must describe actual native gate results faithfully."""
import json
from pathlib import Path
import tempfile
import unittest

from app_release_acceptance import MANUAL_WINDOWS_CHECKS, REQUIRED_CHECK_IDS
from scripts.release_validation import REPORT_FILES, assemble_validation, unit_test_evidence


class ReleaseValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build, self.dist = self.root/'build', self.root/'dist'
        self.build.mkdir()
        self.dist.mkdir()
        self.version = '2.4.0'
        self.sha = 'a'*40
        self.reports = {}
        for name in REPORT_FILES:
            report = {'ok': True, 'version': self.version}
            if name in REPORT_FILES[:3]:
                report.update(frozen=True, modern={'qt_gui_checked': True})
            elif name == 'packaged_workflows_smoke_report.json':
                report.update(editions={edition: {'checks': len(REQUIRED_CHECK_IDS), 'passed': len(REQUIRED_CHECK_IDS),
                    'unmet': 0, 'unrun': 0, 'runner_errors': 0, 'application_callback_errors': 0}
                    for edition in ('standalone-onefile', 'standalone-folder', 'installed')},
                    manual_checks_unrun=list(MANUAL_WINDOWS_CHECKS))
            else:
                report.update(platform='native Windows actual GUI', checks=['observed successful native operation'],
                              limitations=['A real limitation preserved from the native report'])
            self.reports[name] = report
            self.write(name, report)
        for filename in ('ApplianceSignalStudio.exe', 'ApplianceSignalStudio_Portable.zip',
                         f'ApplianceSignalStudio-Setup-{self.version}.exe'):
            (self.dist/filename).write_bytes(b'unit-test artifact identity only; not an executable')

    def write(self, name, report):
        (self.build/name).write_text(json.dumps(report), encoding='utf-8')

    def assemble(self, **kwargs):
        return assemble_validation(self.build, self.dist, source_sha=self.sha,
                                   version=self.version, environment={}, **kwargs)

    def test_original_reports_commit_hashes_and_manual_limits_are_preserved(self):
        (self.build/'build.log').write_text('Ran 391 tests in 153.252s\n\nOK\nPyInstaller output follows\n', encoding='utf-8')
        path, record = self.assemble()
        self.assertEqual(path.name, 'validation-v2.4.0.json')
        self.assertEqual(record['source_commit'], self.sha)
        self.assertEqual(record['native_unit_tests']['tests_run'], 391)
        self.assertEqual(record['native_unit_tests']['skipped'], 0)
        self.assertEqual(set(record['native_gate_reports']), set(REPORT_FILES))
        for name, report in self.reports.items():
            self.assertEqual(record['native_gate_reports'][name]['report'], report)
        self.assertEqual(record['manual_checks_unrun'], MANUAL_WINDOWS_CHECKS)
        self.assertEqual(json.loads(path.read_text()), record)
        self.assertEqual(len(record['artifacts']), 3)
        self.assertIn('A real limitation preserved from the native report', record['limitations'])

    def test_cache_suite_log_takes_precedence_and_absent_count_is_not_invented(self):
        unavailable = unit_test_evidence(self.build)
        self.assertEqual(unavailable['status'], 'unavailable')
        self.assertIsNone(unavailable['tests_run'])
        (self.build/'build.log').write_text('Ran 1 test in 0.1s\n\nOK\n')
        (self.build/'native-unit-tests.log').write_text('Ran 392 tests in 172.1s\n\nOK (skipped=2, expected failures=1)\n')
        observed = unit_test_evidence(self.build)
        self.assertEqual(observed['source_log'], 'native-unit-tests.log')
        self.assertEqual((observed['tests_run'], observed['skipped'], observed['expected_failures']), (392, 2, 1))

    def test_failed_or_incomplete_native_test_summary_stops_publication(self):
        for terminal in ('FAILED (failures=1)', ''):
            with self.subTest(terminal=terminal):
                (self.build/'build.log').write_text('Ran 20 tests in 1.0s\n\n'+terminal+'\n')
                with self.assertRaises(ValueError):
                    self.assemble()

    def test_missing_unsuccessful_stale_and_source_smoke_reports_are_rejected(self):
        name = REPORT_FILES[0]
        for changed in (None, {'ok': False, 'version': self.version},
                        {'ok': True, 'version': '2.3.2'},
                        {'ok': True, 'version': self.version, 'frozen': False, 'modern': {'qt_gui_checked': True}}):
            with self.subTest(report=changed):
                if changed is None:
                    (self.build/name).unlink()
                else:
                    self.write(name, changed)
                with self.assertRaises((FileNotFoundError, ValueError)):
                    self.assemble()
        self.write(name, self.reports[name])

    def test_missing_edition_unrun_contract_and_wrong_source_commit_are_rejected(self):
        name = 'packaged_workflows_smoke_report.json'
        for issue in ('missing', 'unrun'):
            report = json.loads(json.dumps(self.reports[name]))
            if issue == 'missing':
                report['editions'].pop('installed')
            else:
                report['editions']['installed']['unrun'] = 1
            self.write(name, report)
            with self.assertRaises(ValueError):
                self.assemble()
        self.write(name, self.reports[name])
        with self.assertRaises(ValueError):
            assemble_validation(self.build, self.dist, source_sha=self.sha,
                                version=self.version, environment={'GITHUB_SHA': 'b'*40})


if __name__ == '__main__':
    unittest.main()
