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

## Implementation checkpoints and remaining release gates

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

### 2.5.0 development build preparation

- Source identity and Windows version resources are 2.5.0; generated offline
  manual and README clearly distinguish this development build from published
  2.4.3 downloads.
- Windows CI now also runs for this recovery branch, producing all three native
  package forms and diagnostics. Release publication remains restricted to main;
  a development-branch push does not publish a release.
- The first full integration run finished with 601 tests, six failures and one
  error (five skips). Four failures asserted the superseded panel defaults; one
  asserted old pan-induced cursor clamping; one used Qt polling that starved a
  background update worker. The error was stale IDs during recording removal.
  These were corrected while preserving behavioral assertions. The revised
  simplified-workbench suite passed 18 tests; updater suite passed 12 with one
  platform skip. Dock teardown callback lifetime was also corrected.
- Acceptance layout coverage is bounded to all original presets plus a custom
  3-graph layout across themes/sizes. An accidental exhaustive run over every
  generated count was stopped and is not a passing result. A separate regression
  constructs 32 graphs and verifies rejection of a 33rd without layout mutation.
- Fresh 2.5.0 full tests and supplied-recording acceptance are running. Source
  self-test has passed at 2.5.0. Native Windows output is not yet verified.
- Native Windows workflow was observed running for source `c3106fb` (Actions run
  41167515858). A follow-up corrects a final acceptance assertion for the new
  folded Engineering Controls default and checks dock tab membership after
  reopening the hidden dock (Qt omits hidden docks from tabifiedDockWidgets).
  The focused default-layout test passes, including reopening and separate Help.
- Documentation-only progress pushes no longer restart native builds. Source,
  tests, bundled manuals and workflow changes still trigger native validation.
- The supplied-recording domain guard now verifies all three cases: frequency
  stays independent, same-source time stays linked even when globally unlocked,
  and two separate synthetic runs can be independently viewed when unlocked.
- Correcting program start after an engineering plot already exists now uses its
  exact retained parent-clock mapping, avoiding a second shift. Missing or
  nonconstant source mappings block with a regeneration instruction. Six origin
  regressions and four multiple-signal tests pass, including this correction.
- Earlier in-flight runs were stopped after these corrections so the final
  checks use one frozen source revision. They are retained as diagnostic output,
  not reported as passing final validations.
- Final local full discovery at `e8fbd37` ran 604 tests in 363.044 seconds:
  599 passed, five platform skips, zero failures/errors. The expected broken-plugin
  rejection logs its intentional TypeError; it is not an application callback error.
- All 53 supplied-recording acceptance checks passed with zero runner errors,
  zero application callbacks, seven expected safety rejections and five manual
  platform checks unrun. The separate-run synthetic fixture now retains actual
  source time/value rows, so exact table/index roundtrip is exercised meaningfully.
- Visual review of three synthetic program-aligned runs found pale time-axis
  labels on graphs added after light-theme activation. New graphs now inherit
  the active text color; six shared-time/theme checks and nine header/hover checks
  passed afterward. Six origin checks and four multi-comparison checks also passed
  after distinguishing recording origin from program origin in JSON evidence.
- These final focused changes add one theme regression beyond the 604-test full
  run. Native CI will run the complete current suite; do not report an unexecuted
  605-test local run. The 2.5.0 source workbench self-test passed as well.
- Saved-workspace compatibility review found another timing edge: legacy splits
  could restore conflicting pairs, or a hidden graph could reappear with old
  positions. Linking compatible time graphs now copies the active pair/locks on
  restore/expansion as well as on movement. Seven shared-time/theme regressions
  and all 20 existing comparison-workflow tests passed. The manual documents the
  active-pair migration. Final full discovery for this revision is pending; an
  in-flight prior-revision repeat is diagnostic only.
- A later full-suite run exited with a Qt segmentation fault during selected-graph
  fullscreen restoration. This is a failed validation, not covered by the earlier
  passing run. The isolated 11-test fullscreen suite passed, so lifecycle/sequence
  behavior was investigated rather than dropping the test.
- Confirmed defect: closing a workspace left its plot and canvas-alignment timers
  active. Shutdown now stops timers and hover callbacks without destroying graph
  state needed by fullscreen restoration. Old panes also stop callbacks before
  deferred deletion on workspace restore or failed comparison rollback.
- The lifecycle regression asserts stopped timers and prevents rescheduling after
  close. Three consecutive rounds of flexible graphs and both fullscreen modes
  passed all 84 checks with fault diagnostics enabled; all 20 comparison-workflow
  tests passed, as did the 2.5.0 workbench self-test. A complete fault-enabled suite
  is running for this revision; native build validation remains pending.

The core timing/usability requirements above are implemented. Remaining release
gates are native Windows validation and review of the generated packages. The
broader extensible-comparison architecture remains a roadmap: full field inventory,
reviewed semantic/scaling mappings for unfamiliar channels, categorical metrics and
stage-sequence matching are not claimed complete by this regression-focused build.
The original newly supplied CSV/video from the prior account remain unavailable;
its exact CSV wrapper is covered with synthetic regressions.

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
