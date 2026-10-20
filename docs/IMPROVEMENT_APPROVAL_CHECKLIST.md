# Audit review and improvement approval checklist

Reviewed 18 October 2026 against `origin/main` at `d9d9b2d17e61a97061ce37d1ddf2a12b8d0f6dba`, application **2.3.2**. This document proposes changes for approval; it does not record their implementation. Application code, tests, settings and released binaries were not changed by this review.

The user has confirmed that v2.3.2 installs, opens and works on their PC. That is useful installation feedback, not acceptance of every analysis or update scenario.

**Approval received:** the user selected **“Approve all A–H (Recommended)”**. All 26 core items are authorized; I1–I3 remain excluded. The [v2.4.0 implementation and verification record](RELEASE_2.4.0.md) tracks delivery. Checkboxes below preserve the original requested scope and are not a claim that every native/human acceptance check has already run.

## Decisions already confirmed

- Maintain **Windows Installed** and **Standalone** together: one source implementation, feature set, version, manual and release cycle, with working updates for each. Preserve the existing standalone EXE and ZIP forms. See the [distribution policy](DUAL_DISTRIBUTION_POLICY.md).
- Ask before removing or hiding capabilities. The proposed relocation of controls, optional descriptions and expert editors below requires approval with its group; the complete capability remains accessible.
- Use the latest graph-header placement requirement in [user workflow acceptance](USER_WORKFLOW_ACCEPTANCE.md): navigation beside Analysis/Comparison, rather than a separate global navigation toolbar. This supersedes the earlier global-toolbar criterion.
- Keep calibration, phase-code meanings, timing adequacy and acceptance limits configurable. Do not invent engineering values.
- Retain **four main report sections with readable pagination**. Four sections do not mean exactly four pages.
- Engineering Controls remains the default tab in its existing dock group. Preserve the enabled-by-default View panels, real time conversion to minutes, per-file selection isolation, and exact cursor colors A `#00D2FF` / B `#FF9F1C`.

## What the audits establish

The [v2.3.2 repeat test](audits/2026-10-18-repeat-test-v2.3.2.md) reports 275 local passes and two Windows-only skips, plus 18 passing original-file scenarios. The later [native release evidence](validation/release-v2.3.2.json) records 277 Windows passes with zero skips and packaged/installer checks. These results do not override the independently reproduced workflow failures.

The current-source review confirms the main time-link, duplicate-sample identity, split-layout, native FFT and report-rendering paths remain. This review did **not** rerun the full suite or regenerate the large engineering PDF. The four committed recording fixtures were checksum-verified successfully. The original-upload audit's 86-channel inputs and the committed-fixture audit's 91-channel inputs are different sets; their counts must not be combined.

The [engineering PDF review](audits/2026-10-18-engineering-pdf-usefulness-review.md) measured a supplied **v2.3.1** report with **4,049 pages**, including **4,020 anomaly pages**. The current v2.3.2 renderer still expands wide event tables vertically and includes all event records in the PDF; this is source-confirmed, not a newly generated v2.3.2 measurement.

## Already fixed or present — preserve and regression-test

These earlier findings are not new implementation requests:

- One primary navigation presentation with zoom/pan/fit icons and tooltips; its **location** still needs correction.
- Correct legend text through Dark → Light → Dark, signed comparison PDF differences, and automatic trace colors through presets/copying.
- Compact interval statistics including rate, coverage and Wh for verified power channels; actuator ON/OFF statistics remain distinct.
- Active-workspace appearance isolation, direct Close Dataset, isolated per-file checkboxes, TDMS first-use review and persistent known-parameter templates.
- Background normal workspace Save/Restore and atomic JSON/NPZ persistence. Source-preserving workspaces remain large; more informative progress/cancel is a separate improvement.
- Engineering report background worker/cancellation, mapping/unit review, target/actual speed roles, gap-aware calculations and detailed nine-sheet workbook. Review enforcement and PDF presentation need strengthening.
- Installed Setup updates and portable EXE updates with verified downloads and recovery mechanisms. Complete standalone ZIP updates and real application update acknowledgements remain gaps.

## Selectable approval groups

Groups A–H are **approved**. Optional I items still require explicit selection. Priorities indicate implementation order, not a claim that the audits established data loss or a Critical-severity defect.

### A — Plot and cursor correctness — first priority

- [ ] **A1: Reliable Lock Time Axes.** Adopt the active temporal pane's numerical bounds immediately; retain identical bounds across mixed units/axis widths after pan, wheel/box/button zoom, fit, resize, channel visibility, layout/theme/tab changes and restore. Turning the lock off restores independence; frequency/histogram/sample plots stay separate. Regression must catch the observed 40–80 versus 40.7463–80 minute discrepancy.
- [ ] **A2: One locked source sample everywhere.** Use channel ID plus sample index consistently in marker, readout, locked-value card, interval endpoints, export and restore. Test equal timestamps with different values, keyboard/drag stepping, masks, gaps, discrete states, crossing cursors and range clamping. Preserve duplicate source observations; keep absolute interval deltas consistent with the existing HUD contract.
- [ ] **A3: Safe chart processing.** Replace incompatible native transform actions with supported application operations, with no loss of the existing application FFT capability. Native FFT on/off must no longer throw `ScatterPlotItem.setFftMode` errors or incorrectly retain a time-domain label. Preserve valid clock/unit guards and existing application analysis routes.

### B — Graph workspace and navigation — first priority

- [ ] **B1: Correct the navigation location.** Move the single primary set beside Analysis/Comparison inside the graph header. Preserve Zoom X/Y/XY, Hand/Pan, Zoom In/Out, Fit/Reset, Lock Time Axes and Lock Cursors, existing icons, tooltips and shortcuts. Use accessible header overflow at narrow sizes; menus and shortcuts share the same actions and checked state. No duplicate global/plot navigation widgets or controls over signal data.
- [ ] **B2: Add the requested pane context menu.** Act on the clicked pane: Hand/Pan, Cursor, Zoom XY/X/Y, configured cycle snapping, Revert Zoom, comments/add/move annotation, Copy Chart and export. Revert restores the previous view and differs from Fit. Explain unavailable prerequisites; never invent cycle boundaries. Keep existing useful menu and keyboard routes.
- [ ] **B3: Make split plots readable.** Use balanced initial row/column allocation, retain deliberate saved proportions, and give every pane useful drawing space or scrolling. Proposed test criterion: at least 150 logical drawing pixels per pane, with scrolling when the screen cannot fit them. Exercise Single → Split → Grid → Single, import order, mixed units/actuators, resize and restore at 1024×680 and larger sizes. Keep tabs, legends, axes, cursor values and Readout reachable; no automatic hiding of user panels.

### C — Everyday data handling and compact controls

- [ ] **C1: Show recording and active-pane identity.** Use short, unique dataset aliases plus channel names in legends/readout, cursor selectors, hover, processing and reports. Show the current pane/scope clearly. Retain stable IDs, original technical names and full source details through tooltips/accessibility/export. Identically named channels from two files must be distinguishable.
- [ ] **C2: Protect work during Close Dataset.** Preview dependent derived channels when removal affects unsaved work and provide an Undo that restores channel IDs/data, dependencies, plot bindings and cursor locks. Keep direct per-file removal; original disk files and unrelated datasets remain untouched. Existing removal already works; this adds recovery.
- [ ] **C3: Clarify filtered selection and search errors.** Keep file-wide selection explicit; add a separate filtered-results action and visible/total counts per file. Never add a global cross-file Select All. Invalid regular expressions need an actionable inline message and clear result-state/recovery behavior, rather than a red border alone.
- [ ] **C4: Apply compact-form rules throughout.** Size simple forms to required controls; move optional prose to keyboard-accessible collapsed Help/tooltips and routine raw metadata editing to an accessible Advanced area. Use separate Symbol / Reference Unit / Scale fields with inline validation. Elide long selections with full-value access. Test required actions with long names, Help open/closed and Windows scaling; retain scrollable/resizable tabular mapping and TDMS forms. Approval includes relocation of optional prose and advanced editors, not deletion of their functionality.
- [ ] **C5: Use consistent action and output labels.** Explain active/selected/visible/all scope and CSV samples versus Excel summary-plus-samples accurately. Align zoom vocabulary, About/Updates naming and manual links while preserving all export formats, existing manual access and user configuration choices.

### D — Trustworthy engineering interpretation — first priority

- [ ] **D1: Enforce reviewed source roles.** Strengthen existing mapping review so target/command speed cannot silently become an actual/feedback conclusion. Resolve direct pressure versus pulse-time mappings with verified calibration where needed. Show source, canonical role, unit, mapping method and review status beside affected results; persist explicit overrides. Do not infer physical meaning from filenames or rename samples into a new unit.
- [ ] **D2: Explain report readiness before results.** Show usable results, top blockers and corrective actions before KPI tables. Distinguish missing source, ambiguous mapping, unverified unit/calibration, insufficient coverage, unsupported phase and unconfigured acceptance. Separate calculation completion, data adequacy and acceptance evaluation. Add reviewed test identity/conditions without treating filename hints as verified metadata.
- [ ] **D3: Surface timing quality and distinguish fault classes.** Show observed span, supported duration, coverage, duplicates, missing readings, effective gap threshold and acquisition policy beside timing-dependent quantities. Keep all applicable quality flags, rather than overwriting partial-coverage warnings with duplicate warnings. Label actuator/integration totals as supported-time totals. Separate acquisition quality, rule evaluation and appliance events; missing channels remain Not Evaluated, and gaps alone do not prove appliance faults. Preserve the documented conservative fallback until a reviewed acquisition policy is configured; no invented universal coverage limit.

### E — Useful engineering reports — first priority

- [ ] **E1: Bounded PDF summary with complete evidence.** Replace repeated full-event PDF expansion with grouped counts, affected-time union, longest intervals, first/last occurrence and representative evidence. Preserve all original events, IDs and grouping provenance in the complete workbook/CSV/JSON evidence. Proposed default target for the audited fixture: **8–12 readable pages across four main sections**, rather than a universal hard cap. Event growth alone must not increase default summary length; an explicitly selected detailed appendix may add pages. Show expected length and preserve cancellation. The audited case's 10,231 original log records must remain available in detailed output.
- [ ] **E2: Make plot scope explicit.** Default engineering summary scope to whole recording; offer active cursor interval or both explicitly. Display scope throughout and use it consistently for KPIs, PDF and workbook. Include numeric A/B positions and interval values when applicable, reviewed source-role labels, supported/unsupported coverage, event references and verified detail plots. Use print-readable colors and margins so labels/footer do not overlap; never fabricate phases or missing curves. Retain the quick interval-export route.
- [ ] **E3: Concise traceability and navigable output.** Keep source basenames/hashes, report ID, app/profile versions, mapping/calibration/acceptance references and readable calculation methods in the PDF. Retain full recipes/configuration in companion evidence with the same report ID. Add page numbers and contents/bookmarks. Avoid absolute workstation paths in shareable PDF metadata by default while retaining full provenance in the local evidence package.

### F — Processing feedback and responsiveness

- [ ] **F1: Validate processing inputs before Apply.** Display clock regularity, sample rate, Nyquist/cutoff range and confirmed physical units. Choose valid defaults for supported clocks; explain explicit resampling requirements for irregular clocks rather than weakening backend rejection. Unknown-unit integrals/derivatives must remain visibly unknown physical quantities. Correct the audit runner's assumption that changing cutoff repairs an irregular clock; unexecuted checks cannot count as passes.
- [ ] **F2: Improve generic operation progress and cancellation.** Add per-file/stage feedback, cooperative cancellation where safe, stale-result guards and recoverable failure handling for import, calculations and persistence. Save/Restore already run in the background; keep exact source preservation and atomic persistence. Do not claim a measured serialization duration is a measured UI freeze.
- [ ] **F3: Bring quick exports up to the worker standard.** Move the synchronous legacy Export Report path to safe background work with clear scope, progress/cancel, atomic completion and Open File / Open Folder actions. Snapshot the required view state safely before background work. Engineering exports already have a worker; preserve that capability and all formats. Failure must leave the workspace usable and avoid presenting a partial file as complete.

### G — Installed and standalone update parity

The shared two-edition development policy is already confirmed. These are the remaining implementation proposals needed to strengthen it:

- [ ] **G1: Complete standalone ZIP updates.** Detect EXE versus folder packaging and stage/verify/switch a complete ZIP runtime, including `_internal`, with rollback. Keep standalone EXE replacement working. Do not silently convert the folder edition into the onefile EXE or discard either existing download form.
- [ ] **G2: Explicit edition choice and coexistence.** Installed updates stay installed and standalone updates stay standalone. Prevent accidental offline-package conversion; changing edition requires a deliberate user decision. Updating/cleaning one edition must not remove the other edition or its recovery runtime. Check shared settings/templates compatibility when editions or versions coexist; keep outputs and originals safe.
- [ ] **G3: Confirm update success after real startup and recovery.** A process launch alone is insufficient: confirm the new actual application starts and restores the recovery workspace before reporting completion or pruning a backup. Handle post-launch runtime failure and restore failure with actionable recovery. Preserve the installer staged health gate and previous runtime, portable backup, verified downloads, proxy/offline support and cancellation.

### H — Acceptance gates and future-reference documentation

- [ ] **H1: Convert the open audit contracts to acceptance tests.** Cover A–F with original/committed real recordings plus synthetic duplicates, gaps, masks, missing units and invalid inputs. Include all file combinations, strict per-file isolation/removal, TDMS template reuse and unknown-only review, numeric unit/time correctness, source-preserving restore and PDF/workbook agreement. Preserve the resolved-feature regressions. Record failures, expected safety rejections, runner errors, skipped and unrun checks separately.
- [ ] **H2: Test the actual Windows editions and update paths.** Require fresh packaged checks for installed, standalone EXE and standalone ZIP; real old → new in-app updates with recovery restoration, failed health/start/restore, bad checksum, cancellation/interruption, locked files and unwritable destinations. Test installer repair/uninstall/data retention and side-by-side edition isolation. Add manual native wheel/box/keyboard checks, Windows 100/125/150/200% DPI and multi-monitor review; CI offscreen geometry alone does not certify these.
- [ ] **H3: Publish matching release evidence and current documentation.** Keep one source/version/manual/changelog and all supported artifacts/update manifests in the same immutable release. Do not publish a feature update for just one edition. Verify public checksums/feeds and record exact source commit, packaging and update outcomes. Update stale README/status sections while keeping dated audit reports as historical evidence. Document user-visible changes and remaining limitations for each release.

## Optional efficiency proposals — select separately

These are product improvements suggested in audits, not reproduced correctness failures:

- [ ] **I1: Smaller exact-preserving workspaces.** Benchmark and, if useful, replace verbose source-table cell JSON with a compact versioned representation, preserving exact data, atomic writes and automatic legacy JSON/XML/INI configuration compatibility. Keep original files unmodified and compare every restored array/source cell.
- [ ] **I2: Reusable two-recording comparison preset.** Suggest reviewed compatible channel pairs with file labels and explicit confirmation; retain intentional overlay and manual selection. Do not guess ambiguous sensors or units.
- [ ] **I3: Repeat-last-format export.** Offer a clearly labelled split export action for repeated PDF/Excel use; retain all existing format choices and the single-save-dialog path.

## Approval and implementation order

Choose **All A–H**, **Priority A/B/D/E/G/H**, or list group/item IDs. Optional I1–I3 are excluded unless named. A proposed order after approval is A → B → D → E → C/F, with G developed alongside and H validating each completed stage. Prioritize correctness and report interpretation before additional shortcuts.

Approval is recorded above from the user's explicit response. Optional unchecked tasks remain outside scope. If a selected task requires deleting/hiding a capability beyond the described relocation/replacement, ask again with the exact change.

## Sources and current code anchors

- [Original UI audit](audits/2026-10-18/README.md), [v2.3.1 retest](audits/2026-10-18-v2.3.1-retest/README.md), [real-file test](audits/2026-10-18-real-file-test-report.md), [real-user workflows](audits/2026-10-18-real-user-workflows/README.md), [v2.3.2 repeat test](audits/2026-10-18-repeat-test-v2.3.2.md), [engineering PDF review](audits/2026-10-18-engineering-pdf-usefulness-review.md).
- `app_plot_workspace.py`: layout allocation, geometry-sensitive `setXLink`, locked marker versus timestamp-based measurement, framework menu inheritance and legend labels.
- `app_workbench.py`: global navigation toolbar, readout/lock captions, removal coordination, compact forms/unit definition, generic worker and synchronous quick export; normal Save/Restore already backgrounded.
- `app_channel_portal.py` / `app_channel_store.py`: file-level selection/filtering, regex feedback and dependency-aware removal without undo.
- `app_engineering_reports.py`: wide-table expansion and unbounded event rendering. `app_engineering_analytics.py`: mapping/quality status. `app_engineering_trace.py`: supported-time/duplicate/gap policy. `app_engineering_ui.py`: existing review and persistence.
- `app_updates.py`, `app_installed_updates.py`, `app_installation.py`, `app_lifecycle.py`, `app_info.py`: edition dispatch, Setup/EXE transactions and cleanup. `.github/workflows/windows-build.yml`: shared artifact/release gate.
