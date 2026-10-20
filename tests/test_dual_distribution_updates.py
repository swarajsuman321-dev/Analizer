"""Edition isolation, complete runtime staging and real-startup acknowledgements."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from app_installation import distribution_kind
from app_update_launcher import stage_folder
from app_update_transaction import create_request, acknowledge_startup
from app_updates import RELEASES, ZIP_MANIFEST_URL, asset_name, check_latest, require_matching_edition


def workspace(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root/'arrays.npz').write_bytes(b'preserved-array-snapshot')
    path = root/'workspace.json'
    path.write_text(json.dumps({'version':1,'arrays':'arrays.npz','channels':[],'datasets':[],'views':[],'ui':{}}))
    return path


def package(kind='portable', body=b'new', version='2.3.3'):
    value = {'version':version,'kind':kind,'size':len(body),'sha256':hashlib.sha256(body).hexdigest()}
    value['url'] = f'{RELEASES}/download/v{version}/{asset_name(value)}'
    return value


def native_restart_stub(restart, *, fail=False, setup=False):
    """Fake processes only; native PS still performs all hash/rename operations.

    Full actual-app restart coverage lives in scripts/check_application_updates.py.
    """
    from app_updates import ps_quote
    return f'''function Wait-Process {{}}
function Start-Sleep {{}}
$script:launchCount = 0
function Get-Process {{ param($Id) return [pscustomobject]@{{Path=$target}} }}
function Start-Process {{ param($FilePath,$ArgumentList,[switch]$Wait,[switch]$PassThru)
    if ($env:PYINSTALLER_RESET_ENVIRONMENT -ne '1' -or (Test-Path Env:_PYI_APPLICATION_HOME_DIR) -or (Test-Path Env:_MEIPASS2)) {{ throw 'Stale runtime environment at restart' }}
    if ($Wait) {{ return [pscustomobject]@{{ExitCode={1 if fail and setup else 0}}} }}
    $script:launchCount++
    {"if ($script:launchCount -eq 1) { throw 'Simulated restart failure' }" if fail and not setup else ''}
    Set-Content -LiteralPath {ps_quote(restart)} -Value $FilePath -Encoding UTF8
    if ($PassThru) {{
        $ack = @{{schema=1;token=$request.token;version=$request.version;executable=$target;recovery=$recovery;files=$request.files;status='ready';pid=42}}
        $ack | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $request.ack -Encoding UTF8
        $process = [pscustomobject]@{{HasExited=$false;Id=42}}
        Add-Member -InputObject $process -MemberType ScriptMethod -Name Refresh -Value {{}}
        return $process
    }}
}}
'''


class DistributionUpdatesTests(unittest.TestCase):
    def test_onefile_waits_for_same_executable_bootloader_only(self):
        from app_update_transaction import update_wait_pids
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);exe=root/'Application.exe';exe.write_bytes(b'app')
            other=root/'python.exe';other.write_bytes(b'caller')
            with patch('sys.platform','win32'),patch('sys.frozen',True,create=True),patch('sys.executable',str(exe)),patch('app_installation.distribution_kind',return_value='portable'),patch('app_update_transaction.os.getpid',return_value=123),patch('app_update_transaction.os.getppid',return_value=100),patch('app_update_transaction._windows_process_image',return_value=exe) as image:
                self.assertEqual(update_wait_pids(),[123,100]);image.assert_called_once_with(100)
                image.return_value=other;self.assertEqual(update_wait_pids(),[123])
                image.return_value=None;self.assertEqual(update_wait_pids(),[123])
                image.reset_mock()
                with patch('app_installation.distribution_kind',return_value='portable-zip'):
                    self.assertEqual(update_wait_pids(),[123]);image.assert_not_called()
                with patch('sys.frozen',False):
                    self.assertEqual(update_wait_pids(),[123]);image.assert_not_called()

    def test_cancelling_staging_removes_partial_runtime_without_changing_source(self):
        from app_operation_context import operation_context
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'runtime.zip';source=root/'source.csv';source.write_text('original')
            with zipfile.ZipFile(archive,'w') as bundle:
                bundle.writestr('ApplianceSignalStudio/ApplianceSignalStudio.exe',b'executable')
                bundle.writestr('ApplianceSignalStudio/_internal/python312.dll',b'dll')
            cancel=threading.Event()
            def progress(stage,_):
                if stage=='Staging standalone runtime':cancel.set()
            with operation_context(cancel,progress):
                with self.assertRaises(InterruptedError):stage_folder(archive,root,hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertFalse(list(root.glob('.signalstudio-stage-*')))
            self.assertEqual(source.read_text(),'original')

    def test_invalid_startup_request_is_rejected_without_escaping_event_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);request=root/'request.json'
            request.write_text('{not-json')
            self.assertFalse(acknowledge_startup(True,argv=['app','--update-request',str(request)]))
            self.assertFalse(acknowledge_startup(True,argv=['app','--update-request']))

    def test_runtime_destination_preflight_does_not_schedule_or_change_files(self):
        from app_update_launcher import launch_transaction
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);exe=root/'app.exe';exe.write_bytes(b'old');download=root/'new.exe';download.write_bytes(b'new')
            recovery=workspace(root/'snapshot')
            with patch('sys.executable',str(exe)),patch('app_update_launcher.tempfile.TemporaryFile',side_effect=PermissionError('read only')),patch('app_update_launcher.subprocess.Popen') as spawn:
                with self.assertRaisesRegex(ValueError,'writable folder'):launch_transaction(download,recovery,root/'updates',package())
            spawn.assert_not_called();self.assertEqual(exe.read_bytes(),b'old');self.assertFalse((root/'updates').exists())

    def test_overlapping_cache_download_cancel_preserves_other_verified_payload(self):
        from app_updates import download_update
        class Response(io.BytesIO):
            def geturl(self):return 'https://release-assets.githubusercontent.com/runtime.zip'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);first=package('portable-zip',b'cancelled');second=package('portable-zip',b'kept')
            def progress(_):
                download_update(second,root)
                raise InterruptedError('cancel this instance only')
            with patch('app_updates.request',side_effect=[Response(b'cancelled'),Response(b'kept')]):
                with self.assertRaises(InterruptedError):download_update(first,root,progress)
            self.assertEqual((root/'ApplianceSignalStudio_Portable.zip').read_bytes(),b'kept')
            self.assertFalse(list(root.glob('*.part')))

    def test_real_packaging_identity_ignores_leftover_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'_internal').mkdir()
            with patch('sys.frozen',True,create=True), patch('sys.executable',str(root/'App.exe')), patch('app_installation.installed_root',return_value=None):
                with patch('sys._MEIPASS',str(root/'temporary-extraction'),create=True):
                    self.assertEqual(distribution_kind(),'portable')
                with patch('sys._MEIPASS',str(root/'_internal'),create=True):
                    self.assertEqual(distribution_kind(),'portable-zip')
            with patch('app_installation.installed_root',return_value=root):
                self.assertEqual(distribution_kind(),'installer')

    def test_all_cross_edition_update_conversions_are_rejected(self):
        for current in ('installer','portable','portable-zip'):
            with patch('app_installation.distribution_kind',return_value=current):
                for incoming in ('installer','portable','portable-zip'):
                    if current==incoming:self.assertEqual(require_matching_edition(package(incoming))['kind'],incoming)
                    else:
                        with self.assertRaisesRegex(ValueError,'changes edition'):require_matching_edition(package(incoming))

    def test_folder_feed_and_backward_compatible_exe_manifest(self):
        with patch('app_installation.distribution_kind',return_value='portable-zip'),patch('app_updates.request',return_value=io.BytesIO(json.dumps(package('portable-zip')).encode())) as request:
            self.assertEqual(check_latest()['kind'],'portable-zip');request.assert_called_once_with(ZIP_MANIFEST_URL)
        old=package();old.pop('kind')
        with patch('app_installation.distribution_kind',return_value='portable'):
            self.assertEqual(require_matching_edition(old),old)

    def test_whole_zip_staging_keeps_all_runtime_files_and_adjacent_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'runtime.zip';source=root/'source.csv';source.write_text('original')
            with zipfile.ZipFile(archive,'w') as bundle:
                bundle.writestr('ApplianceSignalStudio/ApplianceSignalStudio.exe',b'new-executable')
                bundle.writestr('ApplianceSignalStudio/_internal/python312.dll',b'new-dll')
                bundle.writestr('ApplianceSignalStudio/_internal/profiles/test.json',b'{}')
            staged=stage_folder(archive,root,hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual((staged/'_internal/python312.dll').read_bytes(),b'new-dll')
            self.assertEqual(len(json.loads((staged/'runtime-inventory.json').read_text())),3)
            self.assertEqual(source.read_text(),'original')

    def test_zip_slip_links_case_aliases_and_extra_payloads_rejected(self):
        bad_sets=[['../outside'],['ApplianceSignalStudio/_internal/../../outside'],
                  ['ApplianceSignalStudio/_internal/C:/bad'],['ApplianceSignalStudio/_internal/NUL.txt'],
                  ['ApplianceSignalStudio/_internal/a.'],['ApplianceSignalStudio/source.csv'],
                  ['ApplianceSignalStudio/_internal/A.dll','ApplianceSignalStudio/_internal/a.dll']]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for names in bad_sets:
                archive=root/'bad.zip'
                with zipfile.ZipFile(archive,'w') as bundle:
                    for name in names:bundle.writestr(name,b'x')
                with self.assertRaises(ValueError):stage_folder(archive,root,hashlib.sha256(archive.read_bytes()).hexdigest())
                self.assertFalse(list(root.glob('.signalstudio-stage-*')))
            archive=root/'link.zip'
            with zipfile.ZipFile(archive,'w') as bundle:
                info=zipfile.ZipInfo('ApplianceSignalStudio/_internal/link');info.external_attr=0o120777<<16;bundle.writestr(info,'elsewhere')
            with self.assertRaises(ValueError):stage_folder(archive,root,hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_ack_requires_live_visible_workbench_expected_version_and_unchanged_snapshot(self):
        from app_version import VERSION
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);recovery=workspace(root/'original');exe=root/'app.exe'
            request,metadata=create_request(root/'transaction',exe,recovery,VERSION,'portable')
            argv=['app','--restore',metadata['recovery'],'--update-request',str(request)]
            window=SimpleNamespace(isVisible=lambda:True,store=SimpleNamespace(channels={'sensor':1},datasets={'run':1}),workspaces=[])
            with patch('sys.executable',str(exe)):
                self.assertTrue(acknowledge_startup(True,argv=argv,window=window))
                ack=json.loads(Path(metadata['ack']).read_text());self.assertEqual(ack['state']['channels'],['sensor']);self.assertEqual(ack['token'],metadata['token'])
                self.assertFalse(acknowledge_startup(False,'bad restore',argv=argv,window=window))
                self.assertIn('bad restore',json.loads(Path(metadata['ack']).read_text())['error'])
                Path(metadata['recovery']).write_text('{}')
                self.assertFalse(acknowledge_startup(True,argv=argv,window=window))
            self.assertEqual(json.loads(recovery.read_text())['arrays'],'arrays.npz')
            self.assertIsNone(acknowledge_startup(True,argv=['app'],window=window))

    def test_standalone_finalize_keeps_other_editions_and_rollback_executables(self):
        from app_lifecycle import finalize_installation
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);exe=root/'current.exe';exe.write_bytes(b'new');backup=root/'ApplianceSignalStudio.previous.exe';backup.write_bytes(b'old')
            # winreg is used only to record the current location on real Windows;
            # stop immediately after the data-preserving records are written.
            with patch('sys.platform','win32'),patch('sys.frozen',True,create=True),patch('sys.executable',str(exe)),patch('app_lifecycle.installation_roots',return_value=[root,root/'other-edition']),patch('app_lifecycle.settings_directory',return_value=root),patch('app_installation.installed_root',return_value=None),patch('app_lifecycle.migrate_user_files'),patch('app_lifecycle.cleanup_inventory') as cleanup:
                with patch.dict('sys.modules',{'winreg':MagicMock()}):finalize_installation()
                cleanup.assert_not_called();self.assertEqual(backup.read_bytes(),b'old')


if __name__=='__main__':unittest.main()
