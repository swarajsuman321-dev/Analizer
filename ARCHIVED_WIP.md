# Archived development checkpoint — 1 November 2026

This branch preserves an **unfinished alternate implementation**, based on
`9211de1` from 29 October. It is not the published v2.5.0 source and must not be
used to replace that release, its manual, its tag or its update feeds.

The current release is v2.5.0 from
`da8766f2c60c235c1af1ee2a9e3ddcc3a8a41dfb`, recorded on `main` at `25d1124`.
Read the [current handover](https://github.com/swarajsuman321-dev/Analizer/blob/docs/handover-2026-11-01/docs/HANDOVER_2026-11-01.md)
and the current main-branch `AGENTS.md` / `docs/WORKFLOW_RECOVERY_PROGRESS.md`
before resuming development.

The `2.5.0` identifier in this archived working tree predates the independent
published implementation. It is not evidence of binary or update-feed parity.
Use a new development version after selectively integrating reviewed changes
onto current main; never republish the existing version number.

Preserved work includes the extensible inventory/mapping/capability/event/stage
architecture, an alternate plot-first UI, source-preserving import changes,
reports, examples, tests and synthetic screenshots. Existing functionality now
implemented on main must be reconciled, not overwritten. In particular, preserve
main's confirmed program-start alignment and native Windows lifecycle/menu fixes.

Validation of this branch is incomplete:

- Last full discovery: 749 tests, 742 passed, 2 failed, 5 skipped, 399.022 s.
  The two gate-inventory assertions were subsequently updated. A handover rerun
  of 25 harness/new-acceptance tests passed; complete discovery has not been
  repeated after those updates.
- Source acceptance: 54/55 passed, one runner error, zero application callbacks.
  Nested metadata now contains NumPy arrays; the runner's plain dictionary
  equality is ambiguous. Exact metadata equality still needs array-aware
  verification, not deletion of the assertion.
- The uploaded CSV was checked locally: 1,899 timestamps, 11 signals,
  531.076 seconds / 8.85127 minutes, original data unchanged and report bundle
  created. Private recordings and generated measurement reports are not included.
- No native Windows build, installer/update transaction or public release was
  produced for this archived implementation.

Known UI cleanup remains: an unused `GraphControls.button` can appear at the
window origin, the idle engineering cancellation button remains visible, and
advanced menu comboboxes need visible labels. The two screenshots in this branch
use synthetic signals and document this incomplete state.
