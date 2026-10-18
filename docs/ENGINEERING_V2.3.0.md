# Appliance Signal Studio v2.3.0 — approved implementation and validation

Updated 18 October 2026 (India time). The user approved **all 36 audit items**, then confirmed that mappings/calibrations/limits must stay configurable and PDF reports should use **four sections with readable pagination**. This is an extension of the existing PySide6 app, not a replacement frontend.

The final patch release is **v2.3.1**: it additionally repaints existing legend rich text on theme switches and wraps/rounds PDF table text to prevent clipped long names. All v2.3.0 capabilities remain included. The older real-file audit is preserved in `docs/audits/2026-10-18-real-file-test-report.md`; its F01 delta and F02 legend findings are corrected here. Focus Graph provides an explicit narrow-screen option; default docks remain enabled. Consistent dataset aliases in every legacy legend/readout remain a separate usability opportunity, not a claim of this release.

## Implemented scope

| Approved IDs | Implementation |
| --- | --- |
| U1/U2/U8 | Immediate Legend/Grid/Peak controls; compact advanced settings; workspace-specific appearance; no trace rebind for simple visibility changes. |
| U3/U4 | Inline Play/Pause/speed/seek/time/sample-step strip; optional recorded-phase details; compact missing-phase message; original playback timing retained. |
| U5/U7 | More shares existing Tools actions/categories and shortcuts; Channel Management/Preferences access; compact dock headers and explicit Focus Graph with exact layout restore. Engineering remains the default tab. |
| U6/T1 | Content-fitting dialogs, scrollable overflow and screen clamping; fresh-process Qt tests at 1×/1.25×/1.5× and both themes. Native Windows results are recorded separately after CI. |
| U9/U10/U11/U12/T4 | Correct preset colors and unique automatic copy colors; duplicate tab-row navigation removed as approved; bundled scalable zoom/reset/hand artwork; compact translucent small legends and complete scrollable many-channel legends outside the canvas. |
| A1/A2 | Five schema-1 JSON profiles, category-specific canonical domains/aliases/KPIs; reviewed mappings and source units; exact source identities and original names retained; ambiguity/duplicate matches never resolved by first-channel accident. |
| A3/A5 | Explicit physical conversion/calibration service; safe declarative KPI operators; seconds-based integration, stable statistics, counter-reset rejection and structured unavailable/partial results. No eval or magnitude-based calibration. |
| A4/A8 | Configured phases, analog threshold crossings, hysteresis/debounce/minimum duration, overlap and plot-linked phase ribbon/tooltips. Empty default phase rules do not guess firmware meanings. |
| A6/A7 | Optional subsystem results, requested washer sensor/channel coverage, energy/water/temperature/speed/vibration/counter metrics; enhanced cursor card reuses existing measurements and adds Wh. |
| C1/C2/C3 | Analysis/Reference/Candidate/Golden dataset roles; recorded/actuator/phase/cursor/event/manual anchors stored separately; independent clocks, analog/held sampling, explicit gaps and no extrapolation. Existing heater/drum/manual/five-second causal synchronization remains unchanged. |
| C4/C5 | Absolute/relative/time-dependent envelopes and uncertainty; exact supported-segment breach intervals/durations; expanded KPI deltas and separate ≤5%/≤10%/>10% accents. Existing match scoring is not overwritten. |
| R1–R7 | Current-session engineering generation; executive metadata/KPIs/explicit acceptance, phase breakdown, vector graphical evidence, anomalies/faults; nine named Excel sheets; hashes/profile/formulas/calibration/processing/alignment/quality traceability. Existing exports retained. |
| T2/T3 | Numerical, GUI, profile/schema, partial-input, gap/rate/discrete/cursor regression, report cancellation/atomic-output tests; worker-based analysis/reporting and cancellation; new resources included in PyInstaller. |

## Architecture and reusable services

- `app_appliance_profiles.py` validates and recognizes; `profiles/*.json` are declarative configuration.
- `app_engineering_units.py`, `app_engineering_trace.py` provide physical units and immutable, gap-aware projections.
- `app_engineering_analytics.py` supplies phase/KPI/anomaly services; `app_engineering_compare.py` supplies roles/anchors/envelopes/deviation math.
- `app_engineering_session.py`, `app_engineering_templates.py` persist configuration and confirmed mappings/units.
- `app_engineering_ui.py` integrates setup, guided rule forms, results, explicit comparison projections, ribbons and envelopes into the existing workbench.
- `app_engineering_reports.py` generates vector PDF and nine-sheet Excel with atomic replacement and cancellation.
- `app_compact_controls.py`, `app_adaptive_ui.py` reuse existing actions and playback; existing numerical/engineering synchronization remains in place.

No new runtime package is required. Existing NumPy/Pandas/PySide6/pyqtgraph/Matplotlib/openpyxl dependencies are reused. Profile data is bundled explicitly. Old workspace schema 1 and prior JSON/XML/INI loaders remain; engineering session/display configuration is additive. Archived manuals are not regenerated.

## Numerical and configuration rules

All new time calculations normalize to seconds internally; plots/readouts stay in minutes. Power integration is W·s/3600 → Wh; L/min integration divides by 60. Continuous signals interpolate only over supported spans, states/codes/counts are held, original duplicate rows are retained and analysis uses the last duplicate. Missing/fractional actuator values are unknown. Default analysis gap threshold is 3× median positive sampling interval, explicitly configurable; it does not change the older synchronization engine's causal tolerance.

Phase/state meanings, sensor calibration points, forbidden sequences, stall thresholds and formal acceptance limits are **not invented**. Default profiles include channel/KPI definitions and quality-gap checks; named appliance phases require confirmed rules. Verified calibrations must identify their input/output units and supported range; no extrapolation. Counter resets do not produce invented volume/retry totals. Missing inputs remain Not Available, while absent acceptance limits or incomplete coverage remain Not Evaluated.

Naive recorded timestamps need a declared `metadata.recorded_timezone` for absolute-clock comparison. Otherwise existing numeric coordinates are preserved with a warning. Explicit anchors remain available. Visual KPI bands never imply acceptance; historical simulation match scoring stays separate.

## Verification status

The final local regression discovered **266 tests: 265 passed and one Windows-only test skipped** (148.364 seconds). This includes 33 engineering numerical/report tests, 14 compact-workbench GUI tests and fresh-process Qt scale checks at 1×, 1.25× and 1.5× in both themes. The final Windows workflow passed **268 tests with no skips**, native updater/cursor preflight, both packaged smoke checks and the independent onefile update-restart check. The corrected publication workflow succeeded. The public v2.3.1 EXE was downloaded (154,501,578 bytes) and its SHA-256 matched the official manifest. See [native release evidence](validation/release-v2.3.1.json) and [bounded local/supplied-file evidence](validation/engineering-v2.3.1-local.json).

Source GUI/frozen-workflow smoke now exercises profile loading, a known 1000 W × 120 s energy calculation, engineering PDF, all nine workbook sheets, existing exports, TDMS templates, legacy workspace and update identity. Synthetic dark UI and PDF executive-cover renders were visually inspected. No actual measurement is included in those images.

A private-input audit loaded all four supplied recordings and ran all six pairwise analysis combinations without exceptions; engineering Excel was generated for each and a PDF was generated. Raw technical names/unknown units deliberately produced unavailable KPIs until reviewed. This demonstrates controlled partial availability, not validation of unprovided manufacturer calibration, phase semantics or all physical measurements. Inputs and output artifacts remain private; only bounded validation results may be committed.

## Practical limits and remaining configuration

- Reports can exceed four pages to keep the four required sections, tables and evidence readable, as explicitly approved.
- Missing calibration, aliases, phase maps or physical sensors cannot be replaced by software assumptions. Profiles are configurable starting points, not certified appliance test standards.
- Unknown/ambiguous matches require review; this intentionally prevents plausible-looking but unverified engineering numbers.
- Source-file SHA-256 is used when files exist; otherwise hashes are explicitly labelled as preserved-array hashes.
- Native scale testing uses real Windows Qt subprocesses in CI, but does not certify every monitor/GPU/remote-desktop/security-software configuration.
- A conventional Windows installer remains the separate assessment in INSTALLATION_OPTIONS.md; the approved 36-item scope retains tested single-file EXE and complete portable ZIP delivery.
