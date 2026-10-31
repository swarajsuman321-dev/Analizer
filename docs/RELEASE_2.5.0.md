# Appliance Signal Studio 2.5.0 — program timing and shared graph inspection

Publication authorized on 31 October 2026. The main-branch Windows release
workflow must finish before this version is described as published. The prior
development build passed all automated Windows gates; see the
[observed evidence](validation/v250-windows-build-41183692326.json).
Main was fast-forwarded to `da8766f2c60c235c1af1ee2a9e3ddcc3a8a41dfb`;
[release workflow 41186819267](https://github.com/swarajsuman321-dev/Analizer/actions/runs/41186819267)
is validating that exact revision. Documentation-only progress updates do not
restart it or change its release source.

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
public run page and are not inferred. Release preparation updates the bundled
manual, so the main-branch workflow revalidates the final release revision.

Publication must attach `validation-v2.5.0.json`, containing the actual native gate
reports, source commit, package hashes and manual-check limits. Public downloads,
feeds, release tag, ZIP contents and manual will be checked after publication.

The installer remains unsigned. The following manual Windows checks remain unrun:

- Physical wheel, box selection and keyboard navigation in every zoom mode.
- Windows 100%, 125%, 150% and 200% display scaling.
- Mixed-monitor scaling and graphics-driver behavior.
- Keyboard-only completion and screen-reader announcements.
- Long-running acquisition-sized workloads and antivirus policy interaction.

Full generic field inventory, reviewed scaling/semantic mappings for unfamiliar
channels, categorical metrics and stage-sequence matching remain roadmap work;
they are not claimed complete by this release.
