# Windows installation and update guide — v2.4.2

The per-user installer packages the same PySide6 workbench and complete tested one-folder runtime. Python does not need to be installed. Portable EXE and ZIP downloads remain available. All delivery forms share the v2.4.2 analysis engine and approved graph, cursor, reporting and data-handling improvements. See the [release record](RELEASE_2.4.2.md) and [complete manual](../manuals/v2.4.2.md).

## Try it on your PC

1. Save your workspace and close all Appliance Signal Studio windows.
2. Download **ApplianceSignalStudio-Setup-2.4.2.exe** from the [v2.4.2 release](https://github.com/swarajsuman321-dev/Analizer/releases/tag/v2.4.2).
3. Run Setup as your normal Windows user. Keep the suggested directory unless you need another writable location. No administrator rights are requested.
4. Optionally select **Create a desktop shortcut**, finish installation and launch the app. You can also search for **Appliance Signal Studio** in Start.
5. Open a recording or restore a saved workspace and check your templates and reports. The portable download can remain available for comparison.

Windows 10/11 x64 is the target. This trial installer is **unsigned**: no publisher signing identity was configured. Windows SmartScreen or organizational policy may require publisher approval. Follow your organization's policy rather than disabling its protections.

## Files and personal data

| Content | Location / behavior |
| --- | --- |
| Complete runtime | `%LOCALAPPDATA%\Programs\ApplianceSignalStudio\versions\2.4.2\` by default; direct startup without onefile temporary extraction |
| Settings and templates | Existing `%APPDATA%\ApplianceSignalStudio\`; confirmed TDMS keys, configurations and folder-only `dialog-history.json` retained |
| Installed-app reports/workspaces | Windows Documents directory, `SignalStudio_Output`; explicit `ANALIZER_OUTPUT_DIR` remains supported |
| Existing portable outputs | Remain in their original folder; source recordings and measurement outputs are not silently moved |
| Runtime verification logs | `%LOCALAPPDATA%\ApplianceSignalStudio\InstallerLogs\` |
| Shortcuts | Per-user Start menu; optional desktop shortcut; stable AppUserModelID |
| Previous installed runtime | Retained for recovery instead of deleting it before new startup succeeds |

The application recognizes a strict installed-layout marker. Runtime removal for installed copies belongs to Setup/uninstall; discovery and settings migration do not authorize deleting another edition or a recovery copy. Setup does not bundle an older application, use wildcard uninstall deletion, or delete user settings/measurement folders. Retained previous installed versions consume additional disk space until uninstall. Install outside personal data folders and keep saved measurements outside version directories.

## Updates, recovery and uninstall

Installed copies check `installer-update.json`; standalone EXEs use `update.json`, and standalone ZIP/folder copies use `zip-update.json`. All feeds restrict downloads to the official versioned release URL and require matching size and SHA-256. Installed copies reject portable EXE replacement. Offline updates accept `installer-update.json` alongside the matching versioned Setup EXE.

**Install update & restart** saves the current recovery workspace, waits for the app to exit and runs the complete Setup package. Setup extracts a private staged copy and verifies its startup in `PrepareToInstall` before changing installed files, shortcuts or registration. A failed check returns a hard installation error; it does not rely on ignored `AfterInstall` callback exceptions. Native CI subsequently starts the actual installed copy as a separate verification. A failed Setup causes the updater to restart the retained old executable with its recovery workspace. The prior version can also be launched directly from its version folder. The new visible app must acknowledge its exact version/path and restored recovery workspace before the update is recorded as successful. Failed startup/restore restarts the retained previous runtime using an independent valid snapshot. Full restoration of installer registration/shortcuts after late failure can require rerunning the previous official Setup; read the transaction’s RECOVERY.txt. Recovery runtimes and snapshots remain available after success too. Source files, settings, templates, workspaces and outputs remain outside runtime replacement ownership.

Use **Windows Settings → Apps → Installed apps → Appliance Signal Studio → Uninstall**. Uninstall removes application files recorded by Setup and shortcuts. Settings/templates, outputs and unowned files remain. There is no automatic personal-data deletion option.

Installed updates launched by **v2.4.2** run Setup quietly, then reopen the app and restore the workspace after verified startup. A downloaded Setup opened manually keeps its normal wizard. An installed **v2.4.1-or-earlier** copy can show Setup progress once while installing v2.4.2 because the already-running old app owns that updater. Subsequent installed updates launched from v2.4.2 use its quiet path. Setup logs, startup checks, recovery snapshots and the previous runtime remain available; Windows security or organizational prompts remain outside this guarantee.

## Build and validation

Build the existing native runtime with `build_windows.bat` / `build_exe.py`, then run `python scripts/build_installer.py` in the build virtual environment. Inno Setup 6.3+ is required to compile Setup; it is not required by end users. The GitHub Windows runner provides it. `scripts/check_installer.py` is an explicit disposable-CI lifecycle test and refuses to modify an existing registered installation.

The native gate exercises fresh installation, startup imports, Unicode/apostrophe paths, user-only registration, shortcut targets, running-app exclusion, repair, uninstall, upgrade using the digest-pinned actual v2.3.1 ZIP, and failed-health-check rollback. Tests preserve sentinel settings, measurements and an unowned file. CI-only old/broken installers are not published or bundled. Separately, production update/recovery transactions start the digest-pinned official v2.4.1 EXE, complete ZIP and Setup, then validate the new visible v2.4.2 application and independent recovery workspace. The current updater is invoked against those real prior GUIs; this does not click the previous binary’s embedded update interface. Native visibility checks cover quiet installed updates and a visible manual-Setup positive control.

**Published and verified:** [v2.4.2 downloads](https://github.com/swarajsuman321-dev/Analizer/releases/tag/v2.4.2) and [permanent native/public evidence](validation/release-v2.4.2.json). The [final Windows workflow](https://github.com/swarajsuman321-dev/Analizer/actions/runs/40464046500) for source `33ea570ff9d3eb3f050171a76e4bc48595970db7` passed **477 of 478 regression tests (one non-Windows-only test skipped; zero expected failures)**, 47 real-recording checks in each delivery form, packaged startup/restart, 7 installer lifecycle checks and 13 actual GUI update/recovery/visibility checks. The public Setup EXE was independently downloaded and verified: **135,000,968 bytes**, SHA-256 **`89de0b9aaa3fcf3940fc7afbde97bb96c381fd35b029bcb2664bf4b4d1e1cff7`**. Standalone EXE/ZIP downloads, all three feeds and published/bundled/source manual agreement were verified in the same record. The [v2.3.2 record](validation/release-v2.3.2.json) remains the historical installation baseline.

The native checks caught two important platform details: WScript shortcut inspection loses some Unicode characters (the replacement uses IShellLinkW), and Inno Setup intentionally ignores exceptions from file `AfterInstall` callbacks. Health verification now returns an explicit error from `PrepareToInstall`, which blocks before modifying the installed version. The installer-only diagnostic workflow exercises this hard gate with the real previous runtime; full release checks also run the actual newly installed application.

Windows CI uses a privileged runner account with per-user installer mode; this is not certification of a clean standard-user PC, every antivirus policy, or every GPU/display. The downloadable trial is ready for your PC check.
