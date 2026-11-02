# Appliance Signal Studio 2.5.1 — CSV time headings and aligned panning

Publication authorized on 2 November 2026. This is the release candidate until
the main-branch Windows workflow succeeds and its public downloads are verified.
Release source: `4300b79a9fbca8754e3f1b328b1dff703ddb4e78`.
[Windows release run 41433633248](https://github.com/swarajsuman321-dev/Analizer/actions/runs/41433633248)
is validating that exact revision. Documentation-only progress updates do not
restart the job or change its release source.

## CSV time detection

Some UTF-8 CSV exports retain an invisible encoding marker before the first
`datetime` heading in the delimiter-sniffing reader. Version 2.5.0 misses that
heading and uses sample indices even when every timestamp is valid.

The heading matcher now ignores that marker and surrounding spaces, retaining the
original column keys, timestamp strings and measurement values. Existing clock
selection and parsing rules are otherwise retained. Millisecond precision and
supported Excel text-literal timestamps remain intact.

The supplied recording was reproduced as sample indices 0–1393 in 2.5.0. The fix
imports all 1,394 timestamps and 8 signals over 139.599 seconds on a minute axis.
The private recording is not committed or included in application/source packages;
the regression fixture uses synthetic timestamps and values.

**Reopen the CSV after updating.** A restored old workspace retains the coordinates
saved during its original sample-indexed import. Recording time is distinct from
program start; confirm the actual program-start event through Align Program Starts.

## Horizontal navigation

Same-recording sample graphs now share numerical X ranges, A/B positions, hover,
combined readout and fit bounds. Panning either aligned graph moves the complete
group horizontally, including when the general time-axis lock is off. Horizontal
pan preserves A/B positions, independent Y scales, original arrays and time offsets.
Three-graph checks also verify that the same cursor coordinates occupy the same
screen pixels despite different value axes.

Short traces show Unknown outside supported samples. Unrelated sample recordings
and frequency plots keep their own coordinates. Existing time-graph linking and
the confirmed program-start workflow remain supported.

## Verification and delivery

The correction at `cfaaf9c92e294f7b14e432e0d1a7647232996849` passed **617 local
tests: 612 passed, 5 platform skips, zero failures/errors** in 328.478 seconds.
All 102 focused checks, the source self-test and nine exact-file GUI checks passed.
See [local evidence](validation/csv-clock-aligned-panning-local.json).

The final 2.5.1 native workflow must validate all three distributions, installer
lifecycle and actual updates/workspace recovery, then publish matching manifests
and `validation-v2.5.1.json`. Its final outcome and exact counts will be recorded
after completion; previous-version checks do not establish a passing new build.

Publication is restricted to the original GitHub.com repository. Corporate imports
need reviewed server URLs, Windows runner configuration and release/update feeds
before enabling corporate publication. Current application updates still use the
established GitHub.com feeds.

The five manual Windows checks remain unrun: physical input in each navigation
mode, display scaling, mixed-monitor/driver behavior, keyboard/screen-reader
completion, and long-running/antivirus-policy workloads. The installer is unsigned.
