"""Application identity shared by source and frozen Windows launches."""
from pathlib import Path
import sys
from PySide6 import QtGui,QtWidgets


def apply_identity(window=None):
    if sys.platform=='win32':
        import ctypes
        set_id=ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID;set_id.argtypes=[ctypes.c_wchar_p];set_id.restype=ctypes.c_long
        set_id('ApplianceSignalStudio.Workbench')
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    icon=QtGui.QIcon(str(root/'app_icon.ico'))
    if icon.isNull():icon=QtGui.QIcon(str(root/'app_logo.png'))
    app=QtWidgets.QApplication.instance()
    if app:app.setApplicationName('Appliance Signal Studio');app.setWindowIcon(icon)
    if window is not None:window.setWindowIcon(icon)
    return icon
