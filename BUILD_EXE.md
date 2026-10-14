# Build the analyzer as a Windows EXE

This package contains the working analyzer and the Windows build configuration.
The Windows EXE has to be created on a Windows computer; the supplied ZIP does
not contain an already-compiled executable.

## Three steps

1. Extract the entire ZIP to a writable folder on your Windows computer.
2. Double-click **build_windows.bat**. Keep its window open while it installs
   dependencies, checks the analyzer and builds the executable.
3. Open **dist/ApplianceSignalStudio.exe** after the build reports success.

Use standard 64-bit Python 3.12 on the build computer. The script also accepts
64-bit Python 3.11 and 3.13. Python needs Tcl/Tk support. If Python is missing,
install it from https://www.python.org/downloads/windows/ with the launcher and
Tcl/Tk selected, then run the batch file again. Internet access is needed to
install build dependencies once; Python does not need to be installed on PCs
that only run the finished EXE.

The script uses its own `.venv-exe` folder and does not change your global
Python installation. Build requirements are pinned in `requirements-build.txt`.
It does not embed any simulation dataset, bench recording or uploaded ZIP.

## Outputs

| Output | How to use it |
| --- | --- |
| `dist/ApplianceSignalStudio.exe` | Single EXE; copy this file to a Windows PC and double-click it. |
| `dist/onedir/ApplianceSignalStudio/ApplianceSignalStudio.exe` | Portable folder version; keep the whole folder together. |
| `dist/ApplianceSignalStudio_Portable.zip` | Share or archive the complete portable folder version. |

The normal EXE opens the Tkinter interface without a console window. It includes
the ZIP/CSV parser, plots, Excel reader/exporter, image fallback, icon, Python
runtime and required dependencies. The single-file version extracts its runtime
to a temporary folder at startup and can take longer to open than the folder
version. Run it normally; administrator privileges are not needed.

The comparison keeps original pressure numbers from both files, labelled Pa,
using the selected bench pressure channel. It uses drum-speed feedback,
positive integer actuator states (128 is ON),
ten parameters and actual remaining time. Values show percentage difference
colours without acceptance limits; valves and pumps show count differences.
Existing plugin/log storage continues to use the app folder
when writable and the per-user LocalAppData folder otherwise.

The synchronization dropdown also includes **First Drum Start to First Power
Rise**. Select it to align PD and RD by the first drum feedback movement and
the first sustained power increase, without requiring a 1500 W heater spike.
Detected events and the shift appear in **Data Quality & Synchronization**.
See README.md for thresholds, limitations and the checked 9 kg recording.

## Checks performed by the build

The builder runs all 61 analyzer tests before building, including telemetry GUI checks on Windows. It then builds the
folder version first and starts that compiled EXE in self-test mode. Only after
that check passes does it build and check the single-file EXE. Each compiled
self-test verifies native Tcl/Tk, bundled icons, simulation ZIP/CSV loading,
original pressure numbers and Pa labels, actual remaining time, RPM feedback, heater 128 ON time,
percentage colours, heater watts/state cursor mapping,
first-drum / first-power-rise synchronization with different source clock
origins, rendering and Excel export/readback. Reports are saved to:

- `build/onedir_smoke_report.json`
- `build/onefile_smoke_report.json`
- `build/build.log`

After building, open the app and check it with your real bench and simulation
files before sharing it. Automated self-tests do not cover every interactive
desktop action.

## If the build does not finish

The build window remains open with the error message. Check `build/build.log`.
For an EXE startup error, double-click **build_debug.bat**. It creates a console
version at `dist/debug/ApplianceSignalStudio/ApplianceSignalStudio.exe`; keep its
whole folder together. Early startup exceptions are also written to
`%LOCALAPPDATA%/ApplianceSignalStudio/startup-error.log`.

For an existing build environment with dependencies already installed, run:

```bat
build_windows.bat --skip-install
```

To build only one mode:

```bat
build_windows.bat --mode onedir
build_windows.bat --mode onefile
```

## What was verified here

All analyzer tests pass, and the EXE self-test runs successfully from source
in the supplied environment. The spec and Python build scripts compile. The
Windows batch launcher, native Windows PyInstaller build, and Windows GUI have
not been executed here because this environment is Linux. The included builder
performs the native executable checks on your Windows computer and stops on
failure.

Build references:

- https://pyinstaller.org/en/stable/operating-mode.html
- https://pyinstaller.org/en/stable/spec-files.html
- https://pypi.org/project/pyinstaller/6.22.3/

## Automated GitHub build

Pushes to `main` trigger `.github/workflows/windows-build.yml` on a native
Windows runner with Python 3.12. You can also start **Build Windows application**
from the Actions tab. The workflow uses the same pinned requirements and
`build_exe.py`, runs tests, builds both formats and checks each executable.
A successful run uploads **ApplianceSignalStudio-Windows** containing the
single-file EXE and portable ZIP. Download and extract the artifact to use it.
The separate diagnostics artifact contains the build log and self-test reports.
This configuration alone does not prove that a hosted Windows build succeeded;
check the workflow's result before distributing its outputs.


## Modern frontend reconstruction

The launcher and Windows entry now default to the Qt workbench. Pass `--legacy`
to open the retained Tk app. Build requirements include PySide6, PyQtGraph, SciPy,
Polars and PyArrow; the spec includes Qt SVG and both frontend implementations.
The source/bundle self-test exercises Qt startup, FFT coordinate separation,
portable snapshots and SVG export as well as retained engineering checks.
Native Windows EXE builds and graphics-driver behavior require a Windows run;
Linux source validation does not certify the packaged Windows executable.
