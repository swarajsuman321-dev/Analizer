"""Distribution isolation, verified Setup updates and user-data preservation."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_dual_distribution_updates import workspace,native_restart_stub
from app_installation import installed_root
from app_updates import RELEASES,INSTALLER_MANIFEST_URL,validate_manifest,check_latest,import_offline_update,launch_installer


def package(body=b'setup'):
    return {'version':'2.3.3','kind':'installer','url':RELEASES+'/download/v2.3.3/ApplianceSignalStudio-Setup-2.3.3.exe',
            'size':len(body),'sha256':hashlib.sha256(body).hexdigest()}


class InstallerTests(unittest.TestCase):
    def test_only_marked_versioned_frozen_runtime_is_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);version=root/'versions/2.3.2';version.mkdir(parents=True)
            exe=version/'ApplianceSignalStudio.exe';marker=version/'installed-layout.json'
            with patch('sys.platform','win32'),patch('sys.frozen',True,create=True),patch('sys.executable',str(exe)):
                self.assertIsNone(installed_root())
                marker.write_text(json.dumps({'product':'Appliance Signal Studio','schema':1,'kind':'installed'}))
                self.assertEqual(installed_root(),root.resolve())
                marker.write_text('{broken');self.assertIsNone(installed_root())

    def test_installed_outputs_use_documents_and_override_is_preserved(self):
        from app_output import output_directory
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('app_installation.installed_root',return_value=root/'Programs'),patch('PySide6.QtCore.QStandardPaths.writableLocation',return_value=str(root/'Documents')),patch.dict(os.environ,{'ANALIZER_OUTPUT_DIR':''}):
                self.assertEqual(output_directory(),root/'Documents/SignalStudio_Output')
                with patch.dict(os.environ,{'ANALIZER_OUTPUT_DIR':str(root/'my-results')}):self.assertEqual(output_directory(),root/'my-results')

    def test_installed_lifecycle_never_deletes_installer_owned_versions(self):
        from app_lifecycle import finalize_installation
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('sys.platform','win32'),patch('sys.frozen',True,create=True),patch('app_lifecycle.installation_roots',return_value=[root]),patch('app_lifecycle.settings_directory',return_value=root),patch('app_installation.installed_root',return_value=root),patch('app_lifecycle.migrate_user_files'),patch('app_lifecycle.cleanup_inventory') as cleanup:
                finalize_installation();cleanup.assert_not_called();self.assertEqual(json.loads((root/'lifecycle.json').read_text())['mode'],'installer-managed')

    def test_installer_manifest_cannot_redirect_to_other_payload(self):
        self.assertEqual(validate_manifest(package())['kind'],'installer')
        for edits in ({'url':RELEASES+'/download/v2.3.3/ApplianceSignalStudio.exe'},{'kind':'zip'},{'size':0},{'sha256':'bad'}):
            with self.assertRaises(ValueError):validate_manifest({**package(),**edits})

    def test_installed_update_checks_the_installer_feed(self):
        response=io.BytesIO(json.dumps(package()).encode())
        with patch('app_installation.installed_root',return_value=Path('/installed')),patch('app_updates.request',return_value=response) as request:
            self.assertEqual(check_latest()['kind'],'installer');request.assert_called_once_with(INSTALLER_MANIFEST_URL)

    def test_offline_setup_is_verified_without_replacing_portable_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();manifest=source/'installer-update.json'
            manifest.write_text(json.dumps(package()));exe=source/'ApplianceSignalStudio-Setup-2.3.3.exe';exe.write_bytes(b'setup')
            data,target=import_offline_update(manifest,root/'cache');self.assertEqual(data['kind'],'installer');self.assertIn('Setup',target.name)
            exe.write_bytes(b'bad')
            with self.assertRaises(ValueError):import_offline_update(manifest,root/'cache')
            self.assertEqual(target.read_bytes(),b'setup')

    def test_installed_application_refuses_single_exe_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);download=root/'setup.exe';download.write_bytes(b'setup')
            with patch('sys.platform','win32'),patch('sys.frozen',True,create=True),patch('app_installation.installed_root',return_value=root),patch('app_updates.subprocess.Popen') as launch:
                with self.assertRaisesRegex(ValueError,'Setup package'):launch_installer(download,root/'restore.json',root,package()['sha256'])
                launch.assert_not_called()

    def test_setup_update_script_keeps_complete_previous_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);download=root/'setup.exe';download.write_bytes(b'setup')
            install=root/"User's App";old=install/'versions/2.3.2/ApplianceSignalStudio.exe'
            old.parent.mkdir(parents=True);old.write_bytes(b'previous-runtime');recovery=workspace(root/'snapshot')
            with patch('sys.platform','win32'),patch('sys.frozen',True,create=True),patch('sys.executable',str(old)),patch('app_installation.installed_root',return_value=install),patch('subprocess.CREATE_NO_WINDOW',0x08000000,create=True),patch('app_update_launcher.subprocess.Popen') as launch:
                launch_installer(download,recovery,root,package()['sha256'],manifest=package())
                script=next((root/'transactions').rglob('install-setup-update.ps1')).read_text(encoding='utf-8-sig')
                self.assertIn("User''s App",script);self.assertIn('System.Security.Cryptography.SHA256',script);self.assertIn('$setup.ExitCode',script)
                self.assertIn("@('/VERYSILENT', '/SUPPRESSMSGBOXES', '/SP-', '/NORESTART'",script)
                self.assertNotIn("'/SILENT'",script)
                self.assertIn('setup-install.log',script)
                self.assertNotIn('Move-Item',script);self.assertIn('FilePath $previous',script);self.assertIn('Start-AndConfirm',script)
                self.assertEqual(launch.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'],'1')
                self.assertEqual(launch.call_args.kwargs['creationflags'],subprocess.CREATE_NO_WINDOW)

    @unittest.skipUnless(sys.platform=='win32','Native installed-update transaction is exercised on Windows CI')
    def test_native_setup_success_and_failure_restart_correct_runtime(self):
        from app_updates import ps_quote
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);download=root/'setup.exe';download.write_bytes(b'setup');install=root/"User's App"
            old=install/'versions/2.3.2/ApplianceSignalStudio.exe';new=install/'versions/2.3.3/ApplianceSignalStudio.exe'
            for file in (old,new):file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'runtime')
            recovery=workspace(root/'snapshot')
            for fail in (False,True):
                with patch('sys.frozen',True,create=True),patch('sys.executable',str(old)),patch('app_installation.installed_root',return_value=install),patch('app_update_launcher.subprocess.Popen'):
                    transaction=launch_installer(download,recovery,root,package()['sha256'],manifest=package())
                restart=root/'restart.txt';wrapper=root/'exercise.ps1'
                wrapper.write_text(native_restart_stub(restart,fail=fail,setup=True)+". "+ps_quote(transaction['script']),encoding='utf-8-sig')
                result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(wrapper)],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr)
                started=Path(restart.read_text(encoding='utf-8-sig').strip())
                outcome=json.loads((transaction['directory']/'transaction.json').read_text(encoding='utf-8-sig'))
                self.assertTrue(started.samefile(old if fail else new),outcome)
                self.assertEqual(outcome['status'],'recovered-previous' if fail else 'ready',outcome)
                self.assertEqual(old.read_bytes(),b'runtime')
