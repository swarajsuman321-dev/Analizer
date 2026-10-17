# Installed Windows application: benefit and implementation scope

Assessment date: 2026-10-17. This is a proposed distribution change, not an installer shipped with v2.2.1.

## Recommendation

Offer a **per-user Windows installer as the main download**, with the existing portable ZIP as an optional alternative. Install a complete one-folder runtime rather than unpacking a single-file executable into a temporary directory at every launch. Users would not install Python or any libraries themselves. The analysis engine and Qt interface need no rewrite.

An installer and standalone operation are compatible: “installed” describes deployment, while “standalone” means the app includes everything it needs.

## What improves

| Area | Current single-file / portable download | Proposed installed application |
|---|---|---|
| First use | Find EXE or extract complete ZIP | Guided install, Start menu shortcut, optional desktop shortcut |
| Startup | Single EXE extracts its runtime on each launch; ZIP does not | Runtime already on disk; avoids one-file extraction overhead |
| Updates | Replace EXE in a user-chosen writable folder | Known application directory and managed version switching |
| Recovery | Previous EXE and saved recovery workspace | Keep previous complete runtime until new startup is acknowledged |
| Uninstall | User removes downloaded files manually | Windows Installed Apps entry; remove only application-owned files |
| Templates and presets | Already stored per user in AppData | Keep the same location and exact TDMS identity keys |
| Offline / restricted users | EXE or ZIP can be distributed by IT | Offline installer; per-user installation should need no administrator rights |
| Analysis results | Same engine and numerical behavior | No accuracy or feature gain from installation itself |

Installation does not repair a broken import workflow, add chart features, or inherently fix inherited updater environment variables. The v2.2.1 restart fix is needed in either deployment model. A one-folder installation specifically removes dependency on a temporary `_MEI` runtime, although security software can still block files in any distribution.

## Proposed layout

- Binaries: `%LOCALAPPDATA%\Programs\ApplianceSignalStudio\versions\<version>\`.
- Stable launcher / shortcut target: `%LOCALAPPDATA%\Programs\ApplianceSignalStudio\`.
- Settings, TDMS parameter templates and presets: existing `%APPDATA%\ApplianceSignalStudio\`.
- Reports and saved workspaces: a persistent user documents/output directory, never a version directory removed during upgrade. Preserve the existing output-folder preference and migrate its reference rather than silently moving measurements.

Use one stable Windows application identity across upgrades. A conventional Inno Setup installer is a practical fit for the existing PyInstaller one-folder build. A packaged MSIX deployment is an alternative for organizations already managing MSIX, but brings different signing and deployment requirements. Keep the current portable option for users who cannot run an installer.

## Implementation work and complexity

Overall scope is **moderate**. Installer scripting and shortcuts are straightforward; reliable updates, migration and rollback require most of the engineering effort.

1. Package the complete tested one-folder runtime; define stable install identity, version resources, shortcuts and uninstall rules.
2. Introduce an installation-mode record. Distinguish installed and portable updates explicitly; never replace a one-folder executable with a single-file release by accident.
3. Add a manifest entry for the installer/package alongside the existing EXE. Keep older clients' EXE URL, hash and size fields compatible.
4. Stage a complete new version, verify every package/hash, close the app after saving recovery state, launch with a fresh runtime environment, and switch the launcher only after successful initialization/restore. Retain the old version if startup fails.
5. Migrate portable settings using existing compatibility logic. Preserve custom templates and user outputs; remove only verified obsolete application files. Let the installer manage its own older versions instead of deleting arbitrary folders or other software.
6. Add installer, upgrade, rollback and uninstall checks to native Windows CI; publish tested EXE, ZIP and installer as distinct assets. Document installation, offline upgrades and recovery.

Code signing is strongly recommended for trusted distribution and smoother corporate deployment. It requires a publisher signing identity and a protected signing step. Signing does not guarantee that Windows or company security software will accept every release.

## Acceptance tests before making it the default

- Fresh per-user install under a non-admin account; paths with spaces, apostrophes and non-ASCII characters.
- Launch on a clean supported Windows x64 machine without Python or build tools.
- Upgrade from an installed version and import existing portable templates/workspaces without changed channel names, axes or cursor positions.
- Network interruption, bad checksum, cancelled update, locked files, failed runtime load and failed recovery restore: leave a runnable previous version.
- Open the app twice during an update; avoid partial replacement and competing installations.
- Uninstall removes application binaries and shortcuts while preserving user measurements and templates unless the user explicitly chooses their removal.
- Offline install/update, restricted write access, antivirus interactions, and IT deployment policies.

## Decision

The benefit is high for recurring users and managed PCs; the benefit is smaller for occasional users who prefer a ZIP. Keep the current source/portable workflow working while implementing the installed channel. Do not claim installer readiness until its native installation and rollback lifecycle has been exercised. No installer has been added merely as part of this assessment.
