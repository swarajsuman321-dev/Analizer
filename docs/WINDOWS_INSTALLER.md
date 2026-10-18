# Windows installer trial — v2.3.2

The per-user installer packages the same PySide6 workbench and complete tested one-folder runtime. Python does not need to be installed. Portable EXE and ZIP downloads remain available. Installation does not change the analysis engine or correct unrelated graph-layout limitations recorded in the existing v2.3.1 retest.

## Try it on your PC

1. Save your workspace and close all Appliance Signal Studio windows.
2. Download **ApplianceSignalStudio-Setup-2.3.2.exe** from the [v2.3.2 release](https://github.com/swarajsuman321-dev/Analizer/releases/tag/v2.3.2).
3. Run Setup as your normal Windows user. Keep the suggested directory unless you need another writable location. No administrator rights are requested.
4. Optionally select **Create a desktop shortcut**, finish installation and launch the app. You can also search for **Appliance Signal Studio** in Start.
5. Open a recording or restore a saved workspace and check your templates and reports. The portable download can remain available for comparison.

Windows 10/11 x64 is the target. This trial installer is **unsigned**: no publisher signing identity was configured. Windows SmartScreen or organizational policy may require publisher approval. Follow your organization's policy rather than disabling its protections.

## Files and personal data

| Content | Location / behavior |
| --- | --- |
| Complete runtime | `%LOCALAPPDATA%\Programs\ApplianceSignalStudio\versions\2.3.2\` by default; direct startup without onefile temporary extraction |
| Settings and templates | Existing `%APPDATA%\ApplianceSignalStudio\`; confirmed TDMS keys and configurations retained |
| Installed-app reports/workspaces | Windows Documents directory, `SignalStudio_Output`; explicit `ANALIZER_OUTPUT_DIR` remains supported |
| Existing portable outputs | Remain in their original folder; source recordings and measurement outputs are not silently moved |
| Runtime verification logs | `%LOCALAPPDATA%\ApplianceSignalStudio\InstallerLogs\` |
| Shortcuts | Per-user Start menu; optional desktop shortcut; stable AppUserModelID |
| Previous installed runtime | Retained for recovery instead of deleting it before new startup succeeds |

The application recognizes a strict installed-layout marker. Its portable cleanup code delegates installer-owned versions to Setup. Setup does not bundle an older application, use wildcard uninstall deletion, or delete user settings/measurement folders. Retained previous installed versions consume additional disk space until uninstall. Install outside personal data folders and keep saved measurements outside version directories.

## Updates, recovery and uninstall

Installed copies check `installer-update.json`; portable copies keep using the existing `update.json`. Both feeds restrict downloads to the official versioned release URL and require matching size and SHA-256. Installed copies reject portable EXE replacement. Offline updates accept `installer-update.json` alongside the matching versioned Setup EXE.

**Install update & restart** saves the current recovery workspace, waits for the app to exit and runs the complete Setup package. Setup verifies copied runtime startup before shortcuts/version registration. A failed Setup causes the updater to restart the retained old executable with its recovery workspace. The prior version can also be launched directly from its version folder. Runtime dependency failures and restoring user workspaces are distinct checks; retained files provide recovery if a later workspace restore fails.

Use **Windows Settings → Apps → Installed apps → Appliance Signal Studio → Uninstall**. Uninstall removes application files recorded by Setup and shortcuts. Settings/templates, outputs and unowned files remain. There is no automatic personal-data deletion option.

## Build and validation

Build the existing native runtime with `build_windows.bat` / `build_exe.py`, then run `python scripts/build_installer.py` in the build virtual environment. Inno Setup 6.3+ is required to compile Setup; it is not required by end users. The GitHub Windows runner provides it. `scripts/check_installer.py` is an explicit disposable-CI lifecycle test and refuses to modify an existing registered installation.

The native gate exercises fresh installation, startup imports, Unicode/apostrophe paths, user-only registration, shortcut targets, running-app exclusion, repair, uninstall, upgrade using the digest-pinned actual v2.3.1 ZIP, and failed-health-check rollback. Tests preserve sentinel settings, measurements and an unowned file. CI-only old/broken installers are not published or bundled.

**Verification pending:** final local/native counts, release run and public asset digests will be linked here after completion. Windows CI uses a privileged runner account with per-user installer mode; this is not certification of a clean standard-user PC, every antivirus policy, or every GPU/display. The downloadable trial is intended for your PC check after those gates pass.
