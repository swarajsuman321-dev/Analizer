"""Native disposable install/upgrade/rollback/uninstall checks, for Windows CI.

Run only on an isolated Windows build agent. Refuses to touch an existing
installation. Previous-version test files are never included in release assets.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_installer import compile_installer
from app_version import VERSION

UNINSTALL_KEY=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A63EB095-928B-4A47-943A-E0C289DA916C}_is1'
OLD_ZIP_SHA256='7115b6f7d8de15d2db1a8efc4e3f3469ed6b7b68aaa1c97dca6eaae91c29d2b8'


def registration():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,UNINSTALL_KEY) as key:
            return {name:winreg.QueryValueEx(key,name)[0] for name in ('DisplayVersion','InstallLocation')}
    except FileNotFoundError:return None


def invoke(exe,args,log,expect_success=True):
    from app_updates import ps_quote
    # Inno's uninstaller can copy itself to a temporary child process. Waiting
    # only for the original PID can race registry/file assertions and cleanup.
    arguments=subprocess.list2cmdline([str(arg) for arg in args])
    command=("$ErrorActionPreference = 'Stop'; $p = Start-Process -FilePath "+ps_quote(exe)+
             ' -ArgumentList '+ps_quote(arguments)+' -Wait -PassThru; exit $p.ExitCode')
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],timeout=240)
    if expect_success and result.returncode:
        detail=log.read_text(encoding='utf-8-sig',errors='replace')[-4000:] if log.exists() else 'No installer log'
        raise RuntimeError(f'{exe.name} returned {result.returncode}: {detail}')
    return result.returncode


def previous_runtime(destination):
    """Pin the official previous ZIP by digest; reject unsafe archive paths."""
    archive=destination/'previous.zip'
    with urllib.request.urlopen('https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.3.1/ApplianceSignalStudio_Portable.zip',timeout=90) as response,archive.open('wb') as output:
        import shutil
        shutil.copyfileobj(response,output)
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=OLD_ZIP_SHA256:raise ValueError('Previous runtime checksum mismatch')
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if not (destination/name).resolve().is_relative_to(destination.resolve()):raise ValueError('Unsafe previous runtime archive')
        bundle.extractall(destination)
    return destination/'ApplianceSignalStudio'


def check(legacy_only=False):
    version='2.3.1' if legacy_only else VERSION
    if sys.platform!='win32':raise RuntimeError('Use an isolated native Windows CI runner')
    if registration():raise RuntimeError('Refusing to modify an existing user installation')
    checks=[];setup=ROOT/'dist'/f'ApplianceSignalStudio-Setup-{version}.exe'
    with tempfile.TemporaryDirectory(prefix="Signal Studio O'Brien Ω ",ignore_cleanup_errors=True) as folder:
        root=Path(folder);install=root/'Installed App';settings=root/'settings';results=root/'reports'
        if legacy_only:setup=compile_installer(previous_runtime(root),'2.3.1','ci-legacy-engine',legacy=True)
        settings.mkdir();results.mkdir()
        # Environment overrides apply to installed children, not machine-wide settings.
        os.environ['ANALIZER_SETTINGS_DIR']=str(settings);os.environ['ANALIZER_OUTPUT_DIR']=str(results)
        saved=settings/'user-template.json';saved.write_text('{"keep":"template"}')
        report=results/'measurement.csv';report.write_text('time,value\n0,42\n')
        log=root/'setup.log'
        arguments=['/VERYSILENT','/SUPPRESSMSGBOXES','/SP-','/NORESTART','/TASKS=desktopicon',f'/DIR={install}',f'/LOG={log}']
        def install_package(package,success=True):return invoke(package,arguments,log,success)
        def remove():invoke(install/'unins000.exe',['/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/LOG={root / "uninstall.log"}'],root/'uninstall.log')
        def preserved():
            assert saved.read_text()=='{"keep":"template"}'
            assert report.read_text()=='time,value\n0,42\n'
        def runtime_check(version):
            output=root/'installed-check.json';output.unlink(missing_ok=True)
            exe=install/'versions'/version/'ApplianceSignalStudio.exe'
            invoke(exe,['--self-test' if legacy_only else '--installation-check','--report',str(output)],log)
            data=json.loads(output.read_text(encoding='utf-8'));assert data['ok'] and data['version']==version
            if legacy_only:return
            assert Path(data['installed_root']).resolve()==install.resolve()
            assert Path(data['runtime_directory']).resolve()==(exe.parent/'_internal').resolve()
        shortcut=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Appliance Signal Studio.lnk'
        utf8="$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
        desktop_result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',utf8+"[Environment]::GetFolderPath('Desktop')"],capture_output=True,text=True,encoding='utf-8',check=True)
        desktop=Path(desktop_result.stdout.strip())/'Appliance Signal Studio.lnk'
        def shortcut_target():
            from scripts.windows_shortcut import shortcut_target as read_target
            return read_target(shortcut)
        try:
            print('PHASE: install/repair',flush=True)
            install_package(setup);runtime_check(version);preserved()
            assert registration()['DisplayVersion']==version
            assert desktop.is_file(),f'Desktop shortcut missing: {desktop}; Start shortcut exists: {shortcut.exists()}'
            actual_target=shortcut_target();expected_target=(install/'versions'/version/'ApplianceSignalStudio.exe').resolve()
            assert actual_target==expected_target,f'Shortcut target={actual_target!s}; expected={expected_target!s}; shortcut={shortcut!s}'
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,UNINSTALL_KEY):raise AssertionError('Unexpected machine-wide installation')
            except FileNotFoundError:pass
            checks.append('fresh per-user install, runtime imports, user-only registration and Unicode path')
            import app_installation
            app_installation.hold_application_mutex()
            try:
                assert install_package(setup,False)!=0,'Setup ignored a running application'
                assert registration()['DisplayVersion']==version
            finally:
                import ctypes
                from ctypes import wintypes
                close=ctypes.windll.kernel32.CloseHandle;close.argtypes=[wintypes.HANDLE]
                close(app_installation._mutex_handle);app_installation._mutex_handle=None
            checks.append('running-app mutex prevents concurrent installation')
            print('PHASE: install/repair',flush=True)
            install_package(setup);runtime_check(version);preserved();checks.append('same-version repair')
            user_file=install/'keep-user-file.txt';user_file.write_text('user-owned')
            print('PHASE: uninstall',flush=True)
            remove();assert not registration();preserved();assert user_file.read_text()=='user-owned'
            assert not (install/'versions'/version/'ApplianceSignalStudio.exe').exists()
            assert not shortcut.exists() and not desktop.exists()
            checks.append('uninstall removes app files and retains user settings, reports and unowned file')
            if legacy_only:
                print(json.dumps({'ok':True,'scope':'Installer engine on actual v2.3.1 runtime; not final v2.3.2 validation','checks':checks}),flush=True)
                return
            old=compile_installer(previous_runtime(root),'2.3.1','ci-old-setup',legacy=True)
            install_package(old);assert registration()['DisplayVersion']=='2.3.1';preserved()
            install_package(setup);runtime_check(VERSION);preserved()
            assert (install/'versions/2.3.1/ApplianceSignalStudio.exe').is_file()
            checks.append('upgrade from real v2.3.1 runtime preserves settings and previous runtime')
            bad=compile_installer(version='2.3.3',output='ci-failed-setup',fail_health=True)
            code=install_package(bad,False);assert code!=0,'Failed health check incorrectly reported installation success'
            assert registration()['DisplayVersion']==VERSION,'Failed upgrade replaced active registration'
            assert shortcut_target()==(install/'versions'/VERSION/'ApplianceSignalStudio.exe').resolve()
            runtime_check(VERSION);preserved();checks.append('failed-runtime upgrade rollback keeps current version runnable')
            remove();assert not registration();preserved();checks.append('uninstall after upgrade')
        except BaseException:
            import traceback
            traceback.print_exc()
            raise
        finally:
            if registration() and (install/'unins000.exe').exists():remove()
    record={'ok':True,'version':VERSION,'platform':'native Windows x64 CI','checks':checks,
            'limitations':['Runner account is privileged; per-user mode is verified via registry scope, not a separate standard-user login.','Not a clean VM without Python or antivirus certification.','Installer is unsigned; no publisher signing identity was supplied.']}
    (ROOT/'build/installer_smoke_report.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps(record,indent=2))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--legacy-smoke',action='store_true')
    check(legacy_only=parser.parse_args().legacy_smoke)
