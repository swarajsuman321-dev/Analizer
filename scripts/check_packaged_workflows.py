"""Launch the real frozen workbench acceptance CLI for a supported edition.

Use separately for the standalone EXE, extracted standalone ZIP and installed
runtime.  No Python replacement executable or restart stub satisfies this gate.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_release_acceptance import MANUAL_WINDOWS_CHECKS, REQUIRED_CHECK_IDS


REQUIRED_CATEGORIES = {'real_recordings', 'dataset_isolation', 'templates', 'synthetic',
                       'cursor_identity', 'navigation', 'layout_time_modes', 'time_lock',
                       'processing', 'persistence', 'exports'}


def capture_runtime(command, environment, output, *, timeout, run_id):
    """Keep crash/timeout evidence and stop the onefile bootloader's children.

    ``subprocess.run`` kills only its immediate child on timeout.  A surviving
    frozen workbench would keep the application mutex open and make a subsequent
    installer check fail for an unrelated reason.
    """
    stderr_path = output/'process-stderr.txt'
    process_path = output/'process-result.json'
    for path in (stderr_path, process_path):
        path.unlink(missing_ok=True)
    started = time.monotonic()
    process = None
    stderr = b''
    timed_out = False
    error = None
    try:
        process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        try:
            _, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Kill the tree while its original parent is still alive, so Windows
            # can find both a onefile bootloader and its actual Qt application.
            if sys.platform == 'win32':
                try:
                    subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                                   timeout=30, capture_output=True, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            process.kill()
            _, stderr = process.communicate(timeout=30)
            raise
        return process.returncode
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        stderr_path.write_bytes((stderr or b'')[-100_000:])
        process_path.write_text(json.dumps({'run_id': run_id, 'timed_out': timed_out,
            'returncode': process.returncode if process else None,
            'seconds': round(time.monotonic()-started, 3), 'error': error}, indent=2),
            encoding='utf-8')


def validate_packaged_report(report, *, executable, version, edition, form=None, run_id=None, fixtures=None):
    """Reject a source smoke, incomplete run, stale result or partial success."""
    if report.get('schema') != 1 or not report.get('frozen'):
        raise ValueError('Acceptance must execute inside the real frozen application')
    reported = Path(report.get('executable', ''))
    if not reported.is_file() or not reported.samefile(Path(executable)):
        raise ValueError('Acceptance was produced by another executable')
    if report.get('version') != version or report.get('edition') != edition:
        raise ValueError('Acceptance version or distribution edition does not match')
    if form is not None and report.get('distribution_form') != form:
        raise ValueError('Acceptance packaging form does not match the requested runtime')
    if run_id is not None and report.get('run_id') != run_id:
        raise ValueError('Acceptance does not belong to this fresh invocation')
    rows = report.get('checks', [])
    identities = [row.get('id') for row in rows]
    if len(set(identities)) != len(identities) or REQUIRED_CHECK_IDS-set(identities):
        raise ValueError('Required acceptance checks are missing or duplicated')
    if REQUIRED_CATEGORIES-{row.get('category') for row in rows}:
        raise ValueError('Required acceptance categories did not execute')
    if not report.get('ok') or not rows or any(row.get('status') != 'passed' for row in rows):
        raise ValueError('At least one application acceptance contract is unmet')
    if report.get('callback_errors') or report.get('runner_errors'):
        raise ValueError('Acceptance contains application callback or runner errors')
    if len(report.get('inputs', [])) != 4:
        raise ValueError('Acceptance did not use the four real recording fixtures')
    if fixtures is not None:
        fields = ('role', 'filename', 'bytes', 'sha256')
        expected = {tuple(item.get(key) for key in fields) for item in fixtures}
        observed = {tuple(item.get(key) for key in fields) for item in report['inputs']}
        if len(expected) != 4 or observed != expected:
            raise ValueError('Acceptance fixture identity does not match the approved recordings')
        if any(not isinstance(item.get('channels'), int) or item['channels'] <= 0
               or not item.get('source_rows') or not all(count > 0 for count in item['source_rows'])
               for item in report['inputs']):
            raise ValueError('Acceptance did not import meaningful source data from every recording')
    summary = report.get('summary', {})
    if summary.get('checks') != len(rows) or summary.get('passed') != len(rows):
        raise ValueError('Acceptance summary does not agree with its checks')
    if any(summary.get(field, 0) for field in ('unmet', 'unrun', 'runner_errors', 'application_callback_errors')):
        raise ValueError('Acceptance summary contains unfinished or failed work')
    if report.get('manual_checks_unrun') != MANUAL_WINDOWS_CHECKS:
        raise ValueError('Acceptance must disclose the native manual checks that were not executed')
    return report


def check(executable, samples, output, *, edition='standalone', form=None, timeout=900):
    from app_version import VERSION
    executable, samples, output = Path(executable).resolve(), Path(samples).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixtures = json.loads((samples/'manifest.json').read_text(encoding='utf-8'))['files']
    run_id = str(uuid.uuid4())
    report_path = output/'packaged-acceptance.json'
    report_path.unlink(missing_ok=True)
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen',
                       ANALIZER_ACCEPTANCE_RUN_ID=run_id,
                       ANALIZER_SETTINGS_DIR=str(output/'settings'),
                       ANALIZER_OUTPUT_DIR=str(output/'outputs'))
    # A launcher may itself be frozen or inherit a PyInstaller bootloader's
    # state.  A fresh child runtime must never reuse another app's extraction.
    for key in list(environment):
        if key.startswith('_PYI_') or key == '_MEIPASS2':
            environment.pop(key)
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    returncode = capture_runtime([str(executable), '--acceptance-check', '--samples', str(samples),
                                  '--output', str(output), '--report', str(report_path)],
                                 environment, output, timeout=timeout, run_id=run_id)
    # Windowed EXEs frequently have no stdout; the file is the authoritative
    # result.  Retain bounded stderr for crashes before report initialization.
    if not report_path.is_file():
        raise RuntimeError(f'Frozen acceptance did not produce a report (exit {returncode})')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    validate_packaged_report(report, executable=executable, version=VERSION, edition=edition,
                             form=form, run_id=run_id, fixtures=fixtures)
    if returncode:
        raise RuntimeError(f'Frozen acceptance returned {returncode}')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--samples', type=Path, default=ROOT/'tests/samples/recordings')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--edition', choices=('standalone', 'installed'), default='standalone')
    parser.add_argument('--form', choices=('standalone-onefile', 'standalone-folder', 'installed'))
    parser.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args()
    if args.form and (args.form == 'installed') != (args.edition == 'installed'):
        parser.error('--form and --edition must describe the same distribution')
    report = check(args.exe, args.samples, args.output, edition=args.edition,
                   form=args.form, timeout=args.timeout)
    print(json.dumps({'ok': report['ok'], 'edition': report['edition'], **report['summary']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
