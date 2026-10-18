# Appliance Signal Studio: real-file visual, functional and technical audit

Date: 18 October 2026 (Asia/Kolkata). Application version: **2.2.3**. Repository: [swarajsuman321-dev/Analizer](https://github.com/swarajsuman321-dev/Analizer). Tested commit: `be221590f12448eef12dc434153ff0a15600ae9e`.

## Verdict

Core automated workflows pass for the supplied recordings, but the application is **not free of visual and report-content defects**. Three high-priority findings concern omitted signed comparison differences, legend contrast after theme changes, and severe crowding at minimum window size. Passing regressions do not resolve those independently reproduced issues. This is a bounded audit, not proof of all possible behavior or appliance/IEC compliance.

## Verified results

- Full regression suite: **218 tests discovered: 217 passed, 1 skipped**, 137.997 seconds. The skipped test is native Windows PowerShell replacement/rollback; final outcome shown in unit-tests.txt (local evidence).
- Real-data scenarios: **18/18 passed**: all 15 nonempty combinations of four files; TDMS review/template restart; CSV, Excel, PDF and PNG active-interval exports; full mixed-workspace save/restore.
- Engineering: **6 completed successfully; 4 expected input rejections**. Repeated successful alignment adds no duplicate channels.
- Bundled source-entry self-test: `ok: true`, version 2.2.3; frozen: false. Details (local evidence).
- Dependency consistency: **No broken requirements found**. This does not establish security or vulnerability status.
- Four fresh visual captures reviewed: dark/light at 1440×900 and 1024×680, with all four files loaded and eight selected channels.

## Inputs and import behavior

| Uploaded recording | Bytes | Source table rows | Channels | Channel measurements | Nonfinite Y readings | Import seconds |
|---|---:|---:|---:|---:|---:|---:|
| Cotton 60 label with 9kg IEC load T-3.csv | 5,779,822 | 58,948 | 24 | 1,414,752 | 0 | 5.902 |
| SB30LF0_Cottons_VT0022_var4_7000g_20260731_1332_800RPM_40deg_Standard_R027_0000002_simulated_values.csv | 16,759,584 | 106,148 | 29 | 3,078,292 | 17,105 | 14.102 |
| Cotton 60 label with IEC load 9kg T-3.CSV | 15,248,384 | 155,196 | 6 | 931,176 | 2,415 | 4.685 |
| Temp_F43 9KG 1200RPM cotton 60 T3-001_20260812_124336_001.tdms | 6,771,896 | 11,363 | 27 | 305,779 | 0 | 1.152 |

Total: **86 channels, 5,729,999 channel measurements**. TDMS channel clocks have independent lengths, so source-table rows need not equal every channel's sample count. Import assertions verify finite, nondecreasing time coordinates normalized to minutes. Nonfinite Y counts are observations, not automatically defects. Timings were measured with other checks running and are not isolated performance benchmarks. SHA-256 fingerprints are in recording-results.json (local evidence).

The simulated file name indicates 7 kg / 40°C / 800 RPM, while the other recording names indicate 9 kg / 60°C and TDMS 1200 RPM. These are not an established matched-condition acceptance dataset. Comparison RED/MISSING/REVIEW statuses must not be interpreted as software test failures, appliance acceptance limits, or proof that the simulation is wrong.

## Findings and reproduction

| ID | Priority | Finding and evidence | Recommended correction |
|---|---|---|---|
| F01 | High | PDF comparison table omits supplied signed `delta`. Fresh probe provides reference `100 W`, candidate `115 W`, delta `+15.00 W`, percentage `+15.00%`, match `85`. PDF retains the other values but omits delta. Extracted PDF text (local evidence), PDF (local evidence). `app_workspace_io.render_report` selects `diff`, while the engine uses `delta`. | Use the actual score schema and label candidate minus reference explicitly. Add positive/negative/zero/missing PDF-content and Excel/PDF parity checks. |
| F02 | High | Theme changes leave legend rich text with the preceding palette: Dark renders `#182033`, Light renders `#e3eaf5`. Labels become difficult to read in actual-file screenshots. Fresh rich-text probe (local evidence). | Reapply/recreate rendered label text after setting the effective theme; check Dark→Light→Dark with rendered text and screenshot assertions. |
| F03 | High | At 1024×680, the default dock layout gives the analysis workspace **330 px** versus 746 px at 1440×900. Multiple unit axes and long labels compete with the graph; readout columns require horizontal scrolling. Geometry (local evidence), light minimum-size capture (local evidence). | Responsive docks and readout card sizing; preserve access to engineering controls, complete statistics and independent axes. Test narrow layouts with real long names. |
| F04 | Medium | Legend/readout channel names do not consistently expose file identity. The screenshot shows `Drump Speed`, `drum_speed` and a TDMS technical speed name from different sources without a visible file prefix. This raises source-selection risk in mixed-file work. | Use a consistent short dataset alias plus channel name, retaining full source identity in inspection/tooltips and exports. |
| F05 | Medium | Main navigation and graph header repeat zoom/pan/reset controls; the minimum-size view also collapses tab/header controls. Both actual-file captures reproduce the crowding. | Share actions and use one clear primary navigation presentation, preserving keyboard and menu access. |
| F06 | Low | README identifies version 2.1.7 while `app_version.py` and the self-test identify 2.2.3. | Update release/setup documentation to the tested version. |

Reproductions for F01/F02 use a small synthetic control to isolate the behavior. The visual captures and 18 scenario runs use the four uploaded recordings. Findings are not inferred solely from the earlier synthetic audit.

## Functional scenarios

Each input-combination scenario checks channel counts/visible traces, X/Y/XY constraints, locked cursor stepping, out-of-bounds pan, deselect/reselect all, and dataset removal from both workspaces. The workspace roundtrip compares every channel X/Y array and source DataFrame for equality. Export checks establish file creation and basic interval summary coverage, not independent correctness of every rendered cell or every possible interval.

| Scenario | Outcome | Seconds |
|---|---|---:|
| Input combination 0 | passed | 3.361 |
| Input combination 1 | passed | 6.896 |
| Input combination 2 | passed | 5.108 |
| Input combination 3 | passed | 3.69 |
| Input combination 0,1 | passed | 18.94 |
| Input combination 0,2 | passed | 7.188 |
| Input combination 0,3 | passed | 7.711 |
| Input combination 1,2 | passed | 13.285 |
| Input combination 1,3 | passed | 11.416 |
| Input combination 2,3 | passed | 8.478 |
| Input combination 0,1,2 | passed | 12.871 |
| Input combination 0,1,3 | passed | 10.563 |
| Input combination 0,2,3 | passed | 6.573 |
| Input combination 1,2,3 | passed | 11.372 |
| Input combination 0,1,2,3 | passed | 9.326 |
| TDMS first review and template restart | passed | 0.313 |
| Mixed input active interval exports | passed | 8.808 |
| Full mixed workspace save and restore | passed | 34.897 |

The complete mixed workspace roundtrip passed, but its JSON manifest measured **290,684,126 bytes** (plus its companion data file), and save/restore took 34.897 seconds in this concurrent run. This is a practical large-session storage/latency observation, not an isolated benchmark or demonstrated data-loss defect.

## Alignment and comparison

| Recording | Operation | Outcome | Detail |
|---|---|---|---|
| Cotton 60 label with 9kg IEC load T-3.csv | Intelligent (Heater ON to >1.5kW Spike) | passed | No duplicates on repeated alignment |
| Cotton 60 label with 9kg IEC load T-3.csv | First Drum Start to First Power Rise | passed | No duplicates on repeated alignment |
| Cotton 60 label with 9kg IEC load T-3.csv | Raw Timestamps (No Shift) | passed | No duplicates on repeated alignment |
| Cotton 60 label with 9kg IEC load T-3.csv | Manual Time Offset (Minutes) | passed | No duplicates on repeated alignment |
| Temp_F43 9KG 1200RPM cotton 60 T3-001_20260812_124336_001.tdms | Intelligent (Heater ON to >1.5kW Spike) | expected_rejection | The two recordings do not overlap after synchronization. Check their dates/time zones, choose drum-start or heater synchronization, or set a manual offset. |
| Temp_F43 9KG 1200RPM cotton 60 T3-001_20260812_124336_001.tdms | First Drum Start to First Power Rise | expected_rejection | Drum-start synchronization needs a drum speed/feedback channel in RD and an active power channel in PD. |
| Temp_F43 9KG 1200RPM cotton 60 T3-001_20260812_124336_001.tdms | Raw Timestamps (No Shift) | expected_rejection | The two recordings do not overlap after synchronization. Check their dates/time zones, choose drum-start or heater synchronization, or set a manual offset. |
| Temp_F43 9KG 1200RPM cotton 60 T3-001_20260812_124336_001.tdms | Manual Time Offset (Minutes) | expected_rejection | The two recordings do not overlap after synchronization. Check their dates/time zones, choose drum-start or heater synchronization, or set a manual offset. |
| Cotton 60 label with 9kg IEC load T-3.csv | Comparison against supplied simulation | passed | {'RED': 5, 'VALUE': 4, 'GREEN': 1, 'MISSING': 1} |
| Temp_F43 9KG 1200RPM cotton 60 T3-001_20260812_124336_001.tdms | Comparison against supplied simulation | passed | {'MISSING': 5, 'REVIEW': 5, 'RED': 1} |

The four TDMS alignment rejections are explicitly observed outcomes: nonoverlapping clocks or unavailable recognized drum feedback. The script labels these expected based on those error messages; it does not independently certify their physical cause. The manual-offset test uses 3.5 with the existing API and does not search for an offset that forces recordings to overlap. TDMS comparison still completes, with unavailable/unverified metrics disclosed. No channel-role mapping was guessed to force a result.

## Visual evidence

(Visual capture retained locally.)

(Visual capture retained locally.)

Additional captures: dark 1024 (local evidence), light 1440 (local evidence).

## Reproduction and technical scope

Python 3.12.14 on Linux; existing Qt dependencies with declared npTDMS 1.12.1 installed. Xorg dummy display `:99`, `QT_QPA_PLATFORM=xcb` for the final suite and screenshots. Source self-test used `offscreen`. Writable `ANALIZER_SETTINGS_DIR`, `XDG_CACHE_HOME` and `MPLCONFIGDIR` were set under the scratch audit directory. No HOME variable was changed.

Git fetch from origin succeeded after enabling command network access; local HEAD matched origin/main at the tested commit. Initial setup attempts hit unavailable proxy access, missing npTDMS, no display, or read-only default settings. Those incomplete runs are excluded from final results. An unrelated preexisting text attachment was excluded from the four-file scope.

Re-run the repository's `python -m unittest discover -s tests -v`, `python windows_entry.py --self-test --report self-test.json`, and `python -m pip check` in that environment. For actual recordings, run `tools/audit_recordings.py` with four `--input` paths, `--output` and `--full-workspace`; run `tools/audit_engineering_recordings.py` with `--machine`, `--power`, `--simulation`, `--tdms` and `--output`. Machine is the timestamped Cotton CSV; power is the WT500 uppercase CSV. Visual capture script (local evidence) and isolated report/legend probe (local evidence) are retained locally for reproduction; their local paths need adjustment elsewhere.

The full regression suite exercises numerical/time handling, formulas, missing samples, cursor locks, independent axes, source preservation, lifecycle, templates, exports, update logic and other features named in its log. No independent penetration test, exhaustive fuzzing, sustained memory/performance study, manual screen-reader evaluation, native Windows EXE installation/update, Windows DPI test, or external engineering reference validation was performed. Test source-entry checks referring to Windows identity do not constitute native Windows execution. Raw uploads, exported measurement tables and the full saved measurement workspace are not committed with this report. Application code was not changed.


Publication scope: only this report file is published. Supporting screenshots, raw recordings, logs, machine-readable evidence and generated measurement exports remain local.

