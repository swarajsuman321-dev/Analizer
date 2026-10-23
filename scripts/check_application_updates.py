"""Native real-GUI old-to-new updater acceptance for all three Windows payloads.

Use only a disposable CI runner. The harness drives the production transaction
function against actual, pinned prior application processes. It does not click
the previous binary's update UI. Only the new application's restored-workspace
acknowledgement establishes success.
"""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app_update_launcher import launch_transaction
from app_update_transaction import file_hash
from app_updates import RELEASES, asset_name, require_matching_edition, restart_environment
from app_version import VERSION
from scripts.check_installer import registration, invoke
from scripts.build_installer import compile_installer

PRIOR_VERSION='2.4.0'
PRIOR_ARTIFACTS={
    'portable':{'name':'ApplianceSignalStudio.exe','size':154719110,
                'sha256':'02f5e3fd99a84c23c48d04b86d895060149e21392e9c67b9da5ea1d9af937683'},
    'portable-zip':{'name':'ApplianceSignalStudio_Portable.zip','size':155478250,
                    'sha256':'8b167df6001da26b1b3911ce5a046e6ce57d90a6c21bae98cd76252318070849'},
    'installer':{'name':'ApplianceSignalStudio-Setup-2.4.0.exe','size':134769948,
                 'sha256':'a71c5cc7de7ba5fa3efaf55ccc6148fe49f0f39972b4a52616c6aa15ab5894eb'},
}


def manifest(path,kind):
    result={'version':VERSION,'kind':kind,'size':path.stat().st_size,'sha256':file_hash(path)}
    result['url']=f'{RELEASES}/download/v{VERSION}/{asset_name(result)}'
    return result


def windows_for(executable):
    """Find real visible top-level workbenches by Unicode process image path."""
    user=ctypes.windll.user32;kernel=ctypes.windll.kernel32
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    found=[];expected=os.path.normcase(str(Path(executable).resolve()))
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def visit(hwnd,_):
        if not user.IsWindowVisible(hwnd):return True
        title=ctypes.create_unicode_buffer(1024);user.GetWindowTextW(hwnd,title,1024)
        if not title.value.startswith('Appliance Signal Studio'):return True
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        handle=kernel.OpenProcess(0x1000,False,pid.value)
        if not handle:return True
        try:
            image=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(image))
            if kernel.QueryFullProcessImageNameW(handle,0,image,ctypes.byref(size)) and os.path.normcase(str(Path(image.value).resolve()))==expected:
                found.append((hwnd,pid.value,title.value))
        finally:kernel.CloseHandle(handle)
        return True
    user.EnumWindows(callback(visit),0)
    return found


def wait_gui(exe,timeout=90):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        windows=windows_for(exe)
        if windows:return windows
        time.sleep(.2)
    raise AssertionError('Actual workbench window did not become visible: '+str(exe))


def close_gui(exe):
    post=ctypes.windll.user32.PostMessageW
    post.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    post.restype=wintypes.BOOL
    for hwnd,_,_ in windows_for(exe):post(hwnd,0x0010,0,0)
    deadline=time.monotonic()+15
    while windows_for(exe) and time.monotonic()<deadline:time.sleep(.1)
    for _,pid,_ in windows_for(exe):subprocess.run(['taskkill.exe','/PID',str(pid),'/T','/F'],check=False,capture_output=True)


def make_workspace(path):
    import numpy as np
    import pandas as pd
    from PySide6 import QtWidgets
    from app_channel_store import Channel,Dataset
    from app_workbench import AdvancedStudioWindow
    from app_workspace_io import save_workspace
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window=AdvancedStudioWindow()
    dataset=Dataset('Update recovery measurement',pd.DataFrame({'Time':[0,60,120,180],'Pressure':[0,250,500,100]}),'retained-source.csv')
    window.store.datasets[dataset.id]=dataset
    channel=Channel('Recovery Pressure',np.array([0,1,2,3]),np.array([0,250,500,100]),'Pa',coordinate_unit='min',dataset_id=dataset.id)
    window.store.add(channel);window.dashboard.assign([channel.id])
    pane=window.dashboard.active
    pane.cursor_lines[0].setValue(1);pane.cursor_lines[1].setValue(2)
    pane.cursor_locks[0]={'channel':channel.id,'index':1}
    save_workspace(path,window.store,[w.state() for w in window.workspaces],window.ui_state())
    expected={'channels':[channel.id],'datasets':[dataset.id],'views':[w.state() for w in window.workspaces]}
    window.close();app.processEvents()
    return expected


def checked_download_prior(kind,destination):
    """Read a bounded, immutable official artifact and verify its pinned bytes."""
    expected=PRIOR_ARTIFACTS[kind]
    destination=Path(destination)
    part=destination.with_name(destination.name+'.part')
    count=0;digest=hashlib.sha256()
    try:
        url=f'{RELEASES}/download/v{PRIOR_VERSION}/{expected["name"]}'
        with urllib.request.urlopen(url,timeout=90) as response,part.open('wb') as output:
            if not response.geturl().startswith('https://'):
                raise ValueError('Pinned prior artifact requires HTTPS')
            while chunk:=response.read(1024*1024):
                count+=len(chunk)
                if count>expected['size']:
                    raise ValueError('Pinned prior '+kind+' exceeds its verified release size')
                output.write(chunk);digest.update(chunk)
        if count!=expected['size'] or digest.hexdigest()!=expected['sha256']:
            raise ValueError('Pinned prior '+kind+' failed verification')
        os.replace(part,destination)
    finally:
        part.unlink(missing_ok=True)
    return destination


def previous_bundle(destination):
    """Extract the verified previous ZIP into a private, traversal-safe root."""
    destination=Path(destination)
    archive=checked_download_prior('portable-zip',destination/'previous-runtime.zip')
    extracted=destination/'previous-runtime';extracted.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        entries=bundle.infolist()
        if len(entries)>30000 or sum(entry.file_size for entry in entries)>2*1024*1024*1024:
            raise ValueError('Pinned prior ZIP exceeds runtime extraction limits')
        seen=set()
        for entry in entries:
            path=Path(entry.filename)
            target=(extracted/path).resolve()
            identity=str(target).casefold()
            if ('\\' in entry.filename or path.is_absolute() or '..' in path.parts
                    or not path.parts or path.parts[0]!='ApplianceSignalStudio'
                    or not target.is_relative_to(extracted.resolve())
                    or stat.S_ISLNK(entry.external_attr>>16) or identity in seen):
                raise ValueError('Unsafe pinned prior ZIP path: '+entry.filename)
            seen.add(identity)
        bundle.extractall(extracted)
    payload=extracted/'ApplianceSignalStudio'
    if not (payload/'ApplianceSignalStudio.exe').is_file() or not (payload/'_internal').is_dir():
        raise ValueError('Pinned prior ZIP is missing its complete runtime')
    return payload


def assert_gui_version(exe,version):
    windows=wait_gui(exe)
    expected=re.compile(r'(?<![\d.])'+re.escape(version)+r'(?![\d.])')
    assert any(expected.search(title) for _,_,title in windows),(version,windows)
    return windows


def check_frozen_wait_identity(base):
    """Observe production PID discovery inside both real current runtimes."""
    results=[]
    for kind,exe in (
            ('portable',ROOT/'dist/ApplianceSignalStudio.exe'),
            ('portable-zip',ROOT/'dist/onedir/ApplianceSignalStudio/ApplianceSignalStudio.exe')):
        report=base/(kind+'-wait-identity.json')
        process=subprocess.Popen([str(exe),'--installation-check','--report',str(report)],env=restart_environment())
        assert process.wait(timeout=120)==0,'Frozen updater identity check did not start: '+str(exe)
        data=json.loads(report.read_text(encoding='utf-8'))
        assert data['ok'] and data['frozen'],data
        assert data['pid'] in data['update_wait_pids'],data
        if kind=='portable':
            # Popen owns the native bootloader. Python executes in its child;
            # the real production updater must wait for both, not just the UI.
            assert data['pid']!=process.pid,data
            assert data['parent_pid']==process.pid,data
            assert set(data['update_wait_pids'])=={data['pid'],process.pid},data
        else:
            assert data['pid']==process.pid,data
            assert data['update_wait_pids']==[process.pid],data
        results.append(kind+': actual frozen updater waits for '+('workbench child and owning onefile bootloader' if kind=='portable' else 'workbench only, excluding unrelated Python launcher'))
    return results


def check():
    if sys.platform!='win32':raise RuntimeError('Run on a disposable native Windows runner')
    if registration():raise RuntimeError('Refusing to replace an existing installed application')
    checks=[]
    with tempfile.TemporaryDirectory(prefix="Signal Update O'Brien Ω ",ignore_cleanup_errors=True) as folder:
        base=Path(folder)
        checks.extend(check_frozen_wait_identity(base))
        old_bundle=previous_bundle(base)
        old_exe=checked_download_prior('portable',base/'previous-onefile.exe')
        old_setup=checked_download_prior('installer',base/PRIOR_ARTIFACTS['installer']['name'])
        settings=base/'settings';outputs=base/'outputs';settings.mkdir();outputs.mkdir()
        os.environ['ANALIZER_SETTINGS_DIR']=str(settings);os.environ['ANALIZER_OUTPUT_DIR']=str(outputs)
        template=settings/'tdms-template.json';template.write_text('{"reviewed":"keep"}')
        source=base/'original-recording.csv';source.write_text('time,value\n0,42\n')
        report=outputs/'user-report.csv';report.write_text('preserve-report')
        recovery=base/'workspace.json';expected=make_workspace(recovery)
        original_hashes={str(p):file_hash(p) for p in (template,source,report,recovery)}
        sibling=base/'Other standalone edition';shutil.copytree(old_bundle,sibling)
        sibling_hash=file_hash(sibling/'ApplianceSignalStudio.exe')
        install=base/'Installed App';install_log=base/'setup.log'
        setup=ROOT/'dist'/f'ApplianceSignalStudio-Setup-{VERSION}.exe'
        bad_setup=compile_installer(version=VERSION,output='ci-update-health-failure',fail_health=True)
        all_runtimes=[]
        try:
            def preserved():
                for path,digest in original_hashes.items():assert file_hash(path)==digest,path
                assert file_hash(sibling/'ApplianceSignalStudio.exe')==sibling_hash

            def exercise(kind,case):
                print(f'UPDATE PHASE: {kind} / {case}',flush=True)
                case_root=base/(kind+'-'+case);case_root.mkdir()
                if kind=='installer':
                    if registration():
                        invoke(install/'unins000.exe',['/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/LOG={install_log}'],install_log)
                    invoke(old_setup,['/VERYSILENT','/SUPPRESSMSGBOXES','/SP-','/NORESTART',f'/DIR={install}',f'/LOG={install_log}'],install_log)
                    current=install/'versions'/PRIOR_VERSION/'ApplianceSignalStudio.exe';download=bad_setup if case=='health-failure' else setup
                elif kind=='portable-zip':
                    current_root=case_root/'Application';shutil.copytree(old_bundle,current_root)
                    current=current_root/'ApplianceSignalStudio.exe';download=ROOT/'dist/ApplianceSignalStudio_Portable.zip'
                else:
                    current=case_root/'ApplianceSignalStudio.exe';shutil.copy2(old_exe,current)
                    download=ROOT/'dist/ApplianceSignalStudio.exe'
                before=file_hash(current);all_runtimes.append(current)
                old=subprocess.Popen([str(current),'--restore',str(recovery)],env=restart_environment())
                assert_gui_version(current,PRIOR_VERSION)
                metadata=manifest(download,kind)
                with patch('sys.executable',str(current)),patch('app_installation.installed_root',return_value=install if kind=='installer' else None):
                    transaction=launch_transaction(download,recovery,case_root/'updates',metadata,parent_pid=old.pid)
                request=json.loads(transaction['request'].read_text())
                if case=='restore-failure':
                    # Damage only the new-version recovery copy. The independent
                    # previous-version snapshot must remain usable for fallback.
                    for path in request['files']:
                        if path.endswith('.npz'):Path(path).write_bytes(b'not-a-valid-npz')
                locked=None
                if case=='locked-runtime':
                    kernel=ctypes.windll.kernel32
                    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
                    kernel.CreateFileW.restype=wintypes.HANDLE
                    # Hold the exact directory the updater must rename. A file
                    # handle alone can permit an ancestor directory rename on
                    # some Windows/filesystem combinations.
                    locked=kernel.CreateFileW(str(current.parent/'_internal'),0x80000000,3,None,3,0x02000000,None)
                    assert locked not in (None,ctypes.c_void_p(-1).value)
                if case=='staging-tamper':
                    staged=next(current.parent.glob('.signalstudio-stage-*'))
                    (staged/'_internal/python312.dll').write_bytes(b'changed-after-verification')
                try:
                    close_gui(current);old.wait(timeout=30)
                    transaction['process'].wait(timeout=240)
                    outcome=json.loads((transaction['directory']/'transaction.json').read_text(encoding='utf-8-sig'))
                    target=Path(request['executable']);all_runtimes.append(target)
                    if case=='success':
                        assert outcome['status']=='ready',outcome
                        ack=json.loads(Path(request['ack']).read_text())
                        assert ack['status']=='ready' and ack['version']==VERSION,ack
                        assert set(ack['state']['channels'])==set(expected['channels'])
                        assert set(ack['state']['datasets'])==set(expected['datasets'])
                        pane=ack['state']['views'][0]['panes'][0]
                        assert pane['ids']==expected['channels']
                        assert pane['cursor_locks'][0]['channel']==expected['channels'][0]
                        assert pane['cursors']==[1,2],pane
                        assert_gui_version(target,VERSION)
                        close_gui(target)
                    else:
                        assert outcome['status']=='recovered-previous',outcome
                        if kind!='installer':assert file_hash(current)==before,outcome
                        assert_gui_version(current,PRIOR_VERSION)
                        if case=='restore-failure':
                            ack=json.loads(Path(request['ack']).read_text())
                            assert ack['status']=='failed',ack
                        fallback=Path(outcome['fallback_recovery'])
                        from app_workspace_io import load_workspace
                        restored,_,_=load_workspace(fallback)
                        assert set(restored.channels)==set(expected['channels'])
                        close_gui(current)
                    preserved()
                    checks.append(kind+' '+case+': actual previous GUI, production transaction, '+('new GUI/version/workspace acknowledgement' if case=='success' else 'failure detected; retained prior GUI and valid independent recovery'))
                finally:
                    if locked:ctypes.windll.kernel32.CloseHandle(locked)
                    for exe in (current,Path(request['executable'])):close_gui(exe)

            for kind in ('portable','portable-zip','installer'):
                for case in ('success','restore-failure'):exercise(kind,case)
            exercise('portable-zip','locked-runtime')
            exercise('portable-zip','staging-tamper')
            exercise('installer','health-failure')
            for current in ('portable','portable-zip','installer'):
                with patch('app_installation.distribution_kind',return_value=current):
                    for incoming in ('portable','portable-zip','installer'):
                        if current!=incoming:
                            try:require_matching_edition(manifest(setup,incoming))
                            except ValueError:pass
                            else:raise AssertionError('Edition conversion was not rejected')
            checks.append('all cross-edition update conversions rejected; original sources/settings/templates/reports and sibling runtime unchanged')
        finally:
            for exe in all_runtimes:close_gui(exe)
            if registration() and (install/'unins000.exe').exists():
                invoke(install/'unins000.exe',['/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/LOG={install_log}'],install_log)
    result={'ok':True,'version':VERSION,'previous_version':PRIOR_VERSION,'platform':'native Windows actual GUI', 'checks':checks,
            'limitations':['Harness invokes the current production updater against actual pinned v'+PRIOR_VERSION+' GUIs; it does not click the previous binary\'s update UI.',
                           'The previous runtime supports acknowledgements, but fallback uses ordinary --restore; its exact-version GUI survival and independent recovery snapshot load are checked separately.',
                           'Installed late-failure fallback restarts previous runtime; full registration/shortcut rollback requires rerunning previous official Setup.',
                           'Manual wheel/keyboard/DPI/multi-monitor and external corporate networks remain separate checks.']}
    (ROOT/'build/application_updates_smoke_report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)
    return result


if __name__=='__main__':check()
