"""Publish permanent verification evidence from this native release's gate results.

Run after every build, installer, packaged-workflow and application-update gate,
before publishing the immutable release.  Reports are required, not synthesized
from a successful workflow step.  This script reads no credentials and includes
only an allowlist of public CI identifiers alongside the original JSON reports.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_release_acceptance import MANUAL_WINDOWS_CHECKS, REQUIRED_CHECK_IDS
from app_version import BUILD_DATE, VERSION


REPORT_FILES = (
    'onedir_smoke_report.json',
    'onefile_smoke_report.json',
    'onefile_restart_smoke_report.json',
    'installer_smoke_report.json',
    'packaged_workflows_smoke_report.json',
    'application_updates_smoke_report.json',
)
PACKAGED_EDITIONS = {'standalone-onefile', 'standalone-folder', 'installed'}
UNIT_SUMMARY = re.compile(r'^Ran (\d+) tests? in ([0-9]+(?:\.[0-9]+)?)s\s*$', re.MULTILINE)
UNIT_OUTCOME = re.compile(r'^(OK|FAILED)(?: \(([^\r\n]*)\))?\s*$', re.MULTILINE)


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def unit_test_evidence(build_directory):
    """Parse the actual full-suite terminal summary, never guess cached counts.

    Cache-hit runs capture a dedicated native-unit-tests.log.  Cold builds use
    build_exe.py's build.log, which also contains later PyInstaller output.  An
    absent log is disclosed; an incomplete or failed terminal summary is fatal.
    """
    build_directory = Path(build_directory)
    path = next((build_directory/name for name in ('native-unit-tests.log', 'build.log')
                 if (build_directory/name).is_file()), None)
    if path is None:
        return {'status': 'unavailable', 'tests_run': None, 'skipped': None,
                'reason': 'No captured native full-suite log was available; no count is inferred from smoke checks.'}
    raw = path.read_bytes()
    text = raw.decode('utf-8-sig', errors='replace')
    summaries = list(UNIT_SUMMARY.finditer(text))
    provenance = {'source_log': path.name, 'source_bytes': len(raw),
                  'source_sha256': hashlib.sha256(raw).hexdigest()}
    if not summaries:
        return {'status': 'unavailable', 'tests_run': None, 'skipped': None,
                'reason': 'The captured log contains no complete unittest run summary.', **provenance}
    # The outer full discovery suite finishes after any nested subprocess tests.
    summary = summaries[-1]
    outcome = UNIT_OUTCOME.search(text, summary.end())
    if outcome is None:
        raise ValueError(path.name+' has a test count without a terminal outcome')
    if outcome.group(1) != 'OK':
        raise ValueError(path.name+' records a failed native full test suite: '+outcome.group(0).strip())
    counts = {'skipped': 0, 'expected failures': 0, 'failures': 0, 'errors': 0, 'unexpected successes': 0}
    if outcome.group(2):
        for item in outcome.group(2).split(','):
            match = re.fullmatch(r'\s*([a-z ]+)=(\d+)\s*', item)
            if match is None or match.group(1) not in counts:
                raise ValueError('Unknown unittest outcome detail in '+path.name+': '+item)
            counts[match.group(1)] = int(match.group(2))
    total = int(summary.group(1))
    if total <= 0 or any(counts[key] for key in ('failures', 'errors', 'unexpected successes')):
        raise ValueError(path.name+' did not record a successful nonempty native full suite')
    if counts['skipped']+counts['expected failures'] > total:
        raise ValueError(path.name+' has inconsistent unittest counts')
    return {'status': 'passed', 'tests_run': total, 'skipped': counts['skipped'],
            'expected_failures': counts['expected failures'],
            'duration_seconds': float(summary.group(2)),
            'terminal_summary': summary.group(0).strip()+'\n'+outcome.group(0).strip(), **provenance}


def _read_report(path, version):
    raw = path.read_bytes()  # Missing gates must stop publication.
    try:
        report = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid native gate report: '+path.name) from exc
    if not isinstance(report, dict) or report.get('ok') is not True or report.get('version') != version:
        raise ValueError(path.name+' must report actual success for version '+version)
    if path.name in REPORT_FILES[:3]:
        if report.get('frozen') is not True or report.get('modern', {}).get('qt_gui_checked') is not True:
            raise ValueError(path.name+' must come from a real frozen workbench self-test')
    elif path.name == 'packaged_workflows_smoke_report.json':
        editions = report.get('editions')
        if not isinstance(editions, dict) or set(editions) != PACKAGED_EDITIONS:
            raise ValueError('Packaged workflows must cover the installed, standalone EXE and standalone folder editions')
        for edition, summary in editions.items():
            if not isinstance(summary, dict):
                raise ValueError('Invalid packaged-workflow summary for '+edition)
            total, passed = summary.get('checks'), summary.get('passed')
            if type(total) is not int or total < len(REQUIRED_CHECK_IDS) or passed != total:
                raise ValueError('Incomplete packaged acceptance checks for '+edition)
            if any(summary.get(field, 0) for field in ('unmet', 'unrun', 'runner_errors', 'application_callback_errors')):
                raise ValueError('Failed or unfinished packaged acceptance for '+edition)
        if report.get('manual_checks_unrun') != MANUAL_WINDOWS_CHECKS:
            raise ValueError('Packaged evidence must preserve the explicit native manual-check limits')
    else:
        platform = str(report.get('platform', '')).lower()
        if not platform.startswith('native windows') or not report.get('checks'):
            raise ValueError(path.name+' must contain native Windows checks')
        if path.name == 'application_updates_smoke_report.json' and 'actual gui' not in platform:
            raise ValueError('Application update evidence must exercise the actual application GUI')
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'report': report}


def assemble_validation(build_directory, dist_directory, *, source_sha, version=VERSION, environment=None):
    """Validate every real gate, hash exact downloads, and atomically write JSON."""
    if not isinstance(source_sha, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', source_sha):
        raise ValueError('Provide the exact 40-character GITHUB_SHA for this build')
    source_sha = source_sha.lower()
    environment = os.environ if environment is None else environment
    checkout_sha = environment.get('GITHUB_SHA')
    if checkout_sha and checkout_sha.lower() != source_sha:
        raise ValueError('Requested source commit differs from this workflow GITHUB_SHA')
    build_directory, dist_directory = Path(build_directory), Path(dist_directory)
    reports = {name: _read_report(build_directory/name, version) for name in REPORT_FILES}
    units = unit_test_evidence(build_directory)
    artifacts = {}
    for kind, filename in (
            ('standalone-onefile', 'ApplianceSignalStudio.exe'),
            ('standalone-folder', 'ApplianceSignalStudio_Portable.zip'),
            ('installed-setup', f'ApplianceSignalStudio-Setup-{version}.exe')):
        path = dist_directory/filename
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError('A tested release artifact is missing or empty: '+filename)
        artifacts[kind] = {'filename': filename, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
    ci = {key: environment[key] for key in ('GITHUB_REPOSITORY', 'GITHUB_REF', 'GITHUB_RUN_ID',
          'GITHUB_RUN_ATTEMPT', 'GITHUB_WORKFLOW', 'GITHUB_JOB', 'RUNNER_OS', 'RUNNER_ARCH') if environment.get(key)}
    repository, run_id = ci.get('GITHUB_REPOSITORY'), ci.get('GITHUB_RUN_ID')
    if repository and re.fullmatch(r'[\w.-]+/[\w.-]+', repository) and run_id and run_id.isdigit():
        ci['workflow_url'] = f'https://github.com/{repository}/actions/runs/{run_id}'
    limitations = list(MANUAL_WINDOWS_CHECKS)
    for record in reports.values():
        for limit in record['report'].get('limitations', []):
            if limit not in limitations:
                limitations.append(limit)
    if units['status'] != 'passed':
        limitations.append('The full native unittest count is unavailable in the captured logs; smoke checks do not establish a regression-test count.')
    result = {'schema': 1, 'version': version, 'build_date': BUILD_DATE,
              'source_commit': source_sha, 'assembled_at_utc': datetime.now(timezone.utc).isoformat(),
              'assembly_platform': sys.platform, 'native_gate_reports_passed': True,
              'workflow_completion': 'Not asserted: this evidence is assembled after verification gates and before release publication.',
              'ci': ci, 'native_unit_tests': units, 'artifacts': artifacts,
              'native_gate_reports': reports, 'manual_checks_unrun': list(MANUAL_WINDOWS_CHECKS),
              'limitations': limitations}
    destination = dist_directory/f'validation-v{version}.json'
    # Never leave a partial public evidence file if writing is interrupted.
    temporary = destination.with_suffix('.json.tmp')
    try:
        temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=ROOT/'build')
    parser.add_argument('--dist', type=Path, default=ROOT/'dist')
    parser.add_argument('--source-sha', default=os.environ.get('GITHUB_SHA'))
    args = parser.parse_args()
    path, result = assemble_validation(args.build, args.dist, source_sha=args.source_sha)
    print(json.dumps({'path': str(path), 'version': result['version'],
                      'source_commit': result['source_commit'],
                      'native_gate_reports': len(result['native_gate_reports']),
                      'native_unit_tests': result['native_unit_tests']['status']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
