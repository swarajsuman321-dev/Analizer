# Repeat visual, functional and technical test — Appliance Signal Studio 2.3.2

Date: 18 October 2026 (Asia/Kolkata). Repository: `swarajsuman321-dev/Analizer`. Latest origin/main was fetched, then tested in an isolated detached worktree at **1d8d54c96ed2aa10c1d159b6895224dee751787b**. Earlier baseline: 2.2.3 at `be221590f12448eef12dc434153ff0a15600ae9e`.

## Result

**Core regression and real-file scenarios pass; broader user workflows still fail.** The earlier missing PDF difference and theme legend defects are fixed. New workflow probes confirm inconsistent locked time ranges, native FFT callback errors, and a duplicate-timestamp cursor inconsistency. The minimum-size layout remains crowded. No application code was changed during this retest.

| Area | Result |
|---|---|
| Full regression suite | 275 passed, 2 skipped, 277 total; 230.864 seconds |
| Original real-file matrix | 18/18 passed |
| Alignment/comparison | 6 successful operations, 4 expected TDMS input rejections |
| Source-entry self-test | Passed, version 2.3.2, frozen=False |
| Dependency consistency | No broken requirements found |
| PDF comparison difference | Fixed: fresh extracted PDF contains `+15.00 W` |
| Legend palette transitions | Fixed: Dark `#e3eaf5`, Light `#182033`, Dark `#e3eaf5` |
| Expanded workflow audit on original uploads | 3 passed / 16 unmet / 19 evaluated contracts; 2 application callbacks and 1 runner error |

The expanded audit is a diagnostic acceptance script, not another unit suite. Its contracts include proposed UX expectations as well as correctness checks; an unmet contract is not automatically a new defect. The filter contract and runner error require special treatment below. Findings do not establish that new defects were introduced since the earlier release: the earlier audit did not check these exact interactions.

## Same four uploaded inputs

| Recording | Source table rows | Channels | Channel measurements | Nonfinite Y values |
|---|---:|---:|---:|---:|
| Cotton 60 label with 9kg IEC load T-3.csv | 58,948 | 24 | 1,414,752 | 0 |
| SB30LF0_Cottons_VT0022_var4_7000g_20260731_1332_800RPM_40deg_Standard_R027_0000002_simulated_values.csv | 106,148 | 29 | 3,078,292 | 17,105 |
| Cotton 60 label with IEC load 9kg T-3.CSV | 155,196 | 6 | 931,176 | 2,415 |
| Temp_F43 9KG 1200RPM cotton 60 T3-001_20260812_124336_001.tdms | 11,363 | 27 | 305,779 | 0 |

The original upload fingerprints and import counts match the previous audit: 86 channels, 5,729,999 channel measurements. Missing/nonfinite values remain represented. Every imported channel's time coordinates were checked for finite, nondecreasing values in minutes. TDMS channels retain independent clocks and lengths.

The repository now contains other machine/power recordings. Its default workflow audit was also executed as supplemental evidence, but the principal results here use a separate manifest and symlinks to the **original four uploads**, verified by their original SHA-256 fingerprints. The unrelated text attachment was excluded. No raw recordings or screenshots are newly published by this report.

## Confirmed findings and changes since baseline

### Resolved — comparison PDF signed difference

The fresh control uses reference `100 W`, candidate `115 W`, signed `delta=+15.00 W`, relative difference `+15.00%` and match `85`. The current rendered PDF and extracted text include the signed delta. The old renderer selected `diff`; the current renderer selects `delta`. This verifies the specific earlier omission, not every PDF cell or metric.

### Resolved — legend theme text color

Rendered rich text now changes correctly through Dark → Light → Dark: `#e3eaf5`, `#182033`, `#e3eaf5`. Fresh actual-file screenshots at 1440×900 and 1024×680 confirm improved contrast. The source now re-renders each label after setting legend color. Long technical channel names can still overflow narrow plot areas.

### High — locked time axes do not always share numerical time bounds

An independent displayed-window probe using Qt `xcb`, TDMS channels `PDH_TMT2_UC_T_IST_0_R` and `PDH_AAS_B_HEATER_ON_0_R`, vertical split, and Lock Time Axes enabled produced:

- First pane: `[40.0, 80.0]` minutes.
- Second pane: `[40.74626865671642, 80.0]` minutes.

The first pane was explicitly set to 40–80 minutes; the second starts about 0.74627 minutes later. The result also reproduces in the larger offscreen workflow audit after resize, pan, zoom, reset, visibility/theme/tab changes, restoration and mixed-unit layouts. Different axis widths appear relevant; this audit does not claim a complete root-cause diagnosis. Horizontal split and unlocked independence passed their respective checks.

Recommendation: link numerical X bounds while respecting independent Y geometry; add mixed-axis-width tests for these operations. Do not claim synchronized visible time merely because viewboxes are linked.

### High — native chart FFT toggle raises application callback errors

Reproduction: show a plotted channel and set the native Plot Options → Transforms FFT checkbox on, then off. Both transitions raise:

`AttributeError: 'ScatterPlotItem' object has no attribute 'setFftMode'`

The independent xcb probe recorded 2 callbacks, agreeing with the full workflow audit. This affects the native chart transform; it does not establish that the application's separate derived-channel FFT operation is broken. Recommendation: prevent cursor scatter markers from participating in framework spectral transforms, or replace/disable the exposed native option and route users to supported frequency analysis.

### High — duplicate-timestamp locked marker and readout disagree

In the original machine CSV, `Water Pressure` at **23.66913333333333 minutes**, anchor index **12779**, the locked cursor marker reports **1659.0** while the numeric readout displays **1660.0**. The automation checks actual marker data, channel sampling and displayed Readout A, rather than estimating from an image. Equal timestamps with different values require a consistent sample-index policy.

Recommendation: use the selected locked sample index consistently in marker, numeric readout, interval export and restoration; add a changed-value duplicate-timestamp regression.

### High — narrow/multi-pane layout remains cramped

The actual-file single workspace is still **330 px wide at 1024×680**, compared with 746 px at 1440×900, matching the earlier geometry. Readout columns require horizontal scrolling and long legend names consume the plot. The original-file split-layout audit measured only **65.1 and 66.1 logical pixels** of drawing height at 1024×680; its 150-pixel acceptance target is an audit criterion, not a measured accessibility standard. The larger split view passed that criterion.

Recommendation: responsive docks/readout sizing, scrollable multi-pane drawing areas or an explicit reversible focus mode, preserving engineering controls and complete data inspection.

### Medium — navigation placement and context-menu task coverage

The workflow observed the navigation toolbar parent as `AdvancedStudioWindow`, **40 px** from the tab-row center, rather than a graph-local header. The native context menu lacks explicit Zoom XY/X/Y, cursor, revert-zoom and comments actions. Those actions' absence from this context menu is a workflow/discoverability gap; the audit does not claim they are all absent from the rest of the application. Recommendations should preserve existing menu/keyboard routes.

### Low — documentation version remains behind code

README identifies 2.3.1 while runtime and `app_version.py` identify 2.3.2. The prior mismatch was 2.1.7 versus 2.2.3, so documentation has progressed but is still one release behind.

## Audit limitation discovered during processing checks

The default low-pass contract was marked unmet because the original power recording is not on a strictly increasing uniform clock. The application correctly rejects processing with `Explicitly resample onto a strictly increasing uniform clock first`. The audit then assumes a retry with cutoff 0.1 Hz succeeds, but it raises the same clock error. This is **one audit-runner assumption failure**, not evidence that a changed cutoff should repair an irregular clock. The later mixed-clock formula contract in that function was not reached and must not be counted as passed or failed in this run. Source processing functions were not modified to force a result.

## Core functional matrix

Every input-combination case exercises visible channel counts, zoom X/Y/XY constraints, locked cursor stepping, out-of-bounds pan, deselect/reselect all, and dataset removal across both workspaces. These checks do not test exact linked X bounds across unequal plot geometries, explaining why the broader lock probe can fail while the core matrix passes.

| Scenario | Status | Seconds |
|---|---|---:|
| Input combination 0 | passed | 3.821 |
| Input combination 1 | passed | 14.193 |
| Input combination 2 | passed | 3.902 |
| Input combination 3 | passed | 6.401 |
| Input combination 0,1 | passed | 20.255 |
| Input combination 0,2 | passed | 6.919 |
| Input combination 0,3 | passed | 7.723 |
| Input combination 1,2 | passed | 9.777 |
| Input combination 1,3 | passed | 11.191 |
| Input combination 2,3 | passed | 4.035 |
| Input combination 0,1,2 | passed | 7.459 |
| Input combination 0,1,3 | passed | 6.069 |
| Input combination 0,2,3 | passed | 3.908 |
| Input combination 1,2,3 | passed | 6.145 |
| Input combination 0,1,2,3 | passed | 8.532 |
| TDMS first review and template restart | passed | 0.284 |
| Mixed input active interval exports | passed | 10.17 |
| Full mixed workspace save and restore | passed | 40.456 |

The export scenario checks CSV, Excel, PDF and PNG file creation plus summary/interval coverage. The separate PDF control checks the earlier signed-delta omission. The full mixed workspace comparison asserts every channel X/Y array and original source DataFrame equal after restore. Times were measured concurrently and are not isolated benchmarks.

## Engineering outcomes

Both machine CSV and TDMS comparisons with the supplied simulation complete. Machine comparison has 11 metrics: RED 5, VALUE 4, GREEN 1, MISSING 1. TDMS comparison has 11 metrics: MISSING 5, REVIEW 5, RED 1. These match the previous run's classifications and are not software pass/fail labels.

All four machine CSV alignment strategies complete, and repeated merges add no duplicate channels. TDMS alignment rejects nonoverlap for heater/raw/manual strategies, and reports missing recognized drum-feedback requirements for drum-start alignment. The diagnostic runner classifies these expected based on explicit messages; it does not independently certify physical recording dates or choose a new offset to force overlap.

The simulation filename indicates 7 kg/40°C/800 RPM while the other filenames identify different load/temperature/speed conditions. No matched-condition scientific acceptance claim follows from this exercise.

## Expanded original-file workflow results

| Contract | Status | Expectation |
|---|---|---|
| NAV-HEADER | unmet | Zoom/pan controls are on the graph header beside Analysis/Comparison, not in a separate global toolbar. |
| RIGHT-CLICK | unmet | Right-click offers chart tasks: Hand/Pan, Cursor, Zoom XY/X/Y, previous zoom and comments on the clicked pane. |
| TIME-1 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after same-unit panes. |
| TIME-2 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after different units, stacked. |
| TIME-3 | passed | With Lock Time Axes on, compatible visible time plots have identical left/right limits after different units, side by side. |
| TIME-4 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after resize while locked. |
| TIME-5 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after pan second pane while locked. |
| TIME-6 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after zoom X while locked. |
| TIME-7 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after fit/reset while locked. |
| TIME-8 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after hide and show a pressure channel. |
| TIME-9 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after theme change while locked. |
| TIME-10 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after tab switch while locked. |
| TIME-11 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after restore saved view while locked. |
| TIME-12 | unmet | With Lock Time Axes on, compatible visible time plots have identical left/right limits after four mixed-unit panes. |
| TIME-OFF | passed | With Lock Time Axes off, I can inspect different time windows independently. |
| PANE-1536 | passed | Every visible split plot retains at least 150 logical pixels of drawing height or scrolls instead of being crushed. |
| PANE-1024 | unmet | Every visible split plot retains at least 150 logical pixels of drawing height or scrolls instead of being crushed. |
| FILTER-DEFAULT | unmet | The default low-pass cutoff fits the loaded sample rate, or the UI explains a valid range before Apply. |
| CURSOR-DUPLICATE | unmet | At a duplicate timestamp, the locked marker and numeric readout identify the same sample/value. |

Repeated TIME rows are interaction cases of the same consistency problem, not separate counted defects. FILTER-DEFAULT has the clock/runner limitation above. Navigation and 150-pixel pane expectations are diagnostic UX criteria.

## Reproduction and limits

Python 3.12.14, Linux, existing Python dependency environment; Xorg dummy display `:99`. Full regression, actual-file matrix, fresh visual captures and focused lock/FFT verification used `QT_QPA_PLATFORM=xcb`. Workflow audit used offscreen. Writable application settings and caches were separated by task under `/workspace/work/retest-20261018` without changing HOME.

Commands: `python -m unittest discover -s tests -v`; `python windows_entry.py --self-test --report self-test.json`; `python -m pip check`; `python tools/audit_recordings.py` with four original `--input` paths, `--output`, `--full-workspace`; `python tools/audit_engineering_recordings.py` with original machine/power/simulation/TDMS paths; `python tools/audit_user_workflows.py --samples <original-upload-manifest-directory> --output <scratch-directory>`.

Skipped native tests:

- test_native_setup_success_and_failure_restart_correct_runtime (test_installer.InstallerTests.test_native_setup_success_and_failure_restart_correct_runtime) ... skipped 'Native installed-update transaction is exercised on Windows CI'
- test_native_windows_replacement_and_rollback (test_updates.UpdateTests.test_native_windows_replacement_and_rollback) ... skipped 'Native PowerShell transaction is tested on Windows CI'

Supporting logs, JSON results, actual-file screenshots, synthetic control PDF/text, and focused reproduction script remain local. This report file alone is published under the earlier request to push the report. Native Windows installation/update/rollback, high-DPI scaling, screen-reader use, exhaustive fuzzing, penetration testing and long-duration performance were not independently executed. Passing source-entry self-tests do not constitute testing a frozen Windows executable.
