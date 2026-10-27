# Installed and standalone development policy

Confirmed by the user on 18 October 2026: future development must support both the **Windows Installed** application and **Standalone** application, including update capability in both. This is a standing product requirement, not a choice between editions.

## Shared implementation and release

- Maintain one application codebase, analysis engine, UI feature set, file-format support, configuration schema, version, versioned manual and changelog. Packaging-specific code handles installation, output locations, updates and recovery.
- Publish Installed Setup and the existing Standalone EXE/ZIP artifacts from the same tested source and version in the same immutable GitHub release. Do not overwrite an already published version or ship new functionality to only one edition.
- Any approved feature or bug fix must work in both editions. Verify actual packaged execution as well as source tests; disclose untested platform behavior.
- Preserve personal settings, reviewed TDMS mappings, presets, legacy templates, saved workspaces, outputs and source recordings across updates. Retain supported backward migration and recovery mechanisms.
- Ask before removing or hiding capabilities. Keep both existing standalone download forms; new implementations must not silently drop the ZIP option.

## Current release — v2.4.2

Installed, standalone EXE and standalone ZIP are published together with matching update feeds and the same trace-color, general-comparison, selected-graph fullscreen, panel-folding and remembered-folder capabilities. The native gate passed 477 of 478 regression tests (one non-Windows-only test skipped; zero expected failures), 47 real-recording checks per form, 7 installer lifecycle checks and 13 actual GUI update/recovery/visibility checks. See the [release record](RELEASE_2.4.2.md) and [permanent native/public verification evidence](validation/release-v2.4.2.json). ZIP copies older than v2.4.0 require one complete v2.4.0-or-later extraction into a separate writable folder to gain their folder updater; use the current v2.4.2 ZIP. Installed updates launched from v2.4.2 use quiet Setup; an older app may show progress once installing this fix. Manual Setup retains its wizard. Recovery/registration limitations and human checks are documented in the release record.

## Historical baseline and gaps — v2.3.2

This table records the v2.3.2 baseline, not current gaps. Version 2.4.0 introduced complete ZIP updates, stricter mode isolation and restored-startup acknowledgement; its published [implementation and verification record](RELEASE_2.4.0.md) records that release’s native/public results. Current follow-up behavior and verification are documented above.

| Delivery form | Package/update path in v2.3.2 | Evidence at that time | Improvement then required |
| --- | --- | --- | --- |
| Installed | Versioned complete runtime inside per-user Setup. `installer-update.json` selects the versioned Setup asset; staged runtime health check precedes installation. Recovery workspace and previous runtime retained. | Native install, repair, old-runtime upgrade, failure gate and uninstall checks; packaged runtime startup; updater dispatch tested separately. | End-to-end real application update, recovery acknowledgement and post-launch failure recovery. |
| Standalone EXE | Self-contained EXE. `update.json` selects verified EXE replacement, with previous-EXE backup and independent PyInstaller restart. | Native PowerShell replacement/rollback operations with restart stub; packaged startup/restart checked separately. | End-to-end real application old → new update with workspace acknowledgement and late-failure recovery. |
| Standalone ZIP/folder | Complete runtime with `_internal`. Was treated as generic portable and offered the onefile EXE update. | Packaged one-folder startup. | **No complete ZIP/folder update transaction in v2.3.2.** Verified whole-runtime staging/switch/rollback was required; EXE replacement did not preserve folder packaging. |

Installed and standalone already share a Windows build/release workflow and user-facing update controls. Different package metadata is intentional: installed users need Setup; standalone users need their matching standalone payload. The user experience and release version should agree while these internal mechanisms remain appropriate to each package.

The [v2.3.2 native record](validation/release-v2.3.2.json) reports 277 passing tests, zero skips and packaged/installer checks. Those checks are not a claim that the actual application has completed every old → new GUI update/restoration scenario. The user's successful installed-PC feedback is a separate positive result.

## Required behavior for every release

1. Detect the current packaging form reliably and use matching verified update metadata. Installed remains installed; standalone remains standalone. An edition conversion is a separate deliberate user choice.
2. Check, download, cancel, offline import and install/restart must be available in both delivery choices. Keep official release URL/version, size, SHA-256 and TLS verification, existing network/proxy support and actionable errors.
3. Preserve whole-runtime integrity for ZIP/folder updates. Updating the entry EXE alone cannot establish that `_internal` matches it.
4. Save recovery state before shutdown. Verify actual new startup and recovery restoration before reporting success or pruning recovery copies. Keep an actionable fallback after failure.
5. Updating, repairing or cleaning one edition must not remove another supported edition, its recovery copy or personal data. Verify shared settings/template compatibility during coexistence, including older/newer versions.
6. Show edition, version and actual output/settings locations clearly in About/Updates or its accessible details. Share features and manuals while explaining packaging-specific behavior.

## Release acceptance matrix

Each future release needs recorded checks for the affected paths, with a full release gate for all delivery forms:

| Check | Installed Setup | Standalone EXE | Standalone ZIP/folder |
| --- | --- | --- | --- |
| Bundled runtime startup; no separately installed Python needed | Required | Required | Required |
| TDMS/CSV import, known/new mapping templates, file isolation/removal, zoom/cursors, reports and workspace roundtrip | Same acceptance data and behavior | Same acceptance data and behavior | Same acceptance data and behavior |
| Actual previous-version → new-version in-app update and restored-workspace acknowledgement | Whole Setup | EXE transaction | Complete folder transaction |
| Invalid/cancelled/interrupted download, checksum failure and offline package mismatch | Required | Required | Required |
| Locked/unwritable target, startup/restore failure, recovery preservation | Required | Required | Required |
| Settings/templates/output/source preservation and side-by-side isolation | Required | Required | Required |
| Installation repair, shortcuts, uninstall and user-data retention | Required | Not an installation action | Not an installation action |
| Public artifact/version/feed/checksum agreement from the same source | Required | Required | Required |

Retain automated native tests and actual-application update/recovery transactions for every release. Manual Windows DPI, keyboard/mouse, multiple-monitor and corporate-network checks remain distinct from automated/offscreen results. Source arrays, parameter meanings, calibration and acceptance limits must not be changed merely to make acceptance tests pass.

[Approval groups G and H](IMPROVEMENT_APPROVAL_CHECKLIST.md) document the historical gap analysis and acceptance scope. Published release records and native/public evidence state what is implemented and verified; the release acceptance matrix remains mandatory for future versions. This policy does not authorize unrelated feature removals or UI/report changes.
