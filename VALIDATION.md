# Studio 2.1.7 validation

The full local headless Qt suite passed **176 tests** (one native Windows-only
installer transaction skipped): `/tmp/analizer-v217-tests.log`. The focused
manual/default-layout suite passed four checks, including the final one-time
pre-2.1.7 updater visibility migration and explicit saved-layout restoration:
`/tmp/analizer-v217-manual-tests.log`. Updater regressions also pass locally;
native Windows runs the installer test in CI. The source startup smoke report
is `/tmp/analizer-v217-source-smoke.json` (ok=true).

Coverage verifies a top-toolbar manual button, two graph workspaces, nonmodal
manual reopening without changing the active plot, enabled View docks and channel
kind, topic navigation, wraparound keyword search, retained reading position for
failed searches, and version-filtered documentation including every processing
operation and View panel. Only generated version manuals are bundled; the source
guide/generator stay out of the EXE. Frozen smoke checks validate the toolbar
manual and topic navigation as well as retained TDMS/hover support. Native Windows
CI runs the exact final suite and both executables before release publication.

# Studio 2.1.6 validation

The full local suite passed **170 tests** (one native Windows-only transaction
check skipped): `/tmp/analizer-v216-tests.log`. The final focused TDMS/hover suite
passes **9 tests**, including two added engineering-adapter checks:
`/tmp/analizer-v216-tdms-hover-tests.log`. The final Windows suite has 172 tests.
Coverage includes native per-channel timestamps, units, quality, waveform clocks,
absolute clocks, sample-index fallback, causal synchronization, source preservation,
workspace roundtrips, real mouse movement, independent axes, normalized/shifted
traces, null values, empty selection and stable locked cursors. Plot close stops
pending rendering and hover callbacks.

The supplied TDMS was independently checked: **27 channels, 305,779 measurements,
232.3665 minutes**. Source values match exactly; seconds-to-minutes timestamps
agree within floating-point rounding. Its complete workspace saves and restores,
and PDF/PNG/CSV exports succeed. Alignment produces 27 channels on 124,585
synchronized timestamps while retaining the untouched TDMS source table.
Evidence is outside the repository at
`/workspace/analizer-report-validation/v216/validation.json`; uploaded recordings
and generated data are not packaged or committed. Frozen self-tests explicitly
read a synthetic TDMS and exercise mouse XY hover. Windows CI runs the final full
suite and both packaged-app checks before release publication.

# Studio 2.1.5 validation

The full local suite passed **160 tests** (`/tmp/analizer-v215-tests.log`).
The final focused updater suite passed seven tests; its eighth test exercises
native PowerShell replacement and rollback on Windows CI and is skipped on Linux
(`/tmp/analizer-v215-update-tests.log`). The final Windows suite contains 163 tests.
Coverage includes stable-version ordering, update URL/size/checksum validation,
corrupted-download cleanup, offline errors, cancellation, background completion,
script quoting, unchanged installed files before restart, Info manuals and active
analysis context. The native transaction test uses real filesystem operations and
simulates process waiting/restart so it never replaces the CI interpreter.
Frozen self-tests check that the version manual is actually bundled. CI publishes
release downloads and their SHA-256 manifest only after both packaged apps pass.
Physical power-loss recovery and operating-system security-software prompts are
not simulated. The previous EXE and recovery workspace remain available.

# Studio 2.1.4 validation

The full source suite passes: **155 tests** (`/tmp/analizer-v214-tests.log`).
Six additional actuator regressions cover integer states, physical-unit and
program-code exclusions, reversible overrides, textual states, original readings,
repeat alignment, old/new workspace persistence, step traces, duty/ON duration,
report exports and non-null application/window icons. Targeted results are in
`/tmp/analizer-v214-actuator-tests.log`. The frozen startup check now verifies the
application and window icon. Windows CI tests and builds both executables before
publishing 2.1.4. Historical validation records follow.

# Studio 2.1.3 validation

Six zoom-mode regressions exercise real diagonal rectangle drags in X, Y and XY,
selection-band geometry, wheel input and zoom buttons across independent Y axes.
The full suite contains 149 tests. Evidence: `/tmp/analizer-v213-zoom-tests.log`
and `/tmp/analizer-v213-tests.log`. Native Windows CI tests and builds the final
commit before publishing the versioned download. Earlier records follow.

# Studio 2.1.2 validation

This update makes multi-axis vertical navigation apply equally to every visible
unit axis, surfaces locked cursor values directly, and adds interval statistics
to the main Readout table. Native mouse-pan, wheel zoom, button zoom, view history,
locked readout and reset regressions are included in the full suite. The suite now contains 143 tests. Targeted native pan/wheel/button checks,
locked-sample marker checks, and statistics-scope/note persistence/export checks
pass. Full-suite evidence is written to `/tmp/analizer-v212-verified-tests.log`.
Windows CI runs the complete suite and self-tests both packaged executables before
uploading the versioned 2.1.2 download. Historical validation records follow.

# Studio 2.1.1 validation

The update adds conservative unit detection, visible zoom/reset controls and
shortcuts, persistent per-channel cursor locks, and idempotent alignment refresh.
New regressions cover unit rows/suffixes, chosen sample clocks, linked panning,
channel shifts, anchor deletion/hiding, persistence, keyboard stepping and repeat
alignment with unchanged data, appended samples, new columns and old sessions.
The full Linux suite passes: **139 tests, no skips**
(`/tmp/analizer-v211-complete-tests.log`). The additional existing-duplicate UI
refresh check passes (`/tmp/analizer-v211-repeat-ui.log`). Dependency and whitespace
checks pass. The Windows pipeline runs the complete suite and self-tests both
portable and single-file executables before uploading **v2.1.1** downloads.

The following section preserves the earlier 2.1.0 validation record.

# Studio 2.1.0 validation — 15 October 2026

The earlier-feature audit is recorded in [FEATURE_PARITY.md](FEATURE_PARITY.md).
The restored capabilities use one Qt frontend. Earlier Tk application copies are
not reintroduced into source or bundles.

Validation uses CPython 3.12.14, PySide6 6.10.2 and PyQtGraph 0.14.0 on Linux with
Qt xcb and a dummy Xorg display. Targeted GUI checks also run with Qt offscreen.

## Regression coverage

The complete suite contains 127 tests: the existing numerical, ingestion,
synchronization, comparison, cursor and export regressions plus 23 restored-feature
checks and seven time-conversion checks. The full run passes with no skips.

Restored-feature checks cover:

- Single-file and synchronized recordings; seconds-to-minutes offset conversion;
  original source rows, KPIs, quality tables and complete diagnostic workbooks.
- Explicit comparison mappings; source/curve/calibration/metadata worksheets;
  image-profile extraction and preservation of unverified calibration status.
- Simulation references opened without bench data and recorded-only phase spans.
- Actual seconds/milliseconds/hours/datetime conversion to minutes, old session
  ranges/cursors/masks and countdown conversion, minute-based interval exports,
  unchanged source tables and unchanged physical FFT frequencies.
- Old and new presets, deferred application, invalid setting rejection, channel
  colors/styles/widths/ranges, left/right axes and ten-panel session restoration.
- Normalized drawing with unchanged original data and cursor values, zoom history,
  clipboard readout, sparse-sample playback and timer cleanup.
- Plugin registration, sync/KPI hooks, enable/disable/reload/remove and invalid-hook
  rollback. Malformed configuration does not activate extensions.
- Persistence of studio settings and diagnostic tables; the default interface
  still has two workspaces and keeps advanced docks closed.

The expanded source/frozen entry self-test exercises presets, normalized tracks,
a Qt-hosted custom plot hook, complete workbooks and a calibrated image-reference
fixture in addition to Qt launch, FFT separation, snapshots, SVG/PDF/PNG, interval
Excel/CSV, icons and the established engineering checks.

## Build and runtime checks

- The Linux onedir PyInstaller bundle builds and passes its frozen self-test.
- The bundle includes the current studio tools, extension host and image engine;
  its packaging guard continues to exclude Tk and earlier application UIs.
- `pip check`, Python compilation and `git diff --check` pass.
- Windows builds use the same regression suite and bundled self-test for both
  portable-folder and single-file executables. Artifact name:
  **ApplianceSignalStudio-Windows-v2.1.0**. The title bar and EXE properties also
  carry version 2.1.0 to distinguish it from earlier downloads.

Evidence paths in the current environment:
`/tmp/analizer-v210-final-127-tests.log`, `/tmp/analizer-v210-final-build.log`,
`/tmp/analizer-v210-frozen-report.json` and the executable under
`/workspace/analizer-dist/ApplianceSignalStudio/`.

The fixtures are synthetic. Actual user recordings and dense performance
benchmarks were not rerun. Image extraction uses the known simulator color/tick
profile and retains uncertainty metadata; it is not arbitrary-chart OCR. Plugin
code may require additional libraries and plot hooks use the current pane layout.
Similarity bands are visual percentages, not engineering acceptance criteria.
