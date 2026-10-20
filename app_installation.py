"""Installed-layout identity and a fast, read-only check of the bundled runtime."""
import json
from pathlib import Path
import sys

MUTEX_NAME = r'Local\ApplianceSignalStudio.Workbench'
_mutex_handle = None


def distribution_kind():
    """Identify the running payload, never infer folder mode from stray files."""
    if installed_root():
        return 'installer'
    if getattr(sys, 'frozen', False):
        folder = Path(sys.executable).resolve().parent
        if Path(getattr(sys, '_MEIPASS', '')).resolve() == (folder / '_internal').resolve():
            return 'portable-zip'
    return 'portable'


def installed_root():
    """Only a marked versioned runtime is managed by the Windows installer."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return None
    folder = Path(sys.executable).resolve().parent
    try:
        marker = json.loads((folder / 'installed-layout.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if marker != {'product': 'Appliance Signal Studio', 'schema': 1, 'kind': 'installed'}:
        return None
    from app_updates import version_tuple
    try:
        version_tuple(folder.name)
    except ValueError:
        return None
    return folder.parent.parent if folder.parent.name == 'versions' else None


def hold_application_mutex():
    """Allow multiple windows, but let Setup detect any running new-build app."""
    global _mutex_handle
    if sys.platform == 'win32' and _mutex_handle is None:
        import ctypes
        from ctypes import wintypes
        create = ctypes.windll.kernel32.CreateMutexW
        create.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        create.restype = wintypes.HANDLE
        _mutex_handle = create(None, False, MUTEX_NAME)
        if not _mutex_handle:
            raise ctypes.WinError()


def installation_check():
    """Boot/import real dependencies without opening or rewriting user settings."""
    import numpy
    import pandas
    import scipy.signal
    import openpyxl
    import nptdms
    import matplotlib.backends.backend_pdf
    from PySide6 import QtWidgets
    from app_appliance_profiles import load_profile
    from app_identity import apply_identity
    from app_workbench import AdvancedStudioWindow  # Check the complete frontend import graph.
    from app_version import VERSION
    from app_update_transaction import update_wait_pids
    import os
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    icon = apply_identity()
    if icon.isNull() or not load_profile()['channels']:
        raise RuntimeError('Bundled icon or appliance profiles are missing')
    return {'ok': True, 'version': VERSION, 'frozen': bool(getattr(sys, 'frozen', False)),
            'installed_root': str(installed_root() or ''),
            'runtime_directory': str(getattr(sys, '_MEIPASS', 'source')),
            'pid': os.getpid(), 'parent_pid': os.getppid(),
            'update_wait_pids': update_wait_pids()}
