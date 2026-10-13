# Build through build_exe.py so onedir, onefile and diagnostic outputs are separate.
import os
from pathlib import Path

project = Path(SPECPATH)
mode = os.environ.get('ANALYZER_BUILD_MODE', 'onefile')
if mode not in ('onedir', 'onefile', 'debug'):
    raise ValueError('Unknown analyzer build mode.')
assets = [(str(project / name), '.') for name in ('app_icon.ico', 'app_logo.png')]
analysis = Analysis(
    [str(project / 'windows_entry.py')],
    pathex=[str(project)],
    binaries=[],
    datas=assets,
    hiddenimports=['app_simulation_package', 'app_inspection', 'app_symbols',
                   'openpyxl', 'xlrd', 'matplotlib.backends.backend_tkagg',
                   'matplotlib.backends.backend_agg'],
    hookspath=[],
    hooksconfig={'matplotlib': {'backends': ['TkAgg', 'Agg']}},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'IPython', 'jupyter', 'pytest'],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
options = dict(name='ApplianceSignalStudio', debug=False,
               bootloader_ignore_signals=False, strip=False, upx=False,
               console=mode == 'debug', icon=str(project / 'app_icon.ico'),
               version=str(project / 'version_info.txt'), disable_windowed_traceback=False)
if mode == 'onefile':
    exe = EXE(pyz, analysis.scripts, analysis.binaries, analysis.datas, [], **options)
else:
    exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, **options)
    bundle = COLLECT(exe, analysis.binaries, analysis.datas, strip=False,
                     upx=False, name='ApplianceSignalStudio')
