# Reconstruction validation — 14 October 2026

The failed workspace and its source archive could not be recovered. This is a
new implementation based on the handover and GitHub main at
042bb9e0b5eecf85387dee97dafbbe972692f2d7. The earlier 245-test evidence,
actual-recording counts and 38.86 ms pan p95 must not be attributed to it.

Validated on Python 3.12.14, Linux, dummy Xorg display :99 and Qt xcb.
The tested interpreter is `/workspace/analizer-tools/venv/bin/python`.

- 87 regression tests pass with no skips: 61 retained tests and 26 reconstructed
  domain, numerical, engineering and Qt integration tests.
- Source entry self-test passes, including Qt launch, sample telemetry, FFT
  coordinate separation, portable workspace and SVG export, as well as original
  ZIP/CSV, synchronization, pressure, heater, comparison, rendering and Excel checks.
- `pip check`, repeat installation, application launch and whitespace checks pass.
- Generated 1,000-row power, machine and simulation recordings validate import,
  exact source/channel snapshot restoration (17 channels and three datasets),
  processed CSV readback, and PNG/SVG/PDF/HTML/Markdown presentation exports.
- Generated recordings reproduce 1,000 aligned rows, zero-second event alignment,
  original power/machine/simulation workbook row counts, and a comparison scorecard.
- Qt regressions cover independent axes, frequency layout separation, linked
  cursors, per-tab state, hidden-pane persistence, masks, preview/apply, bounds,
  source selection, selected channels and rejection of obsolete worker completions.

The previous uploaded recording identifiers cannot be authorized or resolved in
this task. Original PD/RD/SIM recordings and their old numerical results were not
revalidated. Generated fixtures are explicitly synthetic.

## Dense renderer benchmark

Isolated raster benchmark: 100 channels × 100,001 samples, four viewports,
10,000,100 source points. Timing processes Qt events and forces painting via
`QWidget.grab`; this includes capture and full-widget raster rendering.

| Measurement | Median | p95 |
| --- | ---: | ---: |
| Painted synchronized pan | 192.45 ms | 209.48 ms |
| Painted dual-cursor update | 116.06 ms | 128.77 ms |
| Interval queries for 100 channels | 9.46 ms | 11.28 ms |

Binding and first paint: 4,841.71 ms. Displayed points: 8,203.
Peak process memory: 955.61 MiB. The initial reconstruction measured pan p95
413.61 ms; prepared paths and the workspace point budget reduced that cost.
These measurements exceed the 16.67 ms frame budget and do not demonstrate
sustained 60 FPS. Timings include forced captures and are not directly comparable
to the failed workspace's different benchmark implementation.

Current-instance evidence is outside the checkout:
`/tmp/analizer-full-tests.log`, `/tmp/analizer-reconstructed-self-test.json`,
`/workspace/workbench-validation-reconstructed/`,
`/workspace/engineering-validation-reconstructed/`,
`/workspace/workbench-benchmark-reconstructed/benchmark.json`.

## Reproduction

```sh
cd /workspace/Analizer
bash /workspace/analizer-tools/install.sh
bash /workspace/analizer-tools/start-display.sh
export DISPLAY=:99
export XDG_CACHE_HOME=/workspace/analizer-tools/cache
export MPLCONFIGDIR=/workspace/analizer-tools/cache/matplotlib
/workspace/analizer-tools/venv/bin/python -m unittest discover -s tests -v
/workspace/analizer-tools/venv/bin/python windows_entry.py --self-test --report /tmp/analizer-self-test.json
/workspace/analizer-tools/venv/bin/python tools/validate_workbench.py --benchmark-only --channels 100 --samples 100001 --output /tmp/workbench-benchmark
```

For actual recordings, run `tools/validate_workbench.py` with `--power`, `--machine`,
`--simulation`, and `--output`. `tools/validate_recordings.py` accepts the same
paths, a synchronization `--strategy` and `--output` for the established pipeline.
Run timed benchmarks after other CPU-intensive work finishes.

Offscreen Qt tests may use `QT_QPA_PLATFORM=offscreen`, but retained Tk GUI tests
require a real virtual display. Native Windows packaging and drivers remain
unverified. Derived channels do not automatically recompute, drag-to-shift is not
implemented, and commercial DIAdem interoperability is not certified.
