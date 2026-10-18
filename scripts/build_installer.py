"""Compile the per-user Setup EXE from a previously smoke-checked onedir build."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app_version import VERSION


def compiler():
    candidates = [shutil.which('ISCC.exe')]
    for key in ('ProgramFiles(x86)','ProgramFiles'):
        if os.environ.get(key):
            candidates.append(str(Path(os.environ[key])/'Inno Setup 6'/'ISCC.exe'))
    for path in candidates:
        if path and Path(path).is_file():return Path(path)
    raise RuntimeError('Install Inno Setup 6.3 or later, then retry. Windows CI includes Inno Setup.')


def compile_installer(payload=None,version=VERSION,output=None,fail_health=False,legacy=False):
    payload=Path(payload or ROOT/'dist/onedir/ApplianceSignalStudio').resolve()
    if not (payload/'ApplianceSignalStudio.exe').is_file() or not (payload/'_internal').is_dir():
        raise ValueError('Build and test the complete one-folder runtime first')
    output=output or f'ApplianceSignalStudio-Setup-{version}'
    command=[str(compiler()),f'/DAppVersion={version}',f'/DPayloadDir={payload}',f'/DOutputBase={output}']
    if fail_health:command.append('/DFailHealthCheck=1')
    if legacy:command.append('/DHealthArguments=--self-test')
    command.append(str(ROOT/'installer/ApplianceSignalStudio.iss'))
    subprocess.run(command,cwd=ROOT,check=True)
    result=ROOT/'dist'/f'{output}.exe'
    if not result.is_file():raise RuntimeError('Setup compiler did not produce the installer')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-script',action='store_true',help='Compile a disposable stub to validate Setup syntax before expensive builds')
    args=parser.parse_args()
    if sys.platform!='win32':parser.error('Build the installer on Windows')
    if args.check_script:
        with tempfile.TemporaryDirectory(prefix='installer-syntax-') as directory:
            payload=Path(directory);(payload/'ApplianceSignalStudio.exe').write_bytes(b'compiler-input-only; never installed')
            (payload/'_internal').mkdir()
            result=compile_installer(payload=payload,output='ci-syntax-only')
            result.unlink()
        print('Installer script syntax passed; disposable stub was not installed.')
    else:
        print(compile_installer())
