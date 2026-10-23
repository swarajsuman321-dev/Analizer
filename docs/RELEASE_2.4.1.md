# Appliance Signal Studio 2.4.1 — aligned plots and streamlined Data Portal

Prepared 23 October 2026. This release implements the user's explicitly approved graph-alignment and UI changes. Installed, standalone EXE and standalone ZIP/folder editions share the same source, version, manual and release cycle.

## Scope

- Align actual stacked graph drawing edges across differing Y-axis counts, so identical time positions and cursors align visually. Coordinate axis margins without changing numerical time ranges, original timestamps or physical values. Preserve independent value axes, numerical Lock Time Axes and normal zoom/pan behavior.
- Keep **Channel** and **Unit** as the Data Portal columns. Retain per-file checkboxes, isolated file-wide/filtered selection and **Close Dataset** through each file header's context menu. Preserve filtering counts, removal/undo and original recordings. Channel Kind metadata remains available in Properties; the obsolete Kind/File Actions columns and Show channel kind View toggle are removed with approval.
- Remove the duplicate **Tools → About version** entry. Preserve the main **About → User Manual** and **About → About / Updates** routes, version details and all update capabilities.

## Compatibility and updates

Existing measurement data, source identities, channel metadata, workspaces and engineering configurations retain their existing formats. Restoring an older workspace does not recreate the removed tree columns or View toggle. The graph drawing correction does not alter stored numerical ranges or sample locks.

All three supported Windows package forms must be published together with matching versioned artifacts and feeds: installed Setup uses `installer-update.json`, standalone EXE uses `update.json`, and standalone ZIP/folder uses `zip-update.json`. Edition changes remain deliberate separate installations. Existing complete-runtime verification, per-attempt recovery snapshots and startup acknowledgement remain required. The native update gate uses digest-pinned official v2.4.0 EXE, complete ZIP and Setup for actual prior-GUI upgrade/recovery checks.

Installed late-startup recovery may restart the retained previous runtime while complete restoration of installation shortcuts/registration requires rerunning its previous official Setup. Recovery instructions and backups remain available. Settings, templates, source recordings, workspaces and outputs remain outside runtime replacement/uninstall ownership.

## Verification state

Full local suite passed: **379/381 tests**, with two Windows-only tests skipped, in 213.146 seconds. Enhanced real-recording acceptance passed **42/42**, with zero callback/runner errors and seven expected safety rejections. All 28 layout/theme/size cases passed actual pixel-alignment assertions (maximum spread 4.55×10⁻¹³ logical pixels; limit 0.5), while retaining exact numeric bounds. Five dedicated geometry regressions cover dynamic tick widths, axis removal, empty panes and restore. See [local evidence](validation/audit-v2.4.1-local.json).

Focused manual/navigation and release-note checks passed: **6/6**, 2.122 seconds, using Linux Qt offscreen with isolated settings/output/cache folders. Version-resource and current-manual consistency checks and `git diff --check` also passed. Historical version manuals were not regenerated. The manual checks cover documentation and retained UI routes; the source and real-data results above are recorded separately.

Native Windows packaging, actual packaged acceptance, update/recovery transactions and public download checksum verification are **pending** until recorded in final release evidence. Source/offscreen verification does not establish those results. The release must not be announced as verified solely because source changes or manual checks pass.

Required regressions cover actual drawing bounds and cursor-pixel alignment with unequal axis counts, retention of numerical ranges after resize/navigation/layout changes, two-column Data Portal and legacy workspace restore, per-file context menu selection/removal isolation, retained Properties metadata and a single main About route. Manual/release-note checks verify the matching version reference and bounded release description. Record final test counts, native workflow/source commit and download checksums in release evidence after completion.

Physical Windows DPI, multi-monitor/GPU, keyboard-only/screen-reader and prolonged-session checks retain their previously documented human/platform limits unless individually completed. Engineering calibrations, phase meanings and acceptance limits remain configurable; no new manufacturer values are introduced.

## References

- [Version 2.4.1 user manual](../manuals/v2.4.1.md)
- [Installed and standalone distribution policy](DUAL_DISTRIBUTION_POLICY.md)
- [Previous approved-audit release record](RELEASE_2.4.0.md)
- [Current user workflow contract](USER_WORKFLOW_ACCEPTANCE.md)
