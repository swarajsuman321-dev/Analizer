# Installed and standalone development policy

Confirmed by the user on 18 October 2026: future development must support both the **Windows Installed** application and **Standalone** application, including update capability in both. This is a standing product requirement, not a choice between editions.

## Shared implementation and release

- Maintain one application codebase, analysis engine, UI feature set, file-format support, configuration schema, version, versioned manual and changelog. Packaging-specific code handles installation, output locations, updates and recovery.
- Publish Installed Setup and the existing Standalone EXE/ZIP artifacts from the same tested source and version in the same immutable GitHub release. Do not overwrite an already published version or ship new functionality to only one edition.
- Any approved feature or bug fix must work in both editions. Verify actual packaged execution as well as source tests; disclose untested platform behavior.
- Preserve personal settings, reviewed TDMS mappings, presets, legacy templates, saved workspaces, outputs and source recordings across updates. Retain supported backward migration and recovery mechanisms.
- Ask before removing or hiding capabilities. Keep both existing standalone download forms; new implementations must not silently drop the ZIP option.

## Current release — v2.4.0

Installed, standalone EXE and standalone ZIP are published together with matching update feeds. The native gate passed 371 regression tests, 42 real-recording checks per form, installer lifecycle and twelve actual GUI update/recovery checks. See the [release record](RELEASE_2.4.0.md) and [permanent native/public verification evidence](validation/release-v2.4.0.json). Older ZIP copies require one complete v2.4.0 extraction into a separate writable folder to gain their new updater; recovery/registration limitations and human checks are documented there.

## Baseline support and remaining gaps — v2.3.2

This table records the pre-implementation baseline. The approved v2.4.0 source now adds complete ZIP updates, stricter mode isolation and restored-startup acknowledgement; its [implementation and verification record](RELEASE_2.4.0.md) separates completed source checks from native release gates.

| Delivery form | Current package and update path | Existing evidence | Remaining improvement |
| --- | --- | --- | --- |
| Installed | Versioned complete runtime inside per-user Setup. `installer-update.json` selects the versioned Setup asset; staged runtime health check precedes installation. Recovery workspace and previous runtime retained. | Native install, repair, old-runtime upgrade, failure gate and uninstall checks; packaged runtime startup; updater dispatch tested separately. | End-to-end real application update, recovery acknowledgement and post-launch failure recovery. |
| Standalone EXE | Self-contained EXE. `update.json` selects verified EXE replacement, with previous-EXE backup and independent PyInstaller restart. | Native PowerShell replacement/rollback operations with restart stub; packaged startup/restart checked separately. | End-to-end real application old → new update with workspace acknowledgement and late-failure recovery. |
| Standalone ZIP/folder | Complete runtime with `_internal`. Currently treated as generic portable and offered the onefile EXE update. | Packaged one-folder startup. | **No complete ZIP/folder update transaction yet.** Add verified whole-runtime staging/switch/rollback; do not describe current EXE replacement as ZIP-preserving update support. |

Installed and standalone already share a Windows build/release workflow and user-facing update controls. Different package metadata is intentional: installed users need Setup; standalone users need their matching standalone payload. The user experience and release version should agree while these internal mechanisms remain appropriate to each package.

The [v2.3.2 native record](validation/release-v2.3.2.json) reports 277 passing tests, zero skips and packaged/installer checks. Those checks are not a claim that the actual application has completed every old → new GUI update/restoration scenario. The user's successful installed-PC feedback is a separate positive result.

## Required behavior for future implementation

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

Retain automated native tests and add the missing actual-application transactions. Manual Windows DPI, keyboard/mouse, multiple-monitor and corporate-network checks remain distinct from automated/offscreen results. Source arrays, parameter meanings, calibration and acceptance limits must not be changed merely to make acceptance tests pass.

The current implementation gaps and proposed work are in [approval groups G and H](IMPROVEMENT_APPROVAL_CHECKLIST.md). This policy records the confirmed direction; publication of the policy does not imply those gaps are fixed or approve unrelated UI/report changes.
