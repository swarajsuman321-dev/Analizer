# Appliance Signal Studio 2.4.1 — aligned plots and streamlined Data Portal

Prepared 23 October 2026. This release implements the user's explicitly approved graph-alignment and UI changes. Installed, standalone EXE and standalone ZIP/folder editions share the same source, version, manual and release cycle.

**Published and independently verified:** [v2.4.1 downloads](https://github.com/swarajsuman321-dev/Analizer/releases/tag/v2.4.1). The release tag and all three packages use tested source [`cf70f1e011315d928bb1d1c78b89c2161da12026`](https://github.com/swarajsuman321-dev/Analizer/commit/cf70f1e011315d928bb1d1c78b89c2161da12026). See the [permanent native/public evidence](validation/release-v2.4.1.json) for final measurements and remaining checks.

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

The [final native Windows workflow](https://github.com/swarajsuman321-dev/Analizer/actions/runs/39891732273), [job 120212833890](https://github.com/swarajsuman321-dev/Analizer/actions/runs/39891732273/job/120212833890), completed successfully on the tested source above. **381 regression tests passed with zero skips** in 119.786 seconds. Actual packaged acceptance passed **42 real-recording checks in each of the three forms**, alongside packaged startup/restart, **seven installer lifecycle checks** and **twelve actual-GUI update/recovery checks**. The production update gate uses digest-pinned v2.4.0 EXE/ZIP/Setup; the separate installer engine/lifecycle fixture remains the real pinned v2.3.1 ZIP. No old application is bundled in the new distribution.

The regressions cover actual drawing bounds and cursor-pixel alignment with unequal axis counts, retention of numerical ranges after resize/navigation/layout changes, two-column Data Portal and legacy workspace restore, per-file context menu selection/removal isolation, retained Properties metadata and a single main About route. Manual/release-note checks verify the matching version reference and bounded release description. The [final evidence](validation/release-v2.4.1.json) records source, native outputs and the separate independent public-download checks; local/offscreen measurements above retain their original scope.

## Published artifacts and update feeds

Each public asset was independently downloaded and matched its official manifest by exact size and SHA-256:

| Form | Official download | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Installed Setup | [ApplianceSignalStudio-Setup-2.4.1.exe](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.4.1/ApplianceSignalStudio-Setup-2.4.1.exe) | 134,843,409 | `53c32165db4c1aa8b01dd4157c8ebfe67727157775e40ba7c1dce27cba285da6` |
| Standalone EXE | [ApplianceSignalStudio.exe](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.4.1/ApplianceSignalStudio.exe) | 154,947,356 | `490540513144e981f597334c833a4cb1913c6b90946d559f86eaccd80cde703e` |
| Standalone ZIP/folder | [ApplianceSignalStudio_Portable.zip](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.4.1/ApplianceSignalStudio_Portable.zip) | 155,789,725 | `8974f6bed1ea52e2bde3bec73757525ef30d0278e07610a9ad9afc143ba36ecc` |

Both latest-release and immutable v2.4.1 versions of `installer-update.json`, `update.json` and `zip-update.json` agreed on version, official URL, size and hash. ZIP CRC/inventory checks confirmed the complete runtime and current assets; these inventory checks supplement the native execution checks rather than execute Windows code themselves.

The [published v2.4.1 manual](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.4.1/v2.4.1.md) is **80,601 bytes**, SHA-256 `84cc58c9d7816c3098edf3e91211256d7609cdcb620d37cc6e5efbf0f5c109a6`. It matches the bundled ZIP manual byte for byte and the source manual after line-ending normalization. Public release-tag verification confirms the tested source commit. These checks are recorded in the permanent evidence without overwriting the immutable native validation asset.

## Remaining limits

The update harness invokes the current production updater against actual pinned v2.4.0 GUI processes; it does **not** click the previous binary's update UI. New-startup version/path and restored-workspace acknowledgement establish success. Fallback uses ordinary `--restore`; the retained previous-version GUI's survival and the independent recovery snapshot's load are checked separately. Restarting the previous installed runtime does not fully roll back Setup registration/shortcuts; rerunning its previous official Setup can still be required.

The Windows CI account is privileged; per-user registration scope is verified, but this is not a separate standard-user login or a clean VM without Python, and it does not certify antivirus behavior. The release is unsigned because no publisher identity was supplied. Physical mouse/wheel/box/keyboard checks, Windows 100/125/150/200% scaling, multi-monitor/GPU, keyboard-only/screen-reader, prolonged sessions and actual corporate-network policies remain separate human/platform checks. Source/offscreen geometry measurements and native automated outcomes do not certify those scenarios.

Engineering calibrations, phase meanings and acceptance limits remain configurable; no new manufacturer values are introduced. Source measurements and generated personal evidence remain outside the runtime replacement lifecycle.

## References

- [Version 2.4.1 user manual](../manuals/v2.4.1.md)
- [Installed and standalone distribution policy](DUAL_DISTRIBUTION_POLICY.md)
- [Previous approved-audit release record](RELEASE_2.4.0.md)
- [Current user workflow contract](USER_WORKFLOW_ACCEPTANCE.md)
