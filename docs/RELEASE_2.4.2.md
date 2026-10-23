# Appliance Signal Studio 2.4.2 — quiet installed-app updates

Prepared 23 October 2026. This focused update removes Setup's progress window from the installed application's update/restart path. Installed Setup, standalone EXE and standalone ZIP/folder retain the same application version, manual and release cycle.

## Behavior and scope

The current installed-app update launcher passes **`/VERYSILENT`** instead of **`/SILENT`** to Inno Setup. `/SILENT` skips the wizard but still displays installation progress; `/VERYSILENT` suppresses that progress window as well. Existing message suppression, installation directory, no-restart and logging arguments remain. This applies to Setup launched by the installed-app updater, not a Setup EXE deliberately opened by a user.

Manual first installation, repair and manual upgrades keep their normal interactive wizard. The change does not disable Windows security/publisher prompts or organizational restrictions. Standalone EXE replacement and complete ZIP/folder updates retain their existing mechanisms; all delivery forms keep matching versions and edition-specific feeds.

Staged-runtime health verification still precedes installation. Setup logging, process/exit-code checks, new-startup version/path and restored-workspace acknowledgement, independent recovery snapshots and previous-runtime retention remain required. Hiding progress must not turn a failed installation into a reported success. Installed late-startup fallback can restart the previous runtime while full registration/shortcut restoration still requires rerunning its previous official Setup.

## Important one-time transition

**An installed v2.4.1-or-earlier copy may show Setup progress once while installing v2.4.2.** The application already running owns the updater: its embedded launcher still passes `/SILENT`. The downloaded v2.4.2 payload cannot retroactively change that old launcher. Once v2.4.2 is installed and running, subsequent installed-app updates use `/VERYSILENT` and no longer show Setup's progress window under normal conditions.

Running the downloaded Setup manually remains an interactive installation, including when used to install this fix. Do not interpret a one-time old-updater progress window or a deliberately opened manual wizard as failure of the new updater.

## Verification state

Focused manual/navigation and bounded release-note checks passed **6/6** in 2.109 seconds on Linux Qt offscreen with isolated settings/output/cache folders. Current version/resource/manual transition assertions and `git diff --check` passed. Only the new v2.4.2 manual was generated; historical manuals remain untouched. These checks cover documentation and retained UI routes, not native Setup visibility.

The local regression run passed **384/387 tests**, with three Windows-only checks skipped, in 156.387 seconds. The final observer-focused run passed **6/7**, with its native Win32 positive control skipped here; it includes the additional public-evidence serialization regression. Setup argument checks verify hidden helper creation, `/VERYSILENT`, suppression/no-restart flags, retained logging and unchanged recovery. Actual native window visibility remains a Windows gate.

Native Windows visibility assertions, actual packaged acceptance, installer lifecycle, production update/recovery transactions and independent public-download checks are **pending** until final evidence is recorded. Source/documentation checks do not certify the absence of a native installer window. No v2.4.2 download or current-release promotion is claimed here before those gates complete.

The native update gate uses pinned official **v2.4.1** EXE, complete ZIP and Setup as the previous-version fixtures. It must distinguish the current production transaction invoked against a prior real GUI from clicking that old binary's embedded update interface; only the former exercises the new launch arguments before the first upgrade. The separate installer engine/lifecycle fixture remains the real pinned v2.3.1 ZIP unless explicitly revised.

Required checks preserve exact version/path/restored-workspace acknowledgement, Setup failure and late-startup/restore recovery, independent snapshots, matching complete package replacement and personal-data retention. Windows visibility checks must detect unintended Setup windows during the new in-app installed-update path while retaining a visible manual first-install wizard. All three package forms and matching update manifests must pass their existing shared native/public gates before publication.

The release remains unsigned unless a publisher identity is configured. Privileged CI runner/per-user registration checks are distinct from a clean standard-user PC, antivirus certification, physical DPI/multi-monitor testing and corporate-network policy. Existing human/platform limits remain explicit. Source measurements, settings, templates, workspaces and outputs stay outside runtime replacement/uninstall ownership; no analysis meanings, calibrations, phase codes or acceptance limits change.

## References

- [Version 2.4.2 manual](../manuals/v2.4.2.md)
- [Installed and standalone distribution policy](DUAL_DISTRIBUTION_POLICY.md)
- [Previous v2.4.1 release and verification](RELEASE_2.4.1.md)
- [Windows installation/update guide](WINDOWS_INSTALLER.md) (current published release until v2.4.2 is verified)
