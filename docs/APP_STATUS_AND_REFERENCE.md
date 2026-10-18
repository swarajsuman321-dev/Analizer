# Appliance Signal Studio: status, decisions and validation reference

**Latest verified release: v2.2.2.** See [current header/hover and release verification](HEADER_NAVIGATION_AND_HOVER.md) and [download the Windows release](https://github.com/swarajsuman321-dev/Analizer/releases/tag/v2.2.2). The audit below preserves its original version context.

Updated: **18 October 2026 (India time)**. Maintained in `swarajsuman321-dev/Analizer`.

The [v2.2.0 desktop finalization reference](DESKTOP_FINALIZATION.md) preserves the earlier layout, per-file controls, Help/About separation and lifecycle changes. Use the v2.2.2 reference above for current navigation and hover behavior. The audit below remains the historical v2.1.9 evidence.

## Historical v2.1.9 status and release evidence

The baseline at the start of this audit was GitHub `main` commit `e3b3367` and **published v2.1.8**. The official latest-release `update.json` was fetched successfully: version `2.1.8`, EXE size `154165843`, SHA-256 `9621fc57818b3a20dd3e9db0eaa2f856da762f05db382846c61108c26ea21d26`. This confirms publication, not connectivity from a particular user's corporate network.

**v2.1.9 is published and verified.** The [Windows workflow](https://github.com/swarajsuman321-dev/Analizer/actions/runs/39043439187) completed successfully for source commit `9790afefb794539ef88c2b299dfa93bc2ea5b9a1`: native updater/channel checks, the full regression suite, portable and single-file packaging, both packaged smoke checks, artifact uploads and release publication. [Download v2.1.9](https://github.com/swarajsuman321-dev/Analizer/releases/tag/v2.1.9).

The public latest-release manifest was fetched after publication and confirmed **2.1.9**, EXE size **154198660 bytes**, SHA-256 **`1bddc8c2b52f1c70ca78229ae85ef8de021843a1f35a8ddc082e01a30a4505a5`**, with the official versioned EXE URL. The source/manual/output-folder changes are therefore available in the downloadable app as well as `main`. Documentation-only updates after this source commit do not change the tested executable.

- [GitHub source](https://github.com/swarajsuman321-dev/Analizer)
- [Windows build workflow](https://github.com/swarajsuman321-dev/Analizer/actions/workflows/windows-build.yml)
- [Release downloads](https://github.com/swarajsuman321-dev/Analizer/releases)
- [Official latest update manifest](https://github.com/swarajsuman321-dev/Analizer/releases/latest/download/update.json)
- [Current complete manual](../manuals/v2.1.9.md), [feature inventory](../FEATURE_PARITY.md), [earlier validation](../VALIDATION.md)

## User requirements and decisions retained

| Requirement | Implemented behavior / reference |
| --- | --- |
| Simple analysis surface | Analysis and Comparison are the graph tabs; advanced tools remain available through compact tool menus and docks |
| No sample-preview pane or bundled old app | Direct workspace loading; PyInstaller excludes legacy frontends |
| Channel visibility | Native per-channel checkboxes plus master Select All/Deselect All; selection for operations is separate from visibility |
| Cursor identity | A cyan `#00D2FF`, B amber `#FF9F1C`, consistently applied to plot/readout presentation |
| Time | Elapsed time is numerically converted to minutes; explicit sample/frequency coordinates remain separate |
| Independent scales | Unit axes, synchronized X interaction, layouts and normalized tracks; cursor locks are available on any visible channel |
| Useful locked values | Readout and locked-channel cards show the anchor, its value and other channels at the same position; arrow keys step samples |
| Quick interval analysis | A/B, differences and interval/whole-recording statistics, including actuator ON duration/duty where valid |
| Zoom and reset | X, Y and XY modes, Pan, Fit/Reset and navigation shortcuts; selected modes constrain the actual gestures |
| Reporting | Main Export Report action; PDF/PNG and interval CSV/Excel, plus retained diagnostic/presentation exports |
| Actuators | Contextual automatic detection and explicit override; 0 OFF, nonzero finite integer ON, missing/fractional values unknown; numeric sensor/code channels stay numeric |
| Alignment | Existing channels are refreshed without duplicate samples/channels; unsuitable event/clock combinations report an error |
| Icons and updates | Bundled app/window icons; verified update download, recovery, backup/rollback, corporate proxy fallback and offline import |
| Info/manual placement | Top toolbar, separate nonmodal manual window, topic navigation/search and archived version manuals |
| View defaults | All View docks and Kind column enabled initially; tabified docks share space; saved preferences remain restorable |
| Complete data removal | **New:** Remove recording… and Clear workspace in Data Portal/Channel menu; both workspaces updated |
| TDMS parameter onboarding | **New:** first-import review of all measurement parameters, short editable names/units/interpretation, reusable template and unknown-only prompts |
| Stored outputs | **New:** persistent output folder beside the executable, visible/openable from Info |

The practical DIAdem-inspired capabilities are adapted to the existing Qt application; no external application's UI or proprietary code is bundled.

## Four supplied files and verified import results

The raw recordings are private test inputs and are **not committed**. Exact identities, sizes and SHA-256 values are in the [machine-readable import/scenario report](validation/four-file-audit-v2.1.9.json).

| Input | Source rows | Measurement channels | Projected measurements | Last elapsed time (min) |
| --- | ---: | ---: | ---: | ---: |
| `Temp_F43 9KG 1200RPM cotton 60 T3-001_20260812_124336_001.tdms` | 11,363 padded table rows | 27 | 305,779 | 232.366501 |
| `Cotton 60 label with 9kg IEC load T-3.csv` | 58,948 | 24 | 1,414,752 | 269.673100 |
| `Cotton 60 label with IEC load 9kg T-3.CSV` (WT500 power export) | 155,196 | 6 numeric projections | 931,176 | 269.700000 |
| `SB30LF0_Cottons_VT0022_var4_7000g_20260731_1332_800RPM_40deg_Standard_R027_0000002_simulated_values.csv` | 106,148 | 29 | 3,078,292 | 176.910000 |

TDMS source groups retain separate clocks and lengths; the source table's padded row count is not a per-channel sample count. Missing/nonfinite readings are retained as unknowns rather than fabricated values. The simulation has 17,105 nonfinite projected readings, and the power projections have 2,415; those gaps did not crash plotting or export.

Direct opening preserves duplicate timestamps and original tables. The engineering adapter has a documented causal clock-union/hold policy; alignment additionally reports its duplicate-timestamp policy. These are different views of the source, not silent replacement of native samples.

## Confirmed issues and corrections

| ID | Observed problem | Correction / regression evidence |
| --- | --- | --- |
| F1 | No obvious way to unload an entire recording | Remove recording picker, Clear workspace confirmation, removal in both workspaces, dependent derived traces/locks removed; originals/outputs retained |
| F2 | WT500 CSV failed Open with `Expected 2 fields in line 26, saw 4` | Generic import falls back to the established engineering header reader for instrument settings blocks; all 155,196 data rows load |
| F3 | WT500 separate Date/Time columns collapsed onto one timestamp | Combine Date + Time as an absolute clock before computing elapsed minutes; midnight crossing regression; actual span is 269.7 min |
| F4 | `Motor_temperatuer` was classified as an actuator and 25/30 became ON | Temperature spelling variants excluded from command detection; values remain numeric; targeted regression |
| F5 | Remaining-time measurements could be selected as the X clock | Automatic clock candidates exclude remaining/left/countdown measurements; absent clock uses sample coordinates |
| F6 | A large workspace operation can make the UI appear hung | User-triggered save/load now run in background workers with mutation guard; Qt event-loop responsiveness test |
| F7 | Source v2.1.8 retained v2.1.7 Windows version-resource metadata | v2.1.9 runtime version, Windows file/product version and CI artifact name synchronized |
| F8 | Technical TDMS labels and repeated setup burden | Review short names once; exact original identities stored with reviewed metadata; future known parameters load without prompting |
| F9 | Export destinations scattered/unobvious | Default output subfolders, Info path/open action, writable-folder fallback |

## Recording-removal behavior

**Remove recording…** lists every loaded dataset, including source-only diagnostic tables. It unloads the selected dataset's channels and derived descendants whose parent IDs depend on them; other loaded data remains. Source tables and plot traces from that entry are removed, locked references are released, readouts/axes refresh, and the comparison scorecard is invalidated rather than kept stale. Source data files are never deleted.

Aligned and comparison datasets imported/generated independently remain separate entries. Removing a raw source-only table does not retroactively erase independent aligned results; remove the result dataset too, or use **Clear workspace** for a complete reset.

**Clear workspace** confirms removal of every loaded dataset/channel from both workspaces, including generated channels without a dataset. It also clears the engineering file fields. Saved workspaces/reports/templates remain on disk. Removal is blocked while processing/saving/loading is active. It is not an undo operation; save a workspace first if needed.

## TDMS review/template contract

1. GUI Open/import loads into a temporary store, then presents **new** measurement identities for review before merging.
2. First import shows all measurement parameters. The review includes original name, suggested display name, unit, Automatic/Raw numeric/ON-OFF choice and sample count/range.
3. Short labels avoid invented meaning: e.g. a logger's V1 is initially **Valve 1**, not automatically “inlet valve”; device states/errors remain identified as such. Edit with hardware knowledge.
4. Save template and load writes `templates/tdms-parameters.json` atomically. It contains schema version 1 and a map keyed by exact original TDMS group/channel path, with name/unit/interpretation. No waveform/sample data is stored.
5. Known identities reuse choices; new identities prompt. Duplicate occurrences in a batch share one review row. Renaming the TDMS file does not discard known mappings.
6. Cancel leaves the workspace and template unchanged for that import batch. Invalid names cannot be saved. A corrupt/unsupported template is ignored with a review warning, rather than silently trusted.
7. **Channel → Review TDMS parameters…** revises loaded TDMS settings and future choices. Original names/source columns remain in metadata, raw tables stay intact, actuator raw values remain recoverable.
8. Units are declarations, not numerical conversion. Do not label an unknown speed as drum RPM or a raw pulse as pressure without establishing its meaning.

Programmatic `ingest()` remains noninteractive for tests/services. GUI import routes through review. Engineering workflows retain original source metadata and their own explicit mappings; a friendly display alias is not evidence of a physical calibration.

## Output and update locations

`SignalStudio_Output` is created beside the actual executable, never in PyInstaller's temporary unpack directory. Source execution uses the checkout directory. If that location is not writable, the app falls back to `~/Documents/SignalStudio_Output`. Info shows the **actual** chosen location. Developers/tests can explicitly set `ANALIZER_OUTPUT_DIR`.

| Subfolder | Content |
| --- | --- |
| `reports/` | Default PDF, PNG, interval Excel/CSV, processed/synchronized/presentation export destinations |
| `workspaces/` | Workspace JSON and generation-named NPZ companion |
| `templates/` | Reviewed TDMS parameter map |
| `diagnostics/` | Default complete diagnostic workbook destination |
| `presets/` | Reusable channel/view presets |

Save dialogs start in these folders; users can choose another destination. Outputs are only generated on a save/export action. `SignalStudio_Output/` is ignored by Git. Update download/cache/recovery uses the updater's own established staging directory and is separate from user reports.

### Screenshot: v2.1.5 `getaddrinfo failed`

This is a DNS/network/proxy-resolution failure in the installed version, not proof that GitHub lacks a release. v2.1.8 adds Windows Internet Options/PAC/SSO proxy fallback and actionable diagnostics. HTTPS verification remains enabled. Corporate policy can still block GitHub; an application cannot fix an unavailable connection or overrule that policy.

An installed v2.1.5 which cannot connect needs a **manual approved download once** to gain these newer networking/offline controls. For subsequent offline updates, provide the official `update.json` and EXE together, then use **Info & manual → Import offline update…**. Size/SHA-256/official location/version are validated. Source builds do not install themselves as a Windows EXE. The existing recovery, backup and rollback logic remains.

## Test coverage and evidence

- **188 regression tests passed locally**, one Windows-only test skipped on Linux; the full Windows build subsequently passed with its native checks and both packaged smoke tests. Command: `python -m unittest discover -s tests -v` with `QT_QPA_PLATFORM=offscreen` and writable Qt/Matplotlib cache/output paths.
- **All 15 nonempty subsets of the four inputs passed**: each file alone; six pairs; four triples; all four. Each checks all trace membership, X/Y/XY zoom constraints, locked sample stepping, out-of-bounds pan, deselect/reselect all and complete-recording removal from Analysis/Comparison.
- TDMS review: 27 parameters, saved template reload, zero unknown parameters after restart, unchanged native X/Y data.
- Mixed export: 86 summary channels, 7,115 active-interval rows; CSV/XLSX/PDF/PNG generated successfully. Existing tests separately verify cursor metadata/match colors and numerical report contents.
- Full workspace: 86 channels/four datasets saved/restored with exact projected arrays and source DataFrames; JSON `290681800` bytes; measured round trip **53.027 s** on this executor. This is an observed result, not a hardware-independent guarantee.
- Eight focused lifecycle tests cover cancellation, unknown-only prompting, corrupt templates, interpretation reversibility, clock selection, dependency/lock cleanup, persistent output defaults and background workspace save/load.
- Source smoke includes icons, bundled manual/topics, TDMS reader/review/template persistence, whole-recording removal, mouse hover, FFT separation, reports, presets, normalization, extensions, full workbook and image calibration.
- The Remove recording and Clear workspace buttons were also exercised through their actual Qt signals, including cancelled and confirmed clear actions.
- Review dialog inspected visually at 1000×650: original labels elide with full-path tooltips, short editable labels remain visible, and interpretations/ranges fit beside them.

### Engineering scenarios and deliberate rejections

Detailed outcomes: [engineering audit](validation/engineering-audit-v2.1.9.json).

- Supplied machine CSV + power CSV: all four built-in synchronization strategies completed; refreshing an alignment added **zero** new duplicate channels (30 aligned channels).
- Supplied TDMS + power CSV: raw timestamps and a small manual offset correctly reject **non-overlapping August and October recordings**.
- Intelligent heater alignment also cannot establish this pairing: the supplied TDMS heater command is **always OFF**. No active heater event is available.
- Drum-start strategy requires drum speed/feedback. The supplied TDMS exposes **motor** actual/reference speed (up to ~31,908), which cannot safely be treated as calibrated drum RPM. This combination is rejected; a display rename is not a gear-ratio conversion.
- Machine CSV and TDMS each complete comparison against the simulation. The CSV scorecard has missing metrics; TDMS additionally has REVIEW/MISSING entries. These are retained rather than falsely reported as a confirmed match. Use explicit mappings/confirmed units for the test setup.

These expected refusals are data/precondition results, not successful synchronization. The automated report labels them `expected_rejection` separately from `passed`.

## Reproduction

Install the pinned build requirements into a venv; run on Windows for native desktop testing or set Qt offscreen for Linux automation. Keep the four recordings outside the repository.

```bash
python -m venv .venv
# Activate the venv using the command for your OS.
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
python tools/audit_recordings.py \
  --input "recording.tdms" --input "machine.csv" \
  --input "power.CSV" --input "simulated_values.csv" \
  --output "/private/audit" --full-workspace
python tools/audit_engineering_recordings.py \
  --power "power.CSV" --machine "machine.csv" --tdms "recording.tdms" \
  --simulation "simulated_values.csv" --output "/private/audit/engineering.json"
```

The first script accepts arbitrary inputs. The second encodes this four-file fixture's expected incompatible TDMS/power cases; review those expectations when replacing the fixtures. Both reports record outcomes, not a claim of exhaustive verification. Generated CSV/Excel/PDF/images/workspace files may contain private measurements and must stay outside Git.

## Implementation map and release maintenance

| File | Responsibility |
| --- | --- |
| `app_channel_store.py` | Observable immutable channel data, dataset/dependency removal |
| `app_channel_portal.py` | Native channel checkboxes, filters, recording-removal controls |
| `app_ingestion.py`, `app_tdms.py` | General readers and native-clock TDMS projections |
| `app_tdms_templates.py` | Review dialog, short-name suggestions, template validation/persistence/application |
| `app_output.py` | Executable-relative output root, writable fallback and subfolders |
| `app_workbench.py` | GUI import/review/merge, removal coordination, asynchronous workspace save/load |
| `app_plot_workspace.py` | Independent axes, zoom/pan, cursor locks, sampling and graph layouts |
| `app_reporting.py`, `app_workspace_io.py` | Report data/snapshots and portable workspace persistence |
| `app_updates.py`, `app_info.py` | Verified updater, system-proxy/offline flows, manuals and output-folder access |
| `manuals/feature-guide.md`, `scripts/build_manuals.py` | Versioned manual source/generator (`python scripts/build_manuals.py 2.1.9`) |
| `tests/test_recording_lifecycle.py` | New import/removal/template/output/async regressions |
| `tools/audit_recordings.py`, `tools/audit_engineering_recordings.py` | Repeatable real-recording audit commands |

For a future release, synchronize `app_version.py`, all file/product versions in `version_info.txt`, CI artifact name, manual version and release notes. Run regression tests and both frozen smoke checks. The workflow publishes only after successful checks and treats an existing published release as immutable; fixes need a new version, not an overwritten EXE. Verify the public latest manifest's version, download URL, size and SHA-256 after publication.

## Limits and next review

No finite test run covers “every possible situation.” This audit covers the supplied files, all input subsets and the stated interaction/regression scenarios. Linux offscreen checks do not establish native Windows visual appearance; Windows CI and a human high-DPI desktop pass serve different purposes.

Large source-preserving JSON workspaces consume substantial disk/RAM and serialization time. Background operations keep repainting responsive but do not make the format smaller. Retain enough free disk space and keep JSON/NPZ together. Unknown engineering units, uncalibrated motor-to-drum conversion and unrelated recording dates require user/test-setup information rather than guesses.

Recommended human acceptance pass: open all four files on the target Windows machine, review TDMS names, reopen to verify no repeated prompt, verify one unknown parameter prompts, inspect high-DPI panel resizing/axis labels, remove one recording then clear all, open the output folder, and test updates through that machine's actual corporate network/offline policy. Those machine-specific checks are not claimed as performed here.
