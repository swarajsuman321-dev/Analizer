# Standalone Windows build — 2.1.3

Use 64-bit CPython 3.12 on Windows. Extract the repository and double-click
`build_windows.bat`; dependencies are installed in `.venv-exe` from the pinned
`requirements-build.txt`. Tcl/Tk is not required.

The builder runs the regression suite, builds the portable folder and single
executable, then runs each executable's bundled self-test. Failures stop the
build. Existing environments can use `build_windows.bat --skip-install`.
Use `--mode onedir`, `--mode onefile`, or `--mode debug` to select one output.

| Output | Usage |
| --- | --- |
| `dist/ApplianceSignalStudio.exe` | Standalone single executable |
| `dist/onedir/ApplianceSignalStudio/ApplianceSignalStudio.exe` | Portable folder; keep the entire folder together |
| `dist/ApplianceSignalStudio_Portable.zip` | Extract completely before running |

Only the current Qt frontend is included. The spec excludes Tk/TkAgg and the
removed application/plugin/zoom modules. Shared numerical, ingestion, engineering,
plot and reporting dependencies remain. Current Qt tools also include the restored
image-reference analyzer and extension host; no old application UI is bundled. Recordings and prior software versions
are not embedded. The old `--legacy` entry point has been removed.

The self-test exercises Qt launch, synthetic signals, FFT coordinate separation,
portable workspace snapshots, SVG/PDF/PNG and interval Excel/CSV reports, bundled
icons, ZIP/CSV parsing, feedback selection, synchronization, pressure, heater
states, comparison rendering and Excel readback.

Diagnostics are saved to `build/build.log`, `build/onedir_smoke_report.json`, and
`build/onefile_smoke_report.json`. `build_debug.bat` creates a console build for
startup diagnosis. Unhandled startup details go to
`%LOCALAPPDATA%/ApplianceSignalStudio/startup-error.log`.

Pushes to `main` trigger [Build Windows application](https://github.com/swarajsuman321-dev/Analizer/actions/workflows/windows-build.yml).
A successful run uploads **ApplianceSignalStudio-Windows-v2.1.3** (EXE and portable ZIP)
and separate build diagnostics. Native Windows binaries must be built and tested
on Windows; a Linux bundle or source test does not certify a Windows executable.
