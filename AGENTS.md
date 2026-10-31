# Development continuity

User requirement: keep application development code and progress on GitHub so work
can resume from another session or account.

- Work on a dedicated development branch. Commit source, relevant tests and
  documentation together in reviewable checkpoints; push completed checkpoints.
- Keep `docs/WORKFLOW_RECOVERY_PROGRESS.md` current with completed work, actual
  validation outcomes, limitations and the next concrete task. Never claim a
  release or passing test that has not completed.
- Preserve uncommitted user work. Do not force-push, merge to main or publish
  installers merely to create a backup checkpoint.
- If a reliable account-usage indicator is available and remaining quota reaches
  5%, stop starting new work, checkpoint current changes, record incomplete work
  and validation honestly, and push. Quota is not normally exposed to the agent;
  do not invent a percentage. Push frequently to preserve progress regardless.
- Do not commit credentials, virtual environments, generated measurement reports
  or private user recordings. Use synthetic regression fixtures when possible.
