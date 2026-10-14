# Refactor validation — 15 October 2026

Current-instance checks used CPython 3.12.14 on Linux, PySide6 6.10.2,
PyQtGraph 0.14.0 and a dummy Xorg display with Qt xcb. The interpreter was
`/workspace/analizer-tools/venv/bin/python`.

- The complete 97-test regression suite passes with no skips. It includes the
  retained numerical, ingestion, synchronization, heater and comparison checks,
  current Qt integration tests and 18 focused usability/export scenarios.
- Native channel-checkbox clicks, master selection, filtered selection and
  per-workspace check states were exercised. Deselecting all channels removes
  traces and auxiliary axes and displays the empty-state placeholder.
- Actual mouse dragging, data/viewport clamping, nearest-sample snapping,
  mismatched clocks, missing/empty arrays, positive inverted spans and signed
  B−A differences were checked. Free cursor positions survive save/restore.
- Channel toggles preserve zoom and selected intervals. Hidden panes drop deleted
  channels. Linked panes retain common cursor coordinates and synchronized panning.
- Three independent unit axes match trace/tick colors. Resizing between
  1024×680 and 1600×1000 and toggling docks preserves canvas geometry.
- PDF/PNG reports include visible traces, A/B positions and interval statistics.
  PDF text readback verified cursor values, signed differences and summary metrics.
  PNG pixel checks verified cyan/amber cursors and percentage accents.
- Excel/CSV readback verified original interval samples, cursor coordinates and
  Excel match-cell fills. Threshold boundaries at 90 and 70 percent and invalid
  or unavailable percentages were tested. Saved scorecards restore without stale
  comparison data leaking into unrelated Analysis reports.
- The final Linux onedir PyInstaller bundle builds and passes its frozen self-test,
  including Qt launch, synthetic signals, FFT separation, snapshots, SVG/PDF/PNG,
  Excel/CSV reports, icons and retained engineering checks. The archive audit
  verifies that Tk and obsolete frontend/image-digitizer modules are absent.
- `pip check`, Python compilation and `git diff --check` pass.

The old Tk-controller/telemetry tests were replaced with current service and Qt
coverage because those interfaces were removed. Domain regression assertions were
retained. Screenshots and export fixtures use explicitly synthetic data.

Current evidence is outside the checkout:
`/tmp/analizer-final-97-tests.log`, `/tmp/analizer-final-bundle-report.json`,
`/tmp/analizer-final-release-build.log`, `/tmp/analizer-export-text.txt`, and
`/workspace/analizer-report-validation/`. The Linux executable is under
`/workspace/analizer-dist/ApplianceSignalStudio/`.

Native Windows executable generation and Windows driver behavior require the
Windows CI workflow. Linux validation does not certify that build. Actual user
recordings and dense-data performance benchmarks were not rerun in this refactor.
Similarity colors express the documented numeric match percentage, not acceptance
limits. No claim is made that all possible datasets or desktop environments have
been tested.
