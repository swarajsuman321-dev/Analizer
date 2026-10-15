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
