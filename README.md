# Appliance Signal Studio 2.1.0

A standalone Qt workbench for recording import, channel analysis and reporting.
Python 3.12 is the supported development runtime.

![Current workbench with synthetic signals](docs/images/workbench.png)

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements-build.txt
.venv/bin/python main.py
```

On Windows use `.venv\Scripts\python.exe`, or build a portable executable with
`build_windows.bat`. See [BUILD_EXE.md](BUILD_EXE.md).

## Everyday workflow

1. **Open** CSV/text, Excel, ZIP-contained CSV, Parquet or JSON recordings. Data
   loads directly into the current Analysis or Comparison workspace. Clocks are
   detected from column names. Unlabelled numeric time is interpreted as seconds,
   then converted to **minutes**, as are seconds, milliseconds, hours and timestamps.
   Recognized simulator exports already in minutes are kept in minutes.
   Axes, cursor intervals, playback and processed reports use minutes; original
   source tables keep their recorded values. Data without a clock remains sample-indexed.
2. Check a channel to plot it; uncheck it to hide its trace. The master checkbox
   selects or deselects all channels, including those hidden by the search filter.
   Checks reflect the visible panes of the current workspace. Selecting a tree
   row inspects its properties without changing visibility.
3. Drag cyan **A** and amber **B**, or click / Shift-click the plot. Snap uses real
   coordinates from the first nonempty plotted channel. Other channels report
   their nearest original sample, preserving missing values and each channel's
   sampling rate. Turn Snap off for interpolated analog readouts. Cursor positions
   stay within the visible data extent; inverted cursors are supported with a
   positive ΔX and signed B−A ΔY. Select a readout row for its compact interval card.
4. Click **Export Report** and save a PDF summary, high-resolution PNG, Excel
   workbook or CSV. PDF/PNG include visible traces, independent axes, cursor
   positions and interval statistics. Excel includes original samples inside each
   pane's A/B interval plus a cursor-summary sheet. CSV contains interval samples
   and cursor coordinates. Each channel keeps its own clock; exports do not
   fabricate a shared sampling rate. Missing or masked values stay missing.

Different units use independent Y axes, with tick/label colors matching their
traces. Compatible viewports share panning and cursor coordinates. Time is displayed in **min**. Time and
frequency coordinates use separate panes; frequency analysis retains Hz. R fits the active plot; C toggles
cursors; Space enables panning.

See [FEATURE_PARITY.md](FEATURE_PARITY.md) for the earlier-feature audit and the location
of every restored capability.

**View** opens optional Engineering Controls, Properties, Channel Math, original
Channel Table and detailed interval statistics. **Analyze** applies a formula or
numerical operation directly as a derived channel. The advanced capabilities live under **Tools**, including channel styling, playback,
engineering diagnostics, image-reference calibration, presets and extension management.
There is no permanent sample-preview pane or separate legacy application. Save workspace writes a JSON manifest plus an
adjacent generation-named NPZ; keep both together when sharing/restoring.

## Engineering comparison

Engineering Controls aligns power/machine recordings and compares measured
machine data with simulation CSV/ZIP data. The established engine retains source
rows, feedback-channel preferences, raw pressure numbers labelled Pa, positive
integer actuator states (128 is ON), event alignment and missing-data rules.

Verified relative-difference metrics display **match = max(0, 100 − |difference
percent|)**. Match accents use ≥90%, 70–<90%, and <70% bands. Missing, unverified,
or zero-reference metrics remain neutral. These are similarity indicators, not
engineering acceptance limits. Color words are never printed as status values.
The same percentage rules and accents are used in PDF/PNG and Excel reports.

## Validation

```sh
python -m unittest discover -s tests -v
python windows_entry.py --self-test --report self-test.json
python -m pip check
```

Linux GUI tests need an X display (Xorg dummy or Xvfb); Qt-only runs may use
`QT_QPA_PLATFORM=offscreen`. The title bar and Windows EXE properties show **2.1.0**. The Windows build artifact
is **ApplianceSignalStudio-Windows-v2.1.0**. The source and frozen entry share the same Qt
frontend. See [VALIDATION.md](VALIDATION.md) for measured results and limitations.
