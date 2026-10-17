import hashlib
import io
import json
from pathlib import Path
import tempfile
import sys
import subprocess
import unittest
from unittest.mock import patch
from app_updates import validate_manifest,version_tuple,download_update,check_latest,RELEASES,ps_quote,import_offline_update,network_hint


def manifest(body=b'example executable',version='2.1.6'):
    return dict(version=version,url=f'{RELEASES}/download/v{version}/ApplianceSignalStudio.exe',size=len(body),sha256=hashlib.sha256(body).hexdigest(),notes='A new feature')


class Response(io.BytesIO):
    def geturl(self):return 'https://release-assets.githubusercontent.com/example'


class UpdateTests(unittest.TestCase):
    def test_stable_versions_and_untrusted_locations(self):
        self.assertGreater(version_tuple('2.1.10'),version_tuple('2.1.9'))
        for bad in ('v2.1.5','2.1.5-beta','../../x',None):
            with self.assertRaises(ValueError):version_tuple(bad)
        for changes in ({'url':'http://example.com/app.exe'},{'url':f'{RELEASES}/download/v2.1.6/other.exe'}, {'size':True},{'size':700*1024*1024},{'sha256':'wrong'}):
            with self.assertRaises(ValueError):validate_manifest(dict(manifest(),**changes))

    def test_check_is_bounded_and_validates_manifest(self):
        with patch('app_updates.request',return_value=Response(json.dumps(manifest()).encode())):
            self.assertEqual(check_latest()['version'],'2.1.6')
        with patch('app_updates.request',return_value=Response(b'x'*(256*1024+1))):
            with self.assertRaises(ValueError):check_latest()

    def test_verified_download_and_corruption_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            progress=[]
            with patch('app_updates.request',return_value=Response(b'example executable')):
                target=download_update(manifest(),directory,progress.append)
            self.assertEqual(target.read_bytes(),b'example executable');self.assertEqual(progress[-1],100)
            for body in (b'corrupted',b'x'*100):
                with patch('app_updates.request',return_value=Response(body)):
                    with self.assertRaises(ValueError):download_update(manifest(),directory)
                self.assertEqual(target.read_bytes(),b'example executable');self.assertFalse(list(Path(directory).glob('*.part')))

    def test_installer_waits_and_keeps_backup_without_shell_interpolation(self):
        from app_updates import launch_installer
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target=root/"User's app.exe";download=root/'download.exe';recovery=root/'my work.json'
            target.write_bytes(b'old');download.write_bytes(b'new')
            with patch('app_updates.sys.platform','win32'),patch('app_updates.sys.frozen',True,create=True),patch('app_updates.sys.executable',str(target)),patch('app_updates.subprocess.CREATE_NO_WINDOW',0,create=True),patch('app_updates.subprocess.Popen') as launch:
                launch_installer(download,recovery,root,hashlib.sha256(b'new').hexdigest())
                args=launch.call_args.args[0];self.assertEqual(args[0],'powershell.exe');self.assertNotIn('shell',launch.call_args.kwargs)
                script=(root/'install-update.ps1').read_text(encoding='utf-8-sig')
                self.assertIn("User''s app.exe",script);self.assertIn('Wait-Process',script);self.assertIn('System.Security.Cryptography.SHA256',script);self.assertIn('Move-Item -LiteralPath $backup -Destination $target',script)
                self.assertEqual(target.read_bytes(),b'old')
                download.write_bytes(b'tampered')
                with self.assertRaises(ValueError):launch_installer(download,recovery,root,hashlib.sha256(b'new').hexdigest())
                self.assertEqual(launch.call_count,1)

    @unittest.skipUnless(sys.platform=='win32','Native PowerShell transaction is tested on Windows CI')
    def test_native_windows_replacement_and_rollback(self):
        from app_updates import launch_installer
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target=root/"User's app.exe";download=root/'download.exe';recovery=root/'workspace.json';restart=root/'restart.txt'
            def quoted(value):return ps_quote(value)
            for fail in (False,True):
                target.write_bytes(b'old');download.write_bytes(b'new');restart.unlink(missing_ok=True)
                with patch('app_updates.sys.frozen',True,create=True),patch('app_updates.sys.executable',str(target)),patch('app_updates.subprocess.Popen'):
                    launch_installer(download,recovery,root,hashlib.sha256(b'new').hexdigest())
                # Exercise real PowerShell file operations. Stub only process waiting,
                # sleep and restart so CI never replaces or closes its own interpreter.
                wrapper=root/'exercise.ps1'
                wrapper.write_text("function Wait-Process {}\nfunction Start-Sleep {}\n$script:launchCount = 0\nfunction Start-Process { param($FilePath, $ArgumentList)\n$script:launchCount++\n"+("if ($script:launchCount -eq 1) { throw 'Simulated restart failure' }\n" if fail else '')+"Set-Content -LiteralPath "+quoted(restart)+" -Value $FilePath\n}\n. "+quoted(root/'install-update.ps1'),encoding='utf-8-sig')
                result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(wrapper)],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr)
                log=(root/'install.log').read_text(encoding='utf-16') if (root/'install.log').exists() else result.stderr
                self.assertEqual(target.read_bytes(),b'old' if fail else b'new',log)
                self.assertEqual(Path(restart.read_text(encoding='utf-8-sig').strip()).resolve(),target.resolve())
                if fail:self.assertIn('Simulated restart failure',(root/'install.log').read_text(encoding='utf-16'))
                else:self.assertEqual(target.with_suffix('.previous.exe').read_bytes(),b'old')

    def test_windows_proxy_fallback_is_used_only_on_connection_failures(self):
        from app_updates import request, MANIFEST_URL
        import urllib.error
        original = urllib.error.URLError(OSError(11001, 'getaddrinfo failed'))
        with patch('app_updates.sys.platform', 'win32'), \
             patch('app_updates.urllib.request.urlopen', side_effect=original), \
             patch('app_updates._windows_system_request', return_value=Response(b'ok')) as win:
            with request(MANIFEST_URL) as response:
                self.assertEqual(response.read(), b'ok')
            win.assert_called_once_with(MANIFEST_URL)
        with patch('app_updates.sys.platform', 'linux'), \
             patch('app_updates.urllib.request.urlopen', side_effect=original), \
             patch('app_updates._windows_system_request') as win:
            with self.assertRaises(urllib.error.URLError):
                request(MANIFEST_URL)
            win.assert_not_called()
        with patch('app_updates.sys.platform', 'win32'), \
             patch('app_updates.urllib.request.urlopen', side_effect=urllib.error.HTTPError(MANIFEST_URL, 404, 'Not found', {}, None)), \
             patch('app_updates._windows_system_request') as win:
            with self.assertRaises(urllib.error.HTTPError):
                request(MANIFEST_URL)
            win.assert_not_called()

    def test_windows_proxy_response_stream_and_error_handling(self):
        from app_updates import _WindowsProxyResponse, _windows_system_request, MANIFEST_URL
        from unittest.mock import MagicMock
        fake = MagicMock()
        fake.stdout = io.BytesIO(b'binary\x00payload')
        fake.stderr = io.BytesIO(b'')
        fake.poll.return_value = 0
        fake.wait.return_value = 0
        with patch('app_updates.sys.platform', 'win32'), \
             patch('app_updates.subprocess.Popen', return_value=fake) as launch:
            with _windows_system_request(RELEASES + '/latest/download/update.json') as response:
                self.assertEqual(response.read(128), b'binary\x00payload')
                self.assertEqual(response.read(128), b'')
            command = launch.call_args.args[0]
            self.assertIn('-Command', command)
            self.assertNotIn('-EncodedCommand', command)
            script = command[-1]
            self.assertIn('GetSystemWebProxy', script)
            self.assertIn('DefaultNetworkCredentials', script)
            self.assertIn('HTTPS required after redirects', script)
            self.assertNotIn('ExecutionPolicy', script)
        failed = MagicMock()
        failed.stdout = io.BytesIO(b'')
        failed.stderr = io.BytesIO(b'proxy authentication denied')
        failed.wait.return_value = 1
        failed.poll.return_value = 1
        with _WindowsProxyResponse(failed, MANIFEST_URL) as response:
            with self.assertRaisesRegex(OSError, 'proxy authentication denied'):
                response.read(128)
        with self.assertRaises(ValueError):
            _windows_system_request('http://example.com/untrusted.json')

    def test_win_11001_resolution_failure_explained(self):
        message = network_hint('<urlopen error [Errno 11001] getaddrinfo failed>')
        self.assertIn('DNS lookup failed', message)
        self.assertIn('offline update', message)

    def test_corporate_offline_import_verified_and_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            destination = root / 'destination'
            package = manifest(body=b'approved executable', version='2.1.8')
            (source / 'update.json').write_text(json.dumps(package), encoding='utf-8')
            exe = source / 'ApplianceSignalStudio.exe'
            exe.write_bytes(b'approved executable')
            progress = []
            metadata, target = import_offline_update(source / 'update.json', destination, progress.append)
            self.assertEqual(metadata['version'], '2.1.8')
            self.assertEqual(target.read_bytes(), b'approved executable')
            self.assertEqual(progress[-1], 100)
            exe.write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                import_offline_update(source / 'update.json', destination)
            self.assertEqual(target.read_bytes(), b'approved executable')
            self.assertFalse(list(destination.glob('*.part')))

    def test_offline_failure_and_script_escaping(self):
        with patch('app_updates.request',side_effect=OSError('offline')):
            with self.assertRaises(OSError):check_latest()
        self.assertEqual(ps_quote("C:/User's files/$stuff"),"'C:/User''s files/$stuff'")


class InfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_background_check_finishes_and_download_can_cancel(self):
        from app_workbench import AdvancedStudioWindow
        from PySide6 import QtCore,QtTest
        w=AdvancedStudioWindow()
        try:
            with patch('app_info.check_latest',return_value=manifest(version='2.1.10')):
                w.info.check()
                for _ in range(200):
                    self.app.processEvents();QtTest.QTest.qWait(5)
                    if w.info.task is None:break
                self.assertIsNone(w.info.task);self.assertTrue(w.info.install_button.isEnabled())
            with tempfile.TemporaryDirectory() as directory:
                def download(data,path,progress):
                    for _ in range(100):QtCore.QThread.msleep(5);progress(1)
                    return Path(directory)/'update.exe'
                with patch('app_info.download_update',side_effect=download),patch.object(w.info,'update_directory',return_value=Path(directory)):
                    w.info.update();w.info.cancel_download()
                    for _ in range(200):
                        self.app.processEvents();QtTest.QTest.qWait(5)
                        if w.info.task is None:break
                    self.assertIsNone(w.info.task);self.assertIsNone(w.info.download);self.assertIn('cancelled',w.info.status.text())
        finally:w.close();self.app.processEvents()

    def test_info_manuals_and_active_plot_are_independent(self):
        from app_workbench import AdvancedStudioWindow
        from app_version import VERSION
        w=AdvancedStudioWindow()
        try:
            self.assertEqual(w.tabs.count(),2);self.assertEqual(w.info_action.text(),'Info & manual');self.assertIn(VERSION,w.info.manuals)
            self.assertIn('Updates',w.info.manual.toPlainText())
            w.tabs.setCurrentIndex(1);w.show_info();self.assertIs(w.active_workspace,w.comparison);self.assertTrue(w.info_dialog.isVisible())
            w.tabs.setCurrentIndex(0);w.show_info();self.assertIs(w.active_workspace,w.dashboard);self.assertEqual(w.ui_state()['tab'],0)
            w.info.checked(manifest(version='2.1.10'),None);self.assertTrue(w.info.install_button.isEnabled())
            w.info.checked(manifest(version=VERSION),None);self.assertIn('latest',w.info.status.text())
            w.info.checked(None,'offline');self.assertIn('Could not check',w.info.status.text())
            w.info.versions.setCurrentText('2.1.4');self.assertIn('Actuator interpretation',w.info.manual.toPlainText())
        finally:w.close();self.app.processEvents()
