"""Native real-GUI old-to-new updater acceptance for all three Windows payloads.

Use only a disposable CI runner. The harness drives the production transaction
function against actual, pinned prior application processes; it does not claim
that an immutable older release already contained the new updater UI. Only the
new application's restored-workspace acknowledgement establishes success.
"""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app_update_launcher import launch_transaction
from app_update_transaction import file_hash
from app_updates import RELEASES, asset_name, require_matching_edition, restart_environment
from app_version import VERSION
from scripts.check_installer import registration, previous_runtime, invoke
from scripts.build_installer import compile_installer

OLD_EXE_SHA='aa44ecba22bbb3ca69f971a4a548bfcdcb0947fced49f296d5abc428a833eebe'
OLD_EXE_SIZE=154533203


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


def checked_download_old_exe(destination):
    destination=Path(destination)
    with urllib.request.urlopen(RELEASES+'/download/v2.3.2/ApplianceSignalStudio.exe',timeout=90) as response,destination.open('wb') as output:
        shutil.copyfileobj(response,output)
    if destination.stat().st_size!=OLD_EXE_SIZE or file_hash(destination)!=OLD_EXE_SHA:
        raise ValueError('Pinned prior EXE failed verification')
    return destination


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
        old_bundle=previous_runtime(base);old_exe=checked_download_old_exe(base/'previous-onefile.exe')
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
        old_setup=compile_installer(old_bundle,'2.3.1','ci-update-old',legacy=True)
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
                    current=install/'versions/2.3.1/ApplianceSignalStudio.exe';download=bad_setup if case=='health-failure' else setup
                elif kind=='portable-zip':
                    current_root=case_root/'Application';shutil.copytree(old_bundle,current_root)
                    current=current_root/'ApplianceSignalStudio.exe';download=ROOT/'dist/ApplianceSignalStudio_Portable.zip'
                else:
                    current=case_root/'ApplianceSignalStudio.exe';shutil.copy2(old_exe,current)
                    download=ROOT/'dist/ApplianceSignalStudio.exe'
                before=file_hash(current);all_runtimes.append(current)
                old=subprocess.Popen([str(current),'--restore',str(recovery)],env=restart_environment())
                wait_gui(current)
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
                        assert VERSION in wait_gui(target)[0][2]
                        close_gui(target)
                    else:
                        assert outcome['status']=='recovered-previous',outcome
                        if kind!='installer':assert file_hash(current)==before,outcome
                        assert '2.3.' in wait_gui(current)[0][2]
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
    result={'ok':True,'version':VERSION,'platform':'native Windows actual GUI', 'checks':checks,
            'limitations':['Harness invokes production updater with an actual prior GUI PID; immutable prior versions did not yet have the new updater UI.',
                           'Previous immutable runtime has no restoration acknowledgement protocol; fallback GUI survival and recovery snapshot load are checked separately.',
                           'Installed late-failure fallback restarts previous runtime; full registration/shortcut rollback requires rerunning previous official Setup.',
                           'Manual wheel/keyboard/DPI/multi-monitor and external corporate networks remain separate checks.']}
    (ROOT/'build/application_updates_smoke_report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)
    return result


if __name__=='__main__':check()
