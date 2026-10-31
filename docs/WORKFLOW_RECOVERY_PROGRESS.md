# Analysis workflow recovery

Target: next development release; current published version remains 2.4.3.
Working branch: `feature/recover-analysis-workflow`.

## Requirements compared with the current implementation

| Requirement | Existing behavior at 02f0ffa | Remaining work |
| --- | --- | --- |
| CSV timestamps including Excel text literals | Engineering parser supports elapsed units, dates and rollover; direct importer has a separate datetime path. Neither unwraps `="timestamp"`. | Share safe normalization and preserve source text; test both imports. |
| Shared A/B across compatible splits | Workspace propagates cursor changes, but each pane can normalize/clamp the pair to its own samples and viewport. | Keep one time pair; verify unequal lengths and combined readout. |
| Add and arrange blank graphs | Fixed layouts, draggable/resizable layout infrastructure and saved proportions exist. | Add explicit graph creation/removal/reordering with persistence. |
| Inspect all traces at one hover time | Hover finds values for traces in one pane, but marks only the nearest trace. | Shared inspection and per-trace markers across compatible panes. |
| Compare three or more signals | Comparison workspace overlays multiple channels; automatic signal comparison is a two-signal workflow. | Explicit multi-signal comparison and common results. |
| Valve overlap | Generic gap-aware binary/overlap backend and tests exist. | Integrate reviewed actuator selection and results into UI/report workflow. |
| Hide exported cursors by default | Plot, comparison and engineering report renderers draw cursor guides. | Common export setting; preserve times/statistics and on-screen state. |
| Simpler initial workspace | Some panels already fold, but advanced toolbars and fixed-layout choices remain prominent. | Plot-first default and clear Analysis/Comparison purpose. |
| Extensible evidence-based comparison | Existing readers, profiles, KPIs, reports and design prompt provide foundations. | Full inventory, reviewed meaning/scaling, typed/event/stage comparison and shared results; deliver in working slices. |

The recovered conversation describes unfinished v2.5.0 edits that are absent from
this checkout and remote branches. Those progress claims are requirements and
context, not verified current behavior.

## Checkpoints

- Baseline: 578 tests ran, 573 passed, 5 skipped; source workbench self-test passed.
- Timestamp fix completed: direct and engineering imports unwrap complete Excel text literals without evaluating formulas or changing source tables. Direct datetime imports now reuse the engineering clock parser, including midnight rollover.
- Validation: four new timestamp regressions passed; all seven existing minute-coordinate tests passed. Original user CSV is unavailable; fixtures reproduce the exact wrapper format and 8.85127-minute span from the handoff.
- Cursor-free report defaults completed across analysis PDF/PNG/SVG, comparison PDF and engineering PDF renderers. Report Details has an opt-in checkbox for cursor lines and lock markers; saved report metadata retains it. Cursor times, values, statistics and original screen state are preserved.
- Validation: three new export tests passed (including actual rendered artists, retained evidence and preference edits); existing report-details tests passed.
- Final checkpoint validation on the implementation in `f42c205`: full unittest discovery ran 585 tests in 261.364 seconds, 580 passed and 5 skipped, with no failures or errors. The source workbench self-test returned `ok: true`, exercising imports, FFT, workspace save/restore and report exports. The new version remains unreleased; native Windows validation has not been run for these changes.
- The GitHub checkpoint rule is saved in root `AGENTS.md`. All completed source and tests are committed on the development branch.

To include cursor guides in an export, open Report Details & Conclusions and
enable **Include cursor lines and markers in exported plots**, then save the
details. Save the workspace to retain this preference across sessions. Leaving it
unchecked keeps cursor times and statistics while exporting clean plots.

## Next checkpoint

Repair shared cursor normalization across unequal-duration splits and combine their
readouts, then add freely arranged blank graphs. Multi-signal comparison, shared
hover, overlap UI integration and broader comparison requirements remain open.

Confirmed cursor reproducer: create vertical splits with minute-based channels
covering 0–10 and 0–3, bind one to each pane, then set the long pane's A/B to 8/9.
After Qt events, both panes read 3/3. Pane-local normalization and range callbacks
must not overwrite the shared pair; the short channel should read Unknown at 8/9.
The active-pane-only readout and interval-card lookup also need a common
channel-to-pane mapping when combining measurements.

GitHub pushes work with the existing platform authentication. GitHub GraphQL API
access returned Forbidden, so automatic pull-request creation is unavailable in
this environment. The development branch is pushed; main and published packages
remain unchanged.

## Continuation policy

Commit and push completed development checkpoints on this branch with this record
updated. Preserve useful work before ending a session. Account usage percentage is
not exposed to the agent, so an exact 5% stop threshold cannot be monitored.
Do not describe a development push as a published installer release. Native
Windows packaging, installer and update/recovery gates remain required for release.
