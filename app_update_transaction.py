"""Update identities and the application-side, restored-workspace handshake.

The updater must observe an acknowledgement written by the *new workbench*,
not merely a successful CreateProcess call or the read-only runtime check.
Backups are intentionally retained after acknowledgement for manual recovery.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import re
import shutil
import sys


def _windows_process_image(pid):
    """Query a process image without opening it for termination or mutation."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.windll.kernel32
    query = kernel.QueryFullProcessImageNameW
    query.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                      ctypes.POINTER(wintypes.DWORD)]
    query.restype = wintypes.BOOL
    open_process = kernel.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        image = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(image))
        return Path(image.value) if query(handle, 0, image, ctypes.byref(size)) else None
    finally:
        close(handle)


def update_wait_pids():
    """Wait for both a onefile workbench and its owning bootloader to exit.

    PyInstaller's onefile parent removes its extraction directory after the
    Python child exits and can still own the old EXE during that cleanup.
    An onedir app or source test must never wait for its unrelated launcher.
    """
    current = os.getpid()
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return [current]
    from app_installation import distribution_kind
    if distribution_kind() != 'portable':
        return [current]
    parent = os.getppid()
    image = _windows_process_image(parent) if parent else None
    if image is not None:
        try:
            same_executable = image.samefile(sys.executable)
        except OSError:
            same_executable = image.resolve() == Path(sys.executable).resolve()
        if same_executable and parent != current:
            return [current, parent]
    return [current]


def file_hash(path):
    from app_operation_context import checkpoint
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            checkpoint()
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def recovery_files(recovery):
    """Hash both workspace metadata and its immutable generation-named arrays."""
    recovery = Path(recovery).resolve()
    record = json.loads(recovery.read_text(encoding='utf-8'))
    arrays = record.get('arrays')
    if not isinstance(arrays, str) or Path(arrays).name != arrays:
        raise ValueError('Update recovery requires an adjacent workspace array file')
    companion = recovery.parent / arrays
    return {str(path): file_hash(path) for path in (recovery, companion)}


def create_request(directory, target, recovery, version, kind):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Isolate a snapshot per transaction: two open editions can update without
    # replacing each other's recovery JSON or its generation-named arrays.
    recovery = Path(recovery).resolve()
    original_files = recovery_files(recovery)
    snapshot = directory / 'recovery'
    snapshot.mkdir()
    fallback = directory / 'previous-recovery'
    fallback.mkdir()
    from app_operation_context import checkpoint
    for source in original_files:
        # A waveform companion can be large: cancellation is safe until the
        # detached updater has been launched, and must not freeze the GUI.
        for destination in (snapshot / Path(source).name, fallback / Path(source).name):
            with Path(source).open('rb') as incoming, destination.open('xb') as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    checkpoint('Preparing independent update recovery snapshots')
                    outgoing.write(chunk)
            shutil.copystat(source, destination)
            if file_hash(destination) != original_files[source]:
                raise ValueError('Recovery workspace changed while preparing the update; save it again')
    recovery = snapshot / recovery.name
    request = directory / 'startup-request.json'
    value = {'schema': 1, 'token': secrets.token_hex(32), 'version': version,
             'kind': kind, 'executable': str(Path(target).resolve()),
             'recovery': str(Path(recovery).resolve()), 'files': recovery_files(recovery),
             'fallback_recovery': str((fallback/recovery.name).resolve()),
             'ack': str((directory / 'startup-ack.json').resolve())}
    atomic_json(request, value)
    return request, value


def request_from_argv(argv=None):
    argv = sys.argv if argv is None else argv
    if '--update-request' not in argv:
        return None
    index = argv.index('--update-request')
    if index + 1 >= len(argv):
        raise ValueError('Missing update startup request')
    path = Path(argv[index + 1]).resolve()
    if path.stat().st_size > 256 * 1024:
        raise ValueError('Update startup request is too large')
    value = json.loads(path.read_text(encoding='utf-8'))
    if (value.get('schema') != 1 or not isinstance(value.get('token'), str)
            or not re.fullmatch('[0-9a-f]{64}', value['token'])
            or value.get('kind') not in ('portable', 'portable-zip', 'installer')
            or Path(value.get('ack', '')) != path.parent / 'startup-ack.json'):
        raise ValueError('Invalid update startup request')
    return value


def acknowledge_startup(restore_succeeded, error='', argv=None, window=None):
    """Root workbench calls this after restoration and a visible event-loop tick.

    Return False for a rejected/failed request, True for acknowledged startup,
    and None for an ordinary launch. The caller exits on False so rollback can
    reclaim the failed runtime. Never acknowledge a different runtime/version.
    """
    try:
        request = request_from_argv(argv)
    except (OSError, ValueError, TypeError):
        # A malformed request must never escape a Qt timer callback and leave
        # an unacknowledged, apparently healthy window running indefinitely.
        return False
    if request is None:
        return None
    from app_version import VERSION
    reason = str(error)
    try:
        if not restore_succeeded:
            raise ValueError(reason or 'Recovery workspace restoration failed')
        if request['version'] != VERSION or Path(request['executable']).resolve() != Path(sys.executable).resolve():
            raise ValueError('Unexpected application version or executable at update startup')
        if window is None or not window.isVisible():
            raise ValueError('The updated workbench is not visible')
        argv = sys.argv if argv is None else argv
        index = argv.index('--restore')
        if Path(argv[index + 1]).resolve() != Path(request['recovery']).resolve():
            raise ValueError('A different workspace was restored')
        if recovery_files(request['recovery']) != request['files']:
            raise ValueError('Recovery workspace changed during application startup')
        # Restoration validation is done by load_workspace; record enough live
        # state for native tests and human recovery diagnostics to inspect.
        state = {'channels': list(window.store.channels), 'datasets': list(window.store.datasets),
                 'views': [workspace.state() for workspace in window.workspaces]}
        status = 'ready'
    except Exception as exc:
        status, reason, state = 'failed', str(exc), {}
    atomic_json(request['ack'], {'schema': 1, 'token': request['token'], 'version': VERSION,
                                'executable': str(Path(sys.executable).resolve()),
                                'recovery': request['recovery'], 'files': request['files'],
                                'status': status, 'error': reason, 'state': state,
                                'pid': os.getpid()})
    return status == 'ready'


def acknowledge_failure(error):
    """Best-effort failure signal when imports fail before the window exists."""
    try:
        return acknowledge_startup(False, str(error))
    except Exception:
        return False
