# Appliance Signal Studio 2.5.1 — CSV time headings and aligned panning

**Published and independently verified on 2 November 2026.**
Installed Setup, standalone EXE and portable ZIP share the tested source and
matching update feeds. See the [release downloads](https://github.com/swarajsuman321-dev/Analizer/releases/tag/v2.5.1)
and [permanent native/public evidence](validation/release-v2.5.1.json).
Release source: `4300b79a9fbca8754e3f1b328b1dff703ddb4e78`.
[Windows release run 41433633248](https://github.com/swarajsuman321-dev/Analizer/actions/runs/41433633248)
passed that exact revision in **41m 52s**. Documentation-only progress updates do not
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

The final native suite ran **617 tests: 616 passed, 1 skip, zero expected
failures** in 491.308 seconds. All **53 recording checks passed in each of the
standalone EXE, extracted ZIP and installed editions**, with zero runner or
application-callback errors. Installer lifecycle passed 7 checks and actual
application update/workspace recovery passed 13 checks.

Independent verification downloaded and hashed all three public binaries,
compared latest and versioned feeds for every edition, and matched the release
tag to the tested source. The public ZIP passed CRC/inventory checks: 2,595 files,
389,080,629 uncompressed bytes. The published manual matches the bundled copy
byte-for-byte and source content after line-ending normalization. Windows binaries
were not manually executed in this Linux cloud environment; execution evidence
comes from native Windows CI.

| Delivery form | Public file | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Installed Setup | [ApplianceSignalStudio-Setup-2.5.1.exe](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.5.1/ApplianceSignalStudio-Setup-2.5.1.exe) | 135,286,506 | `c14543a77c6e78b981e02b466631833d922c086c8cb5f82a36a2960bf1e99031` |
| Standalone EXE | [ApplianceSignalStudio.exe](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.5.1/ApplianceSignalStudio.exe) | 155,398,884 | `1bf61dacd1fdd270d39f29f362a03a0d315ba29e17341f01e99200d26615007d` |
| Portable ZIP | [ApplianceSignalStudio_Portable.zip](https://github.com/swarajsuman321-dev/Analizer/releases/download/v2.5.1/ApplianceSignalStudio_Portable.zip) | 156,240,442 | `da5bbab15a1a019271337ed7bff222c759947e4cdbf4bf3f03248dde846f9710` |

Published/bundled manual: **104,400 bytes**, SHA-256
`882bd5d86f7f0de837db8e5c0a677f0687253d7cd2cb7e9e2a26734bc933a5c7`. Historical manuals remain unchanged.

Publication is restricted to the original GitHub.com repository. Corporate imports
need reviewed server URLs, Windows runner configuration and release/update feeds
before enabling corporate publication. Current application updates still use the
established GitHub.com feeds.

The five manual Windows checks remain unrun: physical input in each navigation
mode, display scaling, mixed-monitor/driver behavior, keyboard/screen-reader
completion, and long-running/antivirus-policy workloads. The installer is unsigned.
