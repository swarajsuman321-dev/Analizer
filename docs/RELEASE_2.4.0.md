# Appliance Signal Studio 2.4.0 — approved audit implementation

Prepared 19 October 2026. The user approved **all A–H** in the [improvement checklist](IMPROVEMENT_APPROVAL_CHECKLIST.md). Optional I1–I3 remain outside this release. Both Windows Installed and Standalone delivery choices use the same application code, feature version and manual.

## Release state

Source implementation and local verification are complete. Native Windows build, actual packaged acceptance and update/recovery checks are mandatory before the release is published. See the workflow and the final release evidence before treating a download as verified; source/offscreen results do not certify native Windows behavior.

## Changes mapped to the approval

| Approved items | Implemented behavior |
| --- | --- |
| A1 | Numerical time bounds propagate between compatible temporal panes, independent of screen geometry and unequal value-axis widths. Locking adopts the active pane immediately; non-time domains stay separate. |
| A2 | Locked channel ID and original sample index govern marker, readout, cards, quick/engineering exports and restoration, including changed-value duplicate timestamps and scoped traces. Raw duplicate observations are retained. |
| A3 | Pane menus use supported application processing. Incompatible native FFT transforms cannot act on cursor scatter items; the application FFT remains available with clock validation. |
| B1 | One navigation set sits in the graph header beside Analysis/Comparison. Existing icons, shortcuts and menu actions share the active workspace's state. Narrow headers use overflow. |
| B2 | Clicked-pane context menu provides Hand/Pan, Cursor, X/Y/XY zoom, configured cycle snapping, previous-view Revert, annotations/move comments, Copy Chart and export. Unconfigured cycle snapping explains its prerequisite. |
| B3 | Balanced splits, retained proportions and scrollable minimum drawing space prevent crushed panes. Pane focus follows pointer navigation; later header commands act on that pane. |
| C1 | Unique short recording aliases qualify channel names, legends, readouts, locks and exports. Full original identities remain accessible. Active-pane scope is explicit. |
| C2 | Dataset removal previews dependent work and supports Undo with stable IDs, dependencies, bindings and sample locks. Later channels, pane work and metadata are preserved; originals remain untouched. |
| C3 | File-wide and filtered-results selection have separate actions/counts, without a global cross-file checkbox. Invalid regular expressions explain their error, clear matching channel results and retain file roots/removal access. |
| C4 | Compact selectors/forms keep required controls visible; optional prose uses keyboard-accessible Help. Structured custom metadata and local unit forms retain an explicit Advanced JSON editor. TDMS and mapping tables remain resizable. |
| C5 | Labels disclose source/active scope and export contents. About/Updates and manual access remain under About; source/diagnostic/processed export routes remain available. |
| D1 | Reviewed physical roles/units separate command from actual speed and direct pressure from uncalibrated pulse-time data. Saved explicit reviews persist; inferred labels cannot silently qualify an engineering result. |
| D2 | Readiness identifies usable results, missing sources, ambiguous/unreviewed mappings, unknown units, inadequate coverage, unsupported phases and unconfigured acceptance, with next actions. |
| D3 | Timing evidence shows requested/observed/supported spans, coverage, duplicates, missing values and effective gap policy. Independent quality flags remain together. Acquisition quality is separate from appliance faults. |
| E1 | Grouped event summary replaces the unbounded event dump. The real regression fixture produces ten PDF pages; every original event is retained in adjacent complete workbook/CSV/JSON evidence. Explicit mandatory/primary or acceptance-result overflow adds readable continuation pages; only an explicitly selected event appendix grows with event count. |
| E2 | Whole-run, cursor interval or both scopes recompute consistent KPI/comparison results. Graphs disclose reviewed source roles, missing support, event context and numeric cursor evidence when used. |
| E3 | Four main sections, page numbers/contents, concise methods, shared report IDs and source fingerprints support traceability. Raw configuration moves to complete companion evidence; default shareable PDF metadata uses source basenames. |
| F1 | Processing preflight shows clock/sample-rate/Nyquist/cutoff prerequisites before Apply; irregular-clock safety rejection remains. Unknown physical quantities stay unknown. |
| F2 | Generic workers show stage/file progress and safe cancellation for import, calculations, persistence and update preparation. Existing background Save/Restore and exact source-preserving format remain. |
| F3 | Quick report exports stage a complete artifact in a worker and commit atomically. Failure/cancellation preserves the previous complete output; successful exports expose Open File/Open Folder. Engineering bundles also roll back a partially failed multi-file publication. |
| G1 | Standalone ZIP updates verify, stage and switch the complete executable plus `_internal`; standalone EXE and installed Setup retain their matching mechanisms. |
| G2 | Edition mismatch is rejected with a deliberate manual-conversion route. Per-edition caches, per-attempt recovery snapshots and per-runtime locking protect coexistence. Discovery/migration no longer authorizes deleting another edition or its backup. |
| G3 | Real new startup and restored-workspace acknowledgement precede update success. Both recovery JSON and arrays are checked; onefile shutdown waits for its verified bootloader parent as well. Failure retains/restarts the previous runtime and exposes recovery diagnostics. |
| H1–H3 | New regression/real-file acceptance suites cover the previously missing contracts. Native CI now gates three actual package forms, production update transactions, source preservation, matching versioned artifacts and all three update feeds. The manual and evidence record tested versus unrun behavior separately. |

## Local verification

- Full local suite: **366 discovered, 364 passed, two native Windows tests skipped**, 168.002 seconds. Native CI reruns the complete final suite, including Windows-specific checks.
- Final header/hover interaction suite: **8/8 passed** at each of 100%, 150% and 200% simulated Qt scaling. It exercises real overflow-menu clicks and on-screen pointer movement; this is not physical Windows DPI certification.
- Source entry smoke: passed, version **2.4.0**, `frozen=False`.
- Real-file acceptance: **42/42 passed**, zero application callback or runner errors; seven expected safety rejections are recorded separately.
- Original real-user workflow diagnostic: **20/20 passed**, zero execution/callback/runner errors; one expected irregular-clock rejection.
- Additional worker tests verify responsive repainting, cancelled calculations, export/save atomicity, previous-file retention and frozen update intent while recovery stages in a worker.
- Dependency consistency check passed. Committed recording SHA-256 values remained unchanged.

The real-file suite includes all 15 nonempty combinations of the four committed fixtures, per-file selection/removal, TDMS known/new template review, exact source/workspace roundtrips, mixed layouts and exports. This remains a finite acceptance set, not every possible input or certified appliance/IEC evaluation.

## Engineering report regression

The supplied older report reviewed in [the PDF audit](audits/2026-10-18-engineering-pdf-usefulness-review.md) had 4,049 pages and 10,231 log records. The current hash-matched RD fixture produces a **ten-page summary** with **30,613 complete records, 30,613 unique event IDs and 31 groups**. Counts differ because acquisition quality can now be evaluated for additional mapped source traces without pretending their physical units/roles are verified. The original speed-gap observations remain; no event deletion is used to obtain the short PDF. A separate synthetic legacy-shaped regression preserves all 10,231 test records.

The actual fixture still has approximately 43.84% supported elapsed time under its documented 0.447-second fallback gap rule. Neither number is a universal limit or evidence of appliance faults. The current report exposes this policy/coverage, blocks unreviewed actual-speed and unknown-unit conclusions, and keeps acceptance Not Evaluated until configured.

Complete measurement outputs remain local. The repository stores the code, fixture manifest and validation summary rather than the generated measurement PDF/workbook/JSON/CSV.

## Update and migration guidance

| Current edition | Matching route |
| --- | --- |
| Installed | About → About / Updates; `installer-update.json` plus complete versioned Setup |
| Standalone EXE | Same interface; `update.json` plus the onefile EXE |
| Standalone ZIP/folder, v2.4.0 onward | Same interface; `zip-update.json` plus the complete portable ZIP |

Older ZIP/folder builds predate their own feed. **Download/extract the full v2.4.0 ZIP into a separate writable folder once**, retain the old folder/outputs until verified, then use complete-folder updates thereafter. An immutable older executable cannot retroactively gain the new update protocol before this migration. Installed and onefile users retain their existing update/manual-download paths.

Backups and independent recovery snapshots remain available after success. Installed late-startup failure restarts the retained previous runtime, but restoring Setup's registration/shortcuts fully can require rerunning its previous official Setup; the transaction's `RECOVERY.txt` explains that distinction. Do not delete the recovery folder while investigating failure. User settings, TDMS templates, workspaces, measurements and reports are outside runtime replacement/uninstall ownership.

The release is unsigned unless an approved publisher certificate is configured. Existing organizational publisher/network rules still apply; installation/update code does not disable them.

## Remaining human/platform checks

Native automation must pass before publication. Human acceptance still includes physical mouse/keyboard interaction, Windows 100/125/150/200% scaling, multi-monitor/GPU behavior, keyboard-only/screen-reader use, prolonged sessions and the user's actual corporate proxy/offline policy. Automated Qt gestures and offscreen geometry do not certify those scenarios. Calibration, manufacturer phase mappings and acceptance thresholds remain user/test-plan responsibilities.

## Maintenance references

- [Current user workflow contract](USER_WORKFLOW_ACCEPTANCE.md), [original real-user findings](audits/2026-10-18-real-user-workflows/README.md), [PDF review](audits/2026-10-18-engineering-pdf-usefulness-review.md).
- [Full v2.4.0 manual](../manuals/v2.4.0.md), [shared distribution policy](DUAL_DISTRIBUTION_POLICY.md).
- `app_cursor_identity.py`, `app_plot_workspace.py`, `app_channel_identity.py`, `app_compact_forms.py`, `app_channel_store.py` and `app_workbench.py` implement the desktop interaction corrections.
- `app_processing_preflight.py`, `app_operation_context.py`, `app_atomic_export.py` and `app_workspace_io.py` implement processing/worker/output safeguards.
- Engineering trace/analytics/session/report modules implement reviewed interpretation, timing quality, scoped results and complete evidence.
- `app_update_transaction.py` / `app_update_launcher.py` implement package-aware startup acknowledgement and recovery. `scripts/check_windows_acceptance.py` / `scripts/check_application_updates.py` exercise actual packaged applications on Windows.
- `tools/check_release_acceptance.py` and `tools/audit_user_workflows.py` reproduce source acceptance with isolated settings/cache/output directories.
