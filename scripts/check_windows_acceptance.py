"""Run the real recording workflows inside every actual Windows distribution.

This is a disposable CI command, not an end-user installer action. It refuses
to touch an existing registered installation and uninstalls only its own Setup.
The folder check extracts the public ZIP artifact instead of reusing its build
input, so an incomplete ZIP cannot pass using an intact build directory.
"""
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def check():
    if sys.platform!='win32':raise RuntimeError('Run packaged acceptance on native Windows')
    from app_version import VERSION
    from scripts.check_installer import registration,invoke
    from scripts.check_packaged_workflows import check as check_workflows
    if registration():raise RuntimeError('Refusing to replace an existing registered installation')
    build=ROOT/'build';build.mkdir(exist_ok=True)
    output=build/'packaged-acceptance';output.mkdir(exist_ok=True)
    samples=ROOT/'tests/samples/recordings';dist=ROOT/'dist'
    results={}
    results['standalone-onefile']=check_workflows(dist/'ApplianceSignalStudio.exe',samples,output/'onefile',edition='standalone',form='standalone-onefile')
    with tempfile.TemporaryDirectory(prefix='Signal acceptance ',dir=build,ignore_cleanup_errors=True) as temporary:
        scratch=Path(temporary);folder=scratch/'extracted'
        with zipfile.ZipFile(dist/'ApplianceSignalStudio_Portable.zip') as archive:
            for member in archive.infolist():
                destination=(folder/member.filename).resolve()
                if not destination.is_relative_to(folder.resolve()):raise ValueError('Unsafe portable ZIP member')
            archive.extractall(folder)
        runtimes=list(folder.rglob('ApplianceSignalStudio.exe'))
        if len(runtimes)!=1:raise ValueError('Portable ZIP must contain one workbench executable')
        results['standalone-folder']=check_workflows(runtimes[0],samples,output/'folder',edition='standalone',form='standalone-folder')
        target=scratch/'installed';setup=dist/f'ApplianceSignalStudio-Setup-{VERSION}.exe'
        try:
            invoke(setup,['/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/DIR={target}',f'/LOG={output / "install.log"}'],output/'install.log')
            registered=registration()
            if not registered:raise RuntimeError('Acceptance installation did not register')
            runtime=target/'versions'/VERSION/'ApplianceSignalStudio.exe'
            results['installed']=check_workflows(runtime,samples,output/'installed',edition='installed',form='installed')
        finally:
            uninstaller=target/'unins000.exe'
            if uninstaller.exists():invoke(uninstaller,['/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/LOG={output / "uninstall.log"}'],output/'uninstall.log')
        if registration():raise RuntimeError('Acceptance installation was not removed completely')
    summary={'version':VERSION,'ok':True,'editions':{key:value['summary'] for key,value in results.items()},
             'manual_checks_unrun':next(iter(results.values())).get('manual_checks_unrun',[])}
    (build/'packaged_workflows_smoke_report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary));return summary


if __name__=='__main__':check()
