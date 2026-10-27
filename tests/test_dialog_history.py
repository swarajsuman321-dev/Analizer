"""Personal dialog folders survive restarts without retaining selected files."""

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6 import QtCore, QtWidgets

import app_dialog_history as history


class DialogHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.settings = self.root / 'personal settings'
        self.environment = patch.dict(os.environ, {'ANALIZER_SETTINGS_DIR': str(self.settings)})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    @property
    def record_path(self):
        return self.settings / history.HISTORY_FILENAME

    def folder(self, name):
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_record(self, value):
        self.settings.mkdir(exist_ok=True)
        self.record_path.write_text(json.dumps(value), encoding='utf-8')

    def test_persists_unicode_apostrophes_and_only_the_containing_folder(self):
        folder = self.folder("José's 測定 données")
        source = folder / 'private measurement.csv'
        source.write_text('time,power\n0,123456789\n')
        self.assertTrue(history.remember_path('OpenData', source))
        text = self.record_path.read_text(encoding='utf-8')
        record = json.loads(text)
        self.assertEqual(record, {'version': 1, 'last_folder': str(folder),
                                  'folders': {'OpenData': str(folder)}})
        self.assertNotIn(source.name, text)
        self.assertNotIn('123456789', text)
        self.assertEqual(history.start_directory('OpenData'), str(folder))
        self.assertEqual(importlib.reload(history).start_directory('OpenData'), str(folder))

    def test_a_new_process_uses_the_same_personal_history_outside_runtime(self):
        folder = self.folder('my recordings')
        history.remember_path('OpenData', folder)
        runtime = self.folder('replacement runtime')
        result = subprocess.run(
            [sys.executable, '-c',
             'from app_dialog_history import start_directory; print(start_directory("OpenData"))'],
            cwd=runtime, env=dict(os.environ, PYTHONPATH=str(Path(history.__file__).parent)),
            capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(result.stdout.strip(), str(folder))
        self.assertEqual(list(runtime.iterdir()), [])

    def test_each_purpose_keeps_its_folder_and_new_purposes_use_latest(self):
        purposes = ('OpenData', 'WorkspaceOpen', 'WorkspaceSave', 'Export',
                    'EngineeringPower', 'EngineeringMachine', 'EngineeringSimulation',
                    'TdmsTemplates', 'Presets', 'OfflineUpdate')
        folders = {}
        for purpose in purposes:
            folders[purpose] = self.folder(purpose)
            self.assertTrue(history.remember_path(purpose, folders[purpose] / 'selected.json'))
        for purpose, folder in folders.items():
            self.assertEqual(history.start_directory(purpose), str(folder))
        self.assertEqual(history.start_directory('NewWorkflow'), str(folders[purposes[-1]]))

    def test_settings_environment_is_resolved_each_time(self):
        first = self.folder('first')
        second = self.folder('second')
        history.remember_path('OpenData', first)
        with patch.dict(os.environ, {'ANALIZER_SETTINGS_DIR': str(self.root / 'other settings')}):
            self.assertEqual(history.start_directory('OpenData', second), str(second))
            history.remember_path('OpenData', second)
            self.assertEqual(history.start_directory('OpenData'), str(second))
        self.assertEqual(history.start_directory('OpenData'), str(first))

    def test_relative_selected_files_are_made_absolute(self):
        folder = self.folder('relative folder')
        source = folder / 'input.csv'
        source.touch()
        actual = os.getcwd()
        try:
            os.chdir(self.root)
            self.assertTrue(history.remember_path('OpenData', Path('relative folder/input.csv')))
            self.assertTrue(history.remember_path('Export', Path('relative folder/new.csv')))
        finally:
            os.chdir(actual)
        self.assertEqual(history.start_directory('OpenData'), str(folder))
        self.assertEqual(history.start_directory('Export'), str(folder))

    def test_deleted_folder_uses_nearest_existing_parent(self):
        parent = self.folder('recordings')
        folder = self.folder('recordings/moved/nested')
        history.remember_path('OpenData', folder)
        folder.rmdir()
        folder.parent.rmdir()
        self.assertEqual(history.start_directory('OpenData'), str(parent))

    def test_first_use_accepts_fallback_then_defaults_to_documents_or_home(self):
        fallback = self.folder('fallback')
        self.assertEqual(history.start_directory('OpenData', fallback), str(fallback))
        home = self.folder('user home')
        with patch('app_dialog_history.Path.home', return_value=home):
            self.assertEqual(history.start_directory('OpenData'), str(home))
            documents = self.folder('user home/Documents')
            self.assertEqual(history.start_directory('OpenData'), str(documents))
        self.assertFalse(self.record_path.exists())

    def test_invalid_selections_do_not_change_history(self):
        history.remember_path('OpenData', self.folder('valid'))
        previous = self.record_path.read_bytes()
        for invalid in ('', None, 12, b'bytes', 'bad\0name', 'bad\nname', '\ud800',
                        'x' * (history.MAX_PATH_LENGTH + 1)):
            self.assertFalse(history.remember_path('OpenData', invalid))
        for invalid in ('', None, 'bad\0purpose', 'x' * (history.MAX_PURPOSE_LENGTH + 1)):
            self.assertFalse(history.remember_path(invalid, self.root))
        self.assertEqual(self.record_path.read_bytes(), previous)

    def test_foreign_windows_paths_are_not_reinterpreted_as_relative_posix_paths(self):
        if os.name == 'nt':
            self.skipTest('Foreign Windows paths only apply on another OS')
        fallback = self.folder('fallback')
        for path in (r"C:\Users\José's\測定\data.csv", r'\\server\share\data.csv', r'C:relative.csv'):
            self.assertFalse(history.remember_path('OpenData', path))
            self.write_record({'version': 1, 'last_folder': path, 'folders': {'OpenData': path}})
            self.assertEqual(history.start_directory('OpenData', fallback), str(fallback))

    def test_native_windows_drive_and_unc_paths_remain_native(self):
        if os.name != 'nt':
            self.skipTest('Native Windows path rules are covered on Windows CI')
        for value in (r"C:\Users\José's\測定", r'\\server\share\測定'):
            path = history._path(value, absolute_only=True)
            self.assertIsNotNone(path)
            self.assertEqual(str(path), value)

    def test_corrupt_settings_do_not_prevent_dialog_or_change_on_cancel(self):
        fallback = self.folder('fallback')
        for encoded in (b'{broken', b'\xff', b'[]', b'{"version": 123}',
                        b'x' * (history.MAX_HISTORY_BYTES + 1)):
            self.settings.mkdir(exist_ok=True)
            self.record_path.write_bytes(encoded)
            with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=('', 'CSV (*.csv)')) as dialog:
                result = history.open_file(None, 'Open', fallback, 'CSV (*.csv)', purpose='OpenData')
            self.assertEqual(result, ('', 'CSV (*.csv)'))
            self.assertEqual(dialog.call_args.args[2], str(fallback))
            self.assertEqual(self.record_path.read_bytes(), encoded)
        self.assertTrue(history.remember_path('OpenData', fallback))
        self.assertEqual(history.start_directory('OpenData'), str(fallback))

    def test_schema_rejects_unbounded_and_invalid_records(self):
        fallback = self.folder('fallback')
        valid = {'version': 1, 'last_folder': str(fallback), 'folders': {'OpenData': str(fallback)}}
        records = [dict(valid, version=True), dict(valid, version=2),
                   dict(valid, folders=[]), dict(valid, last_folder=None),
                   dict(valid, folders={'OpenData': 'relative/path'}),
                   dict(valid, folders={'OpenData': 123}),
                   dict(valid, folders={'bad\0purpose': str(fallback)}),
                   dict(valid, folders={str(i): str(fallback) for i in range(history.MAX_PURPOSES + 1)})]
        for record in records:
            with self.subTest(record=record):
                self.write_record(record)
                home = self.folder('home')
                with patch('app_dialog_history.Path.home', return_value=home):
                    self.assertEqual(history.start_directory('OpenData'), str(home))

    def test_history_bounds_retain_most_recent_purposes(self):
        folder = self.folder('bounded')
        for i in range(history.MAX_PURPOSES + 3):
            self.assertTrue(history.remember_path(f'Purpose{i}', folder))
        record = json.loads(self.record_path.read_text())
        self.assertEqual(len(record['folders']), history.MAX_PURPOSES)
        self.assertNotIn('Purpose0', record['folders'])
        self.assertIn(f'Purpose{history.MAX_PURPOSES + 2}', record['folders'])

    def test_unwritable_settings_and_failed_atomic_replace_are_nonfatal(self):
        original = self.folder('original')
        other = self.folder('other')
        history.remember_path('OpenData', original)
        previous = self.record_path.read_bytes()
        with patch('app_dialog_history.settings_directory', side_effect=PermissionError('read only')):
            self.assertEqual(history.start_directory('OpenData', other), str(other))
            self.assertFalse(history.remember_path('OpenData', other))
            with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=(str(other / 'data.csv'), 'CSV')):
                self.assertEqual(history.open_file(purpose='OpenData'), (str(other / 'data.csv'), 'CSV'))
        with patch('app_support.os.replace', side_effect=PermissionError('read only')):
            self.assertFalse(history.remember_path('OpenData', other))
        self.assertEqual(self.record_path.read_bytes(), previous)
        self.assertEqual(list(self.settings.glob('.signal-export-*')), [])

    def test_open_wrappers_preserve_qt_arguments_return_values_and_filters(self):
        folder = self.folder('opened')
        source = str(folder / 'data.csv')
        result = (source, 'CSV (*.csv)')
        options = QtWidgets.QFileDialog.Option.DontUseNativeDialog
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=result) as dialog:
            returned = history.open_file(None, 'Read measurement', folder, 'CSV (*.csv)',
                                         'CSV (*.csv)', options, purpose='OpenData')
        self.assertIs(returned, result)
        self.assertEqual(dialog.call_args.args, (None, 'Read measurement', str(folder),
                                                'CSV (*.csv)', 'CSV (*.csv)', options))
        files = ([str(folder / 'a.csv'), str(folder / 'b.csv')], 'CSV (*.csv)')
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileNames', return_value=files) as dialog:
            returned = history.open_files(None, 'Many', filter='CSV (*.csv)',
                                          options=options, purpose='OpenData')
        self.assertIs(returned, files)
        self.assertEqual(dialog.call_args.args[2], str(folder))
        self.assertEqual(dialog.call_args.kwargs['options'], options)

    def test_save_uses_remembered_parent_and_retains_suggested_filename(self):
        folder = self.folder('chosen export folder')
        default = self.folder('application outputs')
        history.remember_path('Export', folder / 'previous.pdf')
        result = (str(folder / 'my export.xlsx'), 'Excel (*.xlsx)')
        with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=result) as dialog:
            returned = history.save_file(None, 'Export', default / 'Suggested report.pdf',
                                         'PDF (*.pdf);;Excel (*.xlsx)', purpose='Export')
        self.assertIs(returned, result)
        self.assertEqual(dialog.call_args.args[2], str(folder / 'Suggested report.pdf'))
        self.assertEqual(dialog.call_args.args[3], 'PDF (*.pdf);;Excel (*.xlsx)')
        self.assertEqual(history.start_directory('Export'), str(folder))
        self.assertNotIn('my export.xlsx', self.record_path.read_text())

    def test_first_export_keeps_output_default_before_remembering_its_own_folder(self):
        recordings = self.folder('raw recordings')
        outputs = self.folder('configured output root')
        chosen = self.folder('chosen report exports')
        history.remember_path('OpenData', recordings)
        with patch.object(QtWidgets.QFileDialog, 'getSaveFileName',
                          return_value=(str(chosen / 'First report.pdf'), 'PDF (*.pdf)')) as dialog:
            history.save_file(None, 'Export', outputs / 'Signal report.pdf',
                              'PDF (*.pdf)', purpose='ExportReport')
        self.assertEqual(dialog.call_args.args[2], str(outputs / 'Signal report.pdf'))
        with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=('', 'PDF (*.pdf)')) as dialog:
            history.save_file(None, 'Export', outputs / 'Signal report.pdf',
                              'PDF (*.pdf)', purpose='ExportReport')
        self.assertEqual(dialog.call_args.args[2], str(chosen / 'Signal report.pdf'))

    def test_directory_wrapper_returns_string_and_remembers_selected_directory(self):
        folder = self.folder('chosen directory')
        with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(folder)) as dialog:
            self.assertEqual(history.choose_directory(None, 'Choose folder', self.root,
                                                       purpose='EngineeringMachine'), str(folder))
        self.assertEqual(dialog.call_args.args, (None, 'Choose folder', str(self.root)))
        self.assertEqual(history.start_directory('EngineeringMachine'), str(folder))

    def test_cancellation_of_every_wrapper_preserves_history_bytes(self):
        original = self.folder('original')
        history.remember_path('OpenData', original)
        previous = self.record_path.read_bytes()
        for wrapper, method, cancelled in (
                (history.open_file, 'getOpenFileName', ('', 'CSV')),
                (history.open_files, 'getOpenFileNames', ([], 'CSV')),
                (history.save_file, 'getSaveFileName', ('', 'PDF')),
                (history.choose_directory, 'getExistingDirectory', '')):
            with self.subTest(method=method), patch.object(QtWidgets.QFileDialog, method, return_value=cancelled):
                self.assertEqual(wrapper(purpose='OpenData'), cancelled)
                self.assertEqual(self.record_path.read_bytes(), previous)


class DialogHistoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        from app_workbench import AdvancedStudioWindow
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {
            'ANALIZER_SETTINGS_DIR': str(self.root / 'settings'),
            'ANALIZER_OUTPUT_DIR': str(self.root / 'outputs')})
        self.environment.start()
        self.errors = []
        self.warning = patch.object(QtWidgets.QMessageBox, 'warning',
                                    side_effect=lambda *args: self.errors.append(args[-1]))
        self.warning.start()
        self.windows = [AdvancedStudioWindow()]

    @property
    def window(self):
        return self.windows[-1]

    def tearDown(self):
        for window in self.windows:
            window.close()
        self.app.processEvents()
        self.app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.warning.stop()
        self.environment.stop()
        self.temporary.cleanup()
        self.assertEqual(self.errors, [])

    def folder(self, name):
        path = self.root / name
        path.mkdir()
        return path

    def test_real_preset_save_and_load_reuse_folders_in_a_new_window(self):
        from app_workbench import AdvancedStudioWindow
        folder = self.folder("User's reusable presets")
        source = folder / 'My channels.json'
        with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=(str(source), 'JSON (*.json)')):
            self.window.studio.save_preset()
        self.assertTrue(source.is_file())
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=(str(source), 'JSON (*.json)')):
            self.window.studio.load_preset()
        self.assertIsNotNone(self.window.studio.pending_preset)
        self.window.close()
        self.windows.append(AdvancedStudioWindow())
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=('', '')) as opened:
            self.window.studio.load_preset()
        self.assertEqual(opened.call_args.args[2:], (str(folder), 'Configurations (*.json *.xml *.ini *.cfg)'))
        with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=('', '')) as saved:
            self.window.studio.save_preset()
        self.assertEqual(saved.call_args.args[2:], (str(folder / 'Channel preset.json'), 'JSON (*.json)'))

    def test_profile_and_engineering_report_keep_independent_folders_and_filters(self):
        profile_open = self.folder('profile imports')
        profile_save = self.folder('profile exports')
        report = self.folder('engineering reports')
        for purpose, folder in (('ProfileOpen', profile_open), ('ProfileSave', profile_save),
                                ('EngineeringReport', report)):
            history.remember_path(purpose, folder)
        setup = self.window.engineering.configure()
        buttons = {button.text(): button for button in setup.findChildren(QtWidgets.QPushButton)}
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=('', '')) as opened:
            buttons['Import Profile'].click()
        self.assertEqual(opened.call_args.args[2:], (str(profile_open), 'JSON (*.json)'))
        with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=('', '')) as saved:
            buttons['Save Profile'].click()
        proposed = self.window.engineering.session['profile']['id'] + '.json'
        self.assertEqual(saved.call_args.args[2:], (str(profile_save / proposed), 'JSON (*.json)'))
        setup.close()
        dialog = self.window.engineering.report()
        generate = next(button for button in dialog.findChildren(QtWidgets.QPushButton)
                        if button.text() == 'Choose Output and Generate')
        with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=('', '')) as saved:
            generate.click()
        self.assertEqual(saved.call_args.args[2:],
                         (str(report / 'Engineering report.pdf'), 'PDF (*.pdf);;Excel (*.xlsx)'))

    def test_offline_update_cancel_reuses_manifest_folder_without_starting_worker(self):
        folder = self.folder('approved updates')
        history.remember_path('OfflineUpdate', folder / 'installer-update.json')
        record = self.root / 'settings' / history.HISTORY_FILENAME
        previous = record.read_bytes()
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=('', '')) as opened:
            self.window.info.import_offline()
        self.assertEqual(opened.call_args.args[2:],
                         (str(folder), 'Update manifests (update.json installer-update.json zip-update.json);;JSON files (*.json)'))
        self.assertIsNone(self.window.info.task)
        self.assertEqual(record.read_bytes(), previous)


if __name__ == '__main__':
    unittest.main()
