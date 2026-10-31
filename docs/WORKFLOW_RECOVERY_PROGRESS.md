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
- Cursor-free report defaults are being integrated across analysis, comparison and engineering renderers.

## Continuation policy

Commit and push completed development checkpoints on this branch with this record
updated. Preserve useful work before ending a session. Account usage percentage is
not exposed to the agent, so an exact 5% stop threshold cannot be monitored.
Do not describe a development push as a published installer release. Native
Windows packaging, installer and update/recovery gates remain required for release.
