# Build through build_exe.py so onedir, onefile and diagnostic outputs are separate.
import os
from pathlib import Path

project = Path(SPECPATH)
mode = os.environ.get('ANALYZER_BUILD_MODE', 'onefile')
if mode not in ('onedir', 'onefile', 'debug'):
    raise ValueError('Unknown analyzer build mode.')
assets = [(str(project / name), '.') for name in ('app_icon.ico', 'app_logo.png')]
assets.append((str(project / 'manuals'), 'manuals'))
analysis = Analysis(
    [str(project / 'windows_entry.py')],
    pathex=[str(project)],
    binaries=[],
    datas=assets,
    hiddenimports=['app_simulation_package', 'app_inspection', 'app_symbols',
                   'openpyxl', 'xlrd',
                   'matplotlib.backends.backend_agg',
                   'matplotlib.backends.backend_svg', 'matplotlib.backends.backend_pdf',
                   'matplotlib.backends.backend_qtagg', 'app_studio_tools', 'app_reference_image',
                   'app_workbench',
                   'scipy.signal', 'PySide6.QtSvg', 'pyqtgraph'],
    hookspath=[],
    hooksconfig={'matplotlib': {'backends': ['Agg', 'svg', 'pdf', 'QtAgg']}},
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter', 'app_legacy', 'app_telemetry', 'app_patches', 'app_zoom', 'PyQt5', 'PyQt6', 'PySide2', 'IPython', 'jupyter', 'pytest'],
    noarchive=False,
)
for module_name, *_ in analysis.pure:
    if module_name.split('.')[0] in {'tkinter', 'app_legacy', 'app_telemetry', 'app_patches', 'app_zoom', 'app_plotter', 'app_image_analysis'}:
        raise RuntimeError(f'Obsolete frontend module found in bundle: {module_name}')
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
