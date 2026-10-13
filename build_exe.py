"""Build and check native Windows executables in a dedicated virtual environment."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

PROJECT = Path(__file__).resolve().parent
BUILD = PROJECT / 'build'
DIST = PROJECT / 'dist'


def run(command, *, env=None):
    BUILD.mkdir(exist_ok=True)
    print('\nRunning: ' + subprocess.list2cmdline([str(v) for v in command]), flush=True)
    with (BUILD / 'build.log').open('a', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=PROJECT, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        for line in process.stdout:
            print(line, end='', flush=True)
            log.write(line)
        result = process.wait()
    if result:
        raise RuntimeError(f'Command exited with {result}. See build/build.log.')


def check_bundle(executable, mode):
    report = BUILD / f'{mode}_smoke_report.json'
    report.unlink(missing_ok=True)
    process = subprocess.run([str(executable), '--self-test', '--report', str(report)],
                             cwd=executable.parent, timeout=180, capture_output=True, text=True)
    if not report.exists():
        raise RuntimeError(f'{mode} EXE did not write its self-test report (exit {process.returncode}). '
                           'Run build_debug.bat to diagnose the startup error.')
    data = json.loads(report.read_text(encoding='utf-8'))
    if process.returncode or not data.get('ok'):
        raise RuntimeError(f'{mode} EXE failed its self-test. See {report}.')
    print(f'{mode} EXE self-test passed.', flush=True)


def build(mode):
    env = dict(os.environ, ANALYZER_BUILD_MODE=mode)
    destination = DIST if mode == 'onefile' else DIST / mode
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
         '--workpath', str(BUILD / mode), '--distpath', str(destination),
         str(PROJECT / 'ApplianceSignalStudio.spec')], env=env)
    executable = (destination / 'ApplianceSignalStudio.exe' if mode == 'onefile'
                  else destination / 'ApplianceSignalStudio' / 'ApplianceSignalStudio.exe')
    if not executable.is_file():
        raise RuntimeError(f'Expected executable was not created: {executable}')
    check_bundle(executable, mode)
    return executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('both', 'onedir', 'onefile', 'debug'), default='both')
    parser.add_argument('--skip-install', action='store_true', help='Use already-installed build dependencies.')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.exit(1, 'Build this project on Windows. PyInstaller cannot generate a Windows EXE from Linux.\n')
    if platform.python_implementation() != 'CPython' or sys.maxsize <= 2**32:
        parser.exit(1, 'Use standard 64-bit CPython, preferably Python 3.12.\n')
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        parser.exit(1, 'Use Python 3.11, 3.12 or 3.13. Python 3.12 is the reviewed runtime.\n')
    if sys.prefix == sys.base_prefix:
        parser.exit(1, 'Double-click build_windows.bat to build inside the dedicated virtual environment.\n')
    BUILD.mkdir(exist_ok=True)
    (BUILD / 'build.log').write_text('Appliance Signal Studio Windows build\n', encoding='utf-8')
    try:
        if not args.skip_install:
            run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'])
            run([sys.executable, '-m', 'pip', 'install', '--only-binary=:all:',
                 '-r', str(PROJECT / 'requirements-build.txt')])
        run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
        # Reuse the supplied code-based logo; data/results are never embedded.
        if not (PROJECT / 'app_icon.ico').exists() or not (PROJECT / 'app_logo.png').exists():
            run([sys.executable, str(PROJECT / 'generate_logo.py')])
        modes = ('onedir', 'onefile') if args.mode == 'both' else (args.mode,)
        for mode in modes:
            executable = build(mode)
            print(f'Created and checked: {executable}', flush=True)
        if 'onedir' in modes:
            with zipfile.ZipFile(DIST / 'ApplianceSignalStudio_Portable.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
                folder = DIST / 'onedir' / 'ApplianceSignalStudio'
                for path in sorted(folder.rglob('*')):
                    if path.is_file():
                        archive.write(path, path.relative_to(folder.parent))
        print('\nSUCCESS. Keep the one-folder bundle intact when using the portable version.')
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f'\nBUILD FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
