"""Remember dialog folders in personal settings, outside replaceable runtimes.

Only folder names are stored. The versioned, bounded record deliberately has
room for more dialog purposes without keeping measurements or activity logs.
The Qt wrappers accept the same positional arguments and return the same values
as QFileDialog; ``purpose`` is their sole additional keyword argument.
"""

import json
import os
from pathlib import Path, PureWindowsPath
import threading

from app_lifecycle import settings_directory
from app_support import atomic_output


HISTORY_FILENAME = 'dialog-history.json'
MAX_PURPOSES = 64
MAX_PURPOSE_LENGTH = 128
MAX_PATH_LENGTH = 32_768
MAX_HISTORY_BYTES = 2 * 1024 * 1024
_lock = threading.RLock()


def _purpose(value):
    if not isinstance(value, str) or not value or len(value) > MAX_PURPOSE_LENGTH:
        return None
    if any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF
           for char in value):
        return None
    return value


def _path(value, *, absolute_only=False):
    """Use native path rules; never reinterpret another OS's drive as a folder."""
    try:
        value = os.fspath(value)
        if not isinstance(value, str) or not value or len(value) > MAX_PATH_LENGTH:
            return None
        if any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF
               for char in value):
            return None
        if os.name != 'nt' and PureWindowsPath(value).drive:
            return None
        path = Path(value)
        if absolute_only:
            return path if path.is_absolute() else None
        return path.expanduser().resolve(strict=False)
    except (OSError, ValueError, TypeError, RuntimeError):
        return None


def _empty_history():
    return {'version': 1, 'last_folder': '', 'folders': {}}


def _read_history():
    """Settings are optional: malformed or inaccessible files act as no history."""
    try:
        path = settings_directory() / HISTORY_FILENAME
        with path.open('rb') as stream:
            encoded = stream.read(MAX_HISTORY_BYTES + 1)
        if len(encoded) > MAX_HISTORY_BYTES:
            return _empty_history()
        record = json.loads(encoded)
        if (not isinstance(record, dict) or type(record.get('version')) is not int
                or record['version'] != 1):
            return _empty_history()
        folders = record.get('folders')
        last = record.get('last_folder')
        if (not isinstance(folders, dict) or len(folders) > MAX_PURPOSES
                or not isinstance(last, str)
                or (last and _path(last, absolute_only=True) is None)):
            return _empty_history()
        if any(_purpose(key) is None or _path(value, absolute_only=True) is None
               for key, value in folders.items()):
            return _empty_history()
        # Do not propagate unknown fields into the next write.
        return {'version': 1, 'last_folder': last, 'folders': dict(folders)}
    except (OSError, ValueError, TypeError, RuntimeError, RecursionError):
        return _empty_history()


def _existing_directory(path):
    if path is None:
        return None
    try:
        while True:
            if path.is_dir():
                return path
            parent = path.parent
            if parent == path:
                return None
            path = parent
    except (OSError, ValueError, RuntimeError):
        return None


def start_directory(purpose, fallback=''):
    """Find the purpose's folder, supplied fallback, latest folder, or user home.

    Deleted folders walk up to their nearest existing parent. Paths are resolved
    on each call, so a new settings environment or an app restart has no stale
    global state to clear. Reading history never rewrites it.
    """
    with _lock:
        record = _read_history()
    candidates = (record['folders'].get(_purpose(purpose), ''),
                  fallback, record['last_folder'])
    for candidate in candidates:
        folder = _existing_directory(_path(candidate))
        if folder is not None:
            return str(folder)
    try:
        home = Path.home()
        for candidate in (home / 'Documents', home):
            folder = _existing_directory(candidate)
            if folder is not None:
                return str(folder)
    except (OSError, RuntimeError):
        pass
    # Qt can still choose its platform default if the user home is unavailable.
    return ''


def remember_path(purpose, path):
    """Remember a chosen directory or a file's parent; return write success.

    Nonexistent paths are treated as selected filenames (as in a Save dialog).
    Empty selections and invalid values never change the saved record. Failures
    to write personal settings never prevent opening or saving the chosen file.
    """
    key = _purpose(purpose)
    selected = _path(path)
    if key is None or selected is None:
        return False
    try:
        folder = selected if selected.is_dir() else selected.parent
        folder = _existing_directory(folder)
        if folder is None:
            return False
        value = str(folder)
        if _path(value, absolute_only=True) is None:
            return False
        with _lock:
            record = _read_history()
            folders = record['folders']
            # Insertion order records recency for bounded purpose retention.
            folders.pop(key, None)
            folders[key] = value
            while len(folders) > MAX_PURPOSES:
                del folders[next(iter(folders))]
            record['last_folder'] = value
            encoded = json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8')
            while len(encoded) > MAX_HISTORY_BYTES and len(folders) > 1:
                del folders[next(iter(folders))]
                encoded = json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8')
            if len(encoded) > MAX_HISTORY_BYTES:
                return False
            destination = settings_directory() / HISTORY_FILENAME
            with atomic_output(destination) as temporary:
                with Path(temporary).open('wb') as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
        return True
    except (OSError, ValueError, TypeError, RuntimeError):
        return False


def _initial_path(purpose, supplied, *, save=False):
    folder = start_directory(purpose, supplied)
    if save:
        path = _path(supplied)
        try:
            if path is not None and not path.is_dir():
                return str(Path(folder) / path.name) if folder else path.name
        except (OSError, ValueError):
            pass
    return folder


def open_file(parent=None, caption='', dir='', filter='', *args,
              purpose='OpenData', **kwargs):
    """QFileDialog.getOpenFileName with remembered folder selection."""
    from PySide6 import QtWidgets
    result = QtWidgets.QFileDialog.getOpenFileName(
        parent, caption, _initial_path(purpose, dir), filter, *args, **kwargs)
    if result[0]:
        remember_path(purpose, result[0])
    return result


def open_files(parent=None, caption='', dir='', filter='', *args,
               purpose='OpenData', **kwargs):
    """QFileDialog.getOpenFileNames with its normal (filenames, filter) result."""
    from PySide6 import QtWidgets
    result = QtWidgets.QFileDialog.getOpenFileNames(
        parent, caption, _initial_path(purpose, dir), filter, *args, **kwargs)
    if result[0]:
        remember_path(purpose, result[0][0])
    return result


def save_file(parent=None, caption='', dir='', filter='', *args,
              purpose='Export', **kwargs):
    """QFileDialog.getSaveFileName, retaining the suggested output filename."""
    from PySide6 import QtWidgets
    result = QtWidgets.QFileDialog.getSaveFileName(
        parent, caption, _initial_path(purpose, dir, save=True), filter, *args, **kwargs)
    if result[0]:
        remember_path(purpose, result[0])
    return result


def choose_directory(parent=None, caption='', dir='', *args,
                     purpose='Directory', **kwargs):
    """QFileDialog.getExistingDirectory with its normal string result."""
    from PySide6 import QtWidgets
    result = QtWidgets.QFileDialog.getExistingDirectory(
        parent, caption, start_directory(purpose, dir), *args, **kwargs)
    if result:
        remember_path(purpose, result)
    return result
