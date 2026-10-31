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

### Confirmed additional timing requirements

The user confirmed source-wide timing: channels from one recording must not move
independently in time, and comparison time zero must be program start rather than
recording start. When start cannot be established from reliable data, require a
reviewed program-start point for each run; preserve original timestamps and
negative pre-program time.

### Shared cursors and program-start checkpoint

- Shared cursor normalization uses the full compatible time-channel extent;
  shorter panes and pan/refresh callbacks cannot clamp the pair. Readout and its
  interval card combine all compatible time panes and retain each channel's owner.
- Same-recording time axes remain linked even with the general axis lock off.
- Align Program Starts provides a source-time point and required confirmation
  evidence for each recording, including a Cursor A shortcut. Every time channel
  receives the same physical offset; original arrays and source tables remain
  unchanged. Masks retain their original samples. Origins survive workspace saves.
- The direct comparison UI now requires those program origins and compares on
  program elapsed time. Missing origins block explicitly. The numerical engine
  retains explicit legacy elapsed/recorded/manual modes for compatibility.
- Focused validation: 4 shared-time regressions, 12 existing navigation/lock tests,
  4 program-origin regressions and 10 comparison-control tests passed. Full
  integration validation remains pending for this checkpoint.

### Flexible graphs, shared hover and multiple-signal comparison

- Add Graph creates a blank active graph without exposing hidden-layout channels.
  Arrange Graphs in the chart menu moves, resizes or removes graphs. Layouts retain
  bindings, proportions and order and support up to 32 retained graphs.
- Shared hover adds a marker on every compatible trace's own value axis, with
  sample coordinates/values in the readout tooltip, without changing A/B.
- Compare Signals supports an explicit reference and multiple candidates (select
  three or more rows, or use Compare more signals in the two-source chooser).
  Every candidate uses the established typed, gap-aware pair engine. Incompatible
  pairs remain visible as blocked with reasons. Same-run signal comparisons are
  supported through the multiple-signal chooser.
- Confirmed actuators receive pairwise simultaneous-ON calculations with separate
  gap limits for each acquisition clock. Cross-run overlap is explicitly timing
  similarity on program time, not physical simultaneous operation.
- Multiple-signal PDF/Excel/JSON bundles share the same computed result. Workbook
  and JSON retain source samples, full difference intervals and events; PDF
  includes program-time plots, summaries, overlap, notes and limitations.
- Engineering comparisons also default to confirmed program origins; advanced
  anchor overrides remain explicit. Ordinary new sessions show Data Portal and
  fold Engineering Controls; saved layouts retain their existing state.
- Focused checks passed: 2 flexible-graph regressions, 5 shared-cursor/hover tests,
  9 existing header/hover tests, 4 multi-comparison tests, 10 comparison-control
  tests, 5 program-origin tests and 33 engineering analytics tests. Full suite,
  source smoke and real-recording acceptance are the next integration gates.
- Integration fixes: removed-recording refresh now filters stale channel IDs
  before collecting shared cursor state; dock visibility callbacks ignore a
  destroyed window during teardown. Source smoke passes after the stale-ID fix.
- The real three-signal worker, result UI and complete report bundle passed an
  end-to-end control test. Its wait uses the existing acceptance runner's explicit
  Python-thread yield so Qt polling cannot starve the report worker.
- The first full integration run exposed assertions for the superseded Engineering
  Controls default. Those checks now verify the approved Data Portal default and
  still test that all advanced panels can reopen and saved layouts win.
- Supplied-recording comparison acceptance now checks missing-origin blocking and
  explicit fixture anchors. Fixture coordinates are labelled test-only and do not
  establish actual program starts of the supplied machine runs. Actual starts
  still require user evidence; the app does not guess them.

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
