# Appliance Signal Studio 2.5.0 — program timing and shared graph inspection

**Published and independently verified on 31 October 2026.** Installed Setup,
standalone EXE and portable ZIP share the same tested source and matching update
feeds. See the [public release](https://github.com/swarajsuman321-dev/Analizer/releases/tag/v2.5.0)
and [permanent native/public verification evidence](validation/release-v2.5.0.json).
The release tag resolves to tested source
`da8766f2c60c235c1af1ee2a9e3ddcc3a8a41dfb`. Later documentation-only progress
commits do not change that immutable release source.

## Timing and graph inspection

- **Align Program Starts** establishes one confirmed program origin per recording.
  Every time channel from that recording receives the same physical offset.
  Original arrays/timestamps remain unchanged, and pre-program samples retain
  negative program time. Missing program-start evidence blocks comparison instead
  of silently aligning recording starts.
- Compatible time graphs share one A/B pair and combined readout. A shorter trace
  shows Unknown outside its support instead of moving every cursor to its end.
  Channels from the same recording retain linked time navigation even when the
  general axis lock is off. Frequency and sample coordinates stay separate.
- **Add Graph** and the chart's **Arrange Graphs** menu create, move, resize and
  remove graphs, retaining bindings and proportions across saved workspaces.
  Up to 32 retained graphs are supported. Shared hover marks each compatible
  trace at the inspected time without moving A/B.
- Plot/fullscreen lifecycle cleanup stops obsolete timers and hover callbacks.
  The app uses its existing chart menu without constructing the unused native
  menu implicated in the earlier packaged Windows access violation.

## Comparison, import and reports

- **Compare Signals** supports an explicit reference with multiple candidates.
  Confirm program origins first; three or more selected rows open the chooser.
  Incompatible units remain blocked with a reason. Confirmed actuator pairs have
  gap-aware simultaneous-ON calculations. Across different runs, overlap describes
  timing similarity rather than physical simultaneous operation.
- PDF, Excel and JSON comparison companions share the computed results. Full
  source samples, difference intervals, events, support and limitations remain
  traceable; no universal engineering acceptance limit is invented.
- CSV imports accept complete Excel text-literal timestamps such as
  `="2026-10-30 12:34:56.123"`, retaining fractional precision and source text
  without evaluating formulas.
- Exported plots hide cursor guides by default while retaining cursor times and
  statistics. Enable **Include cursor lines and markers in exported plots** in
  Report Details when needed; saved workspaces retain the preference.
- New workspaces prioritize Data Portal, graphs and Readout. Engineering Controls
  and supporting panels remain available through Panels/View, and saved layouts
  keep their explicit state.

## Downloads and updates

All three forms use the same version and matching verified update feeds:

- [Per-user Setup installer](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.5.0/ApplianceSignalStudio-Setup-2.5.0.exe)
- [Standalone EXE](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.5.0/ApplianceSignalStudio.exe)
- [Complete portable ZIP](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.5.0/ApplianceSignalStudio_Portable.zip)
- [Version manual](../manuals/v2.5.0.md)

Use the matching installed, EXE or complete ZIP update route. Existing workspaces,
original source data and recovery snapshots remain supported. Installed updates
launched by v2.4.2 or later retain quiet Setup; manually opened Setup is interactive.
ZIP builds older than v2.4.0 need a one-time full ZIP download/extraction into a
separate folder; retain the old folder/outputs until verified.

## Verification and limits

The validated application source `2aa04ce27a8add0ed015cb0443af16586e27bac1`
passed local discovery: **609 tests, 604 passed, 5 platform skips**, zero failures
or errors. Local supplied-recording acceptance passed **53/53**, with zero runner
or application-callback errors; the source self-test passed.

[Development Windows run 41183692326](https://github.com/swarajsuman321-dev/Analizer/actions/runs/41183692326)
passed native tests, frozen smoke checks, installer lifecycle, recording acceptance
in standalone EXE/extracted ZIP/installed editions, and actual application
updates/workspace recovery. Exact native test counts were not visible through the
public run page and were not inferred for that earlier build.

The final [main-branch release workflow 41186819267](https://github.com/swarajsuman321-dev/Analizer/actions/runs/41186819267)
finished with **Success in 40m 25s**. Its actual captured native suite ran
**609 tests: 608 passed, 1 skip, zero expected failures**.
All **53 recording checks passed in each of the standalone EXE, extracted ZIP and
installed editions**, with zero runner/application-callback errors. Installer
lifecycle passed 7 checks; actual application updates/workspace recovery passed
13 checks. The attached `validation-v2.5.0.json` retains the original gate reports,
exact source commit, package hashes and manual-check limits.

Independent public verification downloaded and hashed all three binaries, checked
the latest and versioned feeds for every edition, matched the public tag to the
tested commit, and checked the ZIP inventory/CRC. The archive contains 2,594 files
and 389,000,955 uncompressed bytes. The published manual matches its bundled ZIP
copy byte-for-byte and source content after line-ending normalization. These
downloads were inspected in Linux; Windows execution evidence comes from native CI.

| Delivery form | Public file | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Installed Setup | [ApplianceSignalStudio-Setup-2.5.0.exe](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.5.0/ApplianceSignalStudio-Setup-2.5.0.exe) | 135,276,403 | `360530b5fa0998b252f16e4f99a90c32b068c4d5b08a68c154a6d91ec4cdeade` |
| Standalone EXE | [ApplianceSignalStudio.exe](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.5.0/ApplianceSignalStudio.exe) | 155,389,530 | `b93400f01e7b5796fb213e027f44bd94a531969174d12ea55778b17c3573a83c` |
| Standalone ZIP | [ApplianceSignalStudio_Portable.zip](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.5.0/ApplianceSignalStudio_Portable.zip) | 156,228,948 | `9c0e8021d3d8a5f10fac5ed8754993b60aa7229b9c1b88f5d43a931e1266390d` |

Published/bundled manual: **104,437 bytes**, SHA-256
`bf53baac53df079003271b9b3d97d463d6ff034df496c885e23c13053a596689`.
Only the current version manual was regenerated; historical manuals are unchanged.

The installer remains unsigned. The following manual Windows checks remain unrun:

- Physical wheel, box selection and keyboard navigation in every zoom mode.
- Windows 100%, 125%, 150% and 200% display scaling.
- Mixed-monitor scaling and graphics-driver behavior.
- Keyboard-only completion and screen-reader announcements.
- Long-running acquisition-sized workloads and antivirus policy interaction.

Full generic field inventory, reviewed scaling/semantic mappings for unfamiliar
channels, categorical metrics and stage-sequence matching remain roadmap work;
they are not claimed complete by this release.
