# Codex prompt: extensible, evidence-based parameter comparison

Prepared: 29 October 2026. Target: `swarajsuman321-dev/Analizer` (Appliance Signal Studio).

This is an implementation prompt for Codex, not a claim that the features below have already been implemented. Copy the complete prompt into the development session.

## 1. Objective and scope

Act as a Principal Desktop Application Architect, Signal Analysis Engineer and Industrial Test Systems Engineer. Upgrade the existing Analyzer so it can discover, analyse and compare unfamiliar datasets using the appropriate metrics for each signal, event, stage and physical role.

**The uploaded washing-machine TDMS recordings are reference examples and regression inputs only. The product must extend to future channel names, channel counts, acquisition systems, formats, appliances and industrial processes.** Do not hardcode the reference filenames, model, firmware, sampling rate, cycle length, stage codes, number of valves or channel list into the engine.

The required behaviour is: import -> inventory and quality assessment -> resolve signal structure and meaning -> select applicable analysis capabilities -> extract measurements/events -> resolve stages -> compare compatible results -> produce an auditable report. Unfamiliar data must receive useful generic analysis immediately, while ambiguous meaning is presented for review. A report must explain what can and cannot be established from the available evidence.

Handle arbitrary channels within supported readers. Add an extensible reader interface for future formats. An unrecognised file must receive a clear unsupported-format result and import options, rather than a crash or a claim that arbitrary bytes have been understood. Sample-index data without a trustworthy timebase can have sample-domain analysis; it cannot have durations in seconds, RPM derivatives, energy or frequency in hertz.

Implement this in the existing Windows desktop application. Preserve single-run Analysis Mode, multi-run Comparison Mode, plotting, cursors, pan/zoom, exports, workspaces, corporate proxy/update support and existing distribution workflows. Complete working vertical slices, not disconnected scaffolding.

## 2. Inspect and extend the current application

Start by reading applicable repository instructions and checking the actual current branch and version. The inspected reference is `main` at commit `84fb831f6017888493d60acf54b8d71ed0b6da30`, where `app_version.py` identifies v2.4.3. This snapshot is context, not an instruction to downgrade or check out that version.

Relevant integration points already present include:

| Existing component | Required approach |
| --- | --- |
| `app_tdms.py`, `app_tdms_templates.py` | Reuse native per-channel clocks, source metadata, parameter review and mapping templates; extend readers without losing provenance. |
| `app_appliance_profiles.py`, `profiles/*.json`, `profiles/profile.schema.json` | Extend recognition and declarative profiles. Preserve existing profile and workspace compatibility through an explicit migration/adapter. |
| `app_engineering_trace.py` | Reuse immutable, gap-aware projections, unit conversion and interval-aware statistics. |
| `app_engineering_analytics.py` | Extend KPI, phase, readiness and anomaly analysis with reusable analysers and event definitions. |
| `app_signal_comparison.py`, `app_engineering_compare.py` | Extend existing signal/activity comparison and KPI deltas into typed, stage-aware comparison. |
| `app_data_comparison.py`, `app_signal_comparison_controls.py` | Integrate channel pairing, review and comparison workflows into the existing UI. |
| `app_comparison_report.py`, `app_engineering_report_summary.py`, `app_engineering_report_pdf.py` | Use one computed result model for the UI, numerical exports and narrative reports. |

Verify the current implementations before changing them. Existing code already handles useful statistics, activity events, comparison envelopes, quality and evidence exports; reuse and improve those capabilities. Do not create competing analysis paths that disagree for the same input.

The inspected profile validator uses a bounded set of domains, channel types and operations. Extend this cleanly with versioned schemas and capability registries, rather than accepting unvalidated arbitrary fields or inserting appliance-specific branches throughout the UI. Current washing-machine phase names have empty detection conditions in the inspected profile; a displayed phase name alone does not prove that a phase was detected.

## 3. Import and inventory every input

Build an inventory for every source field, including unfamiliar, unmapped, constant, empty, nonnumeric and metadata-only fields. Each must have an explicit disposition: analysed, supporting clock, quality/status source, metadata, needs review, unsupported, or invalid. Nothing should silently disappear because it is absent from a predefined appliance profile.

Preserve source file/dataset identity, group/path, original names, raw arrays, original sample order, native timestamps, source row/sample indices, units, datatype, group/channel metadata and quality/status channels. Distinguish original file hashes from hashes of loaded arrays; label each correctly. A channel count must distinguish measurement values from their clocks and quality companions.

Reuse TDMS support and existing CSV/Excel/text readers where available. Readers should emit a common run/channel model. Future adapters must be addable without editing metric implementations. For ambiguous tabular input, allow time-column, header, delimiter, locale and unit review. Keep text state labels and quality flags as categorical data instead of forcing everything to float. Handle vector, complex or other unsupported structures through declared capabilities or an explicit partial-support result.

Assess invalid values, NaNs/infinities, status validity, late starts/early finishes, sampling intervals and jitter, gaps, duplicate and backward timestamps, clock resets/wraps, inconsistent units, saturation and suspicious ranges. Constant data is an observation, not proof of a stuck sensor. Event logs and sampled waveforms need different acquisition policies; irregular event logging is not automatically a dropout.

Do not interpret a filename, file modification time or an arbitrary timestamp-like register as the acquisition clock. Relative and absolute clocks, tick counters, timezones and clock domains must be declared. Unwrap ticks only with a defined tick unit, modulus and rollover/reset policy. Warn about unsynchronised clocks or drift before cross-channel timing claims.

## 4. Separate structure, meaning, encoding and confidence

Classify these independently:

- **Structure:** continuous/quantised analog, binary state, multistate enum, bit field, pulse/event stream, cumulative counter, countdown/budget, setpoint, categorical text, metadata, or unknown.
- **Physical or logical role:** rotational speed, temperature, pressure, valve command, valve feedback, pump, heater, flow, stored volume, cumulative volume, cycle state, fault, and extensible custom roles.
- **Encoding:** stored datatype, signedness, bit width, sentinels, scale/offset, lookup table, calibration, unit and whether values are already transformed.
- **Evidence:** confirmed user/template mapping, documented source schema, compatible metadata, heuristic suggestion, or unresolved.

A two-level numeric signal is not automatically ON/OFF. A constant temperature is not automatically binary. A cumulative-looking series is not automatically a counter. A name containing speed does not establish command versus measured feedback, scaling, direction encoding or a physical RPM value. A two-state enum such as codes 34 and 42 must remain an enum unless its meaning is defined.

Use source schema and scoped confirmed mappings first, then compatible metadata and reviewed aliases/patterns, then conservative suggestions. Present conflicts and competing candidates. Store the reason and evidence for a match. A heuristic confidence label is not a calibrated probability; do not invent confidence percentages.

Support multiple instances of a role, such as any number of valves, pumps, temperature probes, motors or phases. Pairing must include instance, location/function, command versus feedback, dimension and encoding compatibility. Never join channels merely because their display names or ordinal positions match. Preserve unpaired fields from both runs in the report.

Allow the user to review type, role, units, decoder, enum dictionary and pairing, then save a versioned reusable template. Scope reuse to a compatible source schema, device/firmware family and encoding signature. Do not silently reuse a scale or state dictionary across incompatible sources. Display aliases may change without changing source identity.

## 5. Validate physical scaling before physical conclusions

The reference recordings demonstrate missing units, coded device states, different parameter sets, and potentially inconsistent stored-value/scaling metadata. They are examples of general data-contract problems. Named source functions and an active scaling flag do not, by themselves, establish whether stored values are raw or already transformed.

Implement a reviewed transform pipeline: raw -> documented decoding/sentinel handling -> verified calibration/scaling -> unit normalisation -> analysis projection. Retain every transform, version, parameter and source of authority. Prevent repeated application when importing, restoring a workspace, converting units or exporting. Distinguish absolute temperature conversions from temperature differences, rates and standard deviations.

Treat source function names as inert metadata. Execute only explicitly supported, reviewed operations from the application registry; never evaluate arbitrary expressions or scripts from a file. An opaque function name requires a documented implementation or user-confirmed mapping. A plausible-looking result after division is not validation. Do not infer a scale from the expected label RPM or appliance model.

When decoding is unresolved, retain raw-unit statistics, expose the conflict and mark physical measurements as `needs_scaling` or `needs_mapping`. Do not print a misleading peak RPM, litres or minutes. Command state does not establish actual mechanical actuation or water delivery.

## 6. Use capability-driven analysis, not a fixed metric list

Introduce composable registries for readers, transforms, analysers, event detectors, stage resolvers and comparators. Follow existing module conventions; avoid a monolithic class or a second application framework. A metric advertises its supported structures/roles/dimensions, required inputs, parameters, prerequisites, scopes, output units, evidence requirements, coverage policy and implementation version.

Each channel receives all applicable generic capabilities, then role-specific capabilities when its meaning is established. Profiles attach semantic definitions and thresholds; the core engine must not contain a sequence of hardcoded appliance/channel-name checks. Configuration expressions must use a bounded validated operator DSL, not Python `eval`.

| Signal family | Useful generic comparison capabilities |
| --- | --- |
| Analog/quantised measurement | Native-sample extrema and times, first/last values, time-weighted mean/RMS/standard deviation, explicitly defined percentiles, ranges, slopes, threshold dwell, supported-time distribution, paired error and shape measures. |
| Binary actuator or flag | Observed rising/falling edges, active episodes, initial/final state, ON/OFF durations, duty cycle, pulse/gap distributions, first/last activation, per-stage timing and cross-channel overlap. |
| Multistate enum/text | Occupancy and duration per state, state entry/exit events, transition matrix, ordered sequence, repeats, dwell distributions and unmatched states/transitions. Do not average enum codes. |
| Bit field | Decode only documented masks; analyse each decoded flag and observed combinations. Preserve undecoded bits and contradictory definitions. |
| Counter/pulse stream | Supported increments, event counts/rates, increments per stage, declared reset/rollover handling and calibrated quantity where supported. |
| Countdown/time budget | Initial/final estimate, pauses, upward/downward revisions, jumps, estimate progression and comparison with actual remaining cycle time when cycle boundaries are established. |
| Setpoint with feedback | Changes in command, response delay, signed error, absolute error/RMSE, overshoot, settling and tracking duration in a declared band. Requires compatible roles, units and timing. |
| Dynamic/vibration waveform | RMS/peaks, crest factor and optional spectrum/band metrics only when units, sample rate, bandwidth and acquisition quality support them. Slow telemetry does not establish vibration frequency or physical shocks. |
| Unknown numeric field | Raw-unit descriptive statistics, data quality and cautiously labelled numeric change patterns; no invented physical role. |
| Text, metadata or unsupported structure | Schema/value changes, categorical comparison or an explicit unsupported reason, with a route to map or add support. |

New semantic roles using existing operations must be addable through a profile/template. A genuinely new mathematical method may require a trusted plugin implementing a documented interface. Demonstrate both extension paths. Missing dimensions should block physical conversions, not block the complete report.

## 7. Timing, events and stage semantics

Preserve every channel's native time axis. Do not synchronise channels by row number or assume equal length/rate. Use projections on supported intervals for relationships; keep interpolation and timing assumptions visible.

Use half-open event/occupancy intervals `[start, end)`. Analog interpolation is allowed only under its declared acquisition policy and maximum supported gap. Held states remain held; do not linearly interpolate state codes, invent intermediate transitions or interpolate counters across resets. No extrapolation outside observed support.

An observed binary OFF->ON transition is distinct from a channel already ON at recording start. Track initial/final active episodes, left/right censoring and unknown boundaries separately. A data gap is not an OFF interval, and activity after a gap is not a proven new start. Sampled transition timing must retain its observation bracket/resolution; do not claim exact sub-sample physical edge timing.

Provide configurable hysteresis, minimum dwell, noise floor, debounce and refractory/merge rules. Keep original onset, confirmation time and retained duration distinct. Record suppressed short pulses rather than silently erasing them. A valid short actuation must not disappear due to an undisclosed default filter.

Define event count attribution across stage boundaries: count by observed onset, while reporting clipped occupancy duration in every intersected stage. An episode spanning two stages is one event, not two. Split at unknown support; do not join through gaps.

Keep these duration concepts separate: recording span, supported channel time, common comparison coverage, active time and proven process/cycle duration. Earliest-to-latest logging time is not automatically a complete appliance cycle. Include pre/post-cycle recording and censored cycles.

Resolve stages in this order: documented controller stage codes; confirmed user/recipe/event boundaries; declared multi-signal state-machine rules; explicitly labelled heuristic segments. If semantic evidence is absent, report neutral segments such as Segment 1, or unknown stage. Do not guess that code 3 means rinse or that every zero-speed interval is soak.

Represent exclusive process stages and overlapping activities separately. Heating, filling, pumping and rotation can overlap; their durations must not be added as though they partition the whole run. Support repeated stages, nested substeps, branches, optional steps, pauses, aborts and retries. Maintain stage instance IDs and boundary evidence.

Match repeated stages/events using configurable ordered sequence matching with type/context gates, timing/duration costs and insertion/deletion penalties. Preserve added, missing, split/merged, ambiguous and unmatched events. Do not force the third pulse or rinse in one run to match the third in another. Matching is order-preserving by default; permitted reordering must be explicit and reported.

## 8. Rotational-speed analysis in detail

Build reusable rotation/setpoint capabilities that apply to drums, compressors, pumps, fans and other rotating equipment where appropriate. Keep measured, requested/target and reference/control-internal speed separate; more than one command/reference channel may exist.

For each run and each applicable stage/substage, calculate:

- Peak signed value and peak absolute speed, their timestamps and evidence windows; minimum, mean, RMS and percentiles with their weighting convention.
- Valid recording/stage duration; supported rotation time; stationary dwell; time in configurable speed bands; percentage of supported time in each band.
- Start/stop observations and active bouts; ramp-up/down intervals and rates, plateau speed/duration/stability, time to reach a defined target band, overshoot and settling.
- Positive/negative rotation time, reversals and directional sequences only after direction encoding is established. Numeric sign changes must remain numeric sign changes when mechanical meaning is unknown.
- Command-to-feedback delay and tracking error when both are available and properly synchronised. Use simultaneous paired samples/intervals, not a difference between independently averaged channels.
- Interrupted acceleration, repeated ramp attempts, aborted high-speed attempts and recovery sequences according to documented event definitions. Do not call these confirmed unbalance corrections without supporting evidence.

For unbalance, compare explicit flags/counters or documented controller steps when present: episodes, attempts, per-attempt value, peak before/after correction, correction duration, recovery to the requested band, achieved plateau and unresolved/aborted attempts. A counter difference is a counter increase, not automatically the number of complete correction episodes. Use a parameterised definition of successful recovery.

When only speed and an unbalance-like measurement exist, allow **candidate** retry/correction segments with their rule and evidence. Do not infer a confirmed retry count from every speed dip. Report unavailable metrics when the necessary state/counter is absent.

For soak, compare a confirmed soak stage's count, duration, timing and permitted agitation. Without a confirmed definition, report stationary/pause dwell and optionally a candidate soak segment with supporting water/stage/actuator evidence. Stillness alone cannot establish soaking. For shock/impact events, require an appropriate measured signal and acquisition capability; low-rate RPM changes can establish abrupt reported-speed changes, not confirmed physical impact.

Show A, B, B-A, relative delta where meaningful, phase/event correspondence and comparability for all applicable metrics. Do not declare a faster or higher-RPM run better without an applicable acceptance rule and comparable test conditions.

## 9. Valve, pump and actuator analysis in detail

Support any number of actuator instances. Keep valve identity as Valve 1/2/etc. unless cold/hot/prewash/softener function is established. Separate command, electrical feedback and physical flow/position feedback.

For every actuator, whole run and every stage, report observed ON/OFF edge counts, active episode count with censoring, total ON time, duty cycle, first/last actuation, each pulse start/end/duration, pulse duration statistics, OFF gaps and unusually short/long episodes under explicit rules.

For multiple valves or actuators, compare:

- Which actuates first, ordering of subsequent events and inter-actuator delays.
- Pairwise simultaneous-ON intervals, episode count and supported overlap duration; distinguish overlap from a start-time tie.
- All-off intervals, alternation/switching patterns, and observed multi-actuator combinations. Enumerate observed combinations rather than generating every possible subset.
- Stage-specific pulse sequences, changed/missing/extra pulses and associated duration deltas.
- Time from command to feedback or flow/pressure response when those signals and synchronisation are available.

Treat ordering as simultaneous or indeterminate when source timing uncertainty prevents a reliable ordering. An actuator active before recording cannot establish which actuator originally started first. Report overlap and duty-cycle denominators over the relevant shared valid support, not over a different channel's recording span.

For pumps, additionally offer start-to-level-drop/flow response, drain interval, cycling and time to a declared empty/target threshold where sensors/calibration support them. For heaters, offer command-to-temperature response, switching, active duration, target attainment and measured energy when power exists. Do not convert valve ON time into litres or heater ON time into kWh without a declared, applicable measurement/model and uncertainty.

## 10. Other parameter-specific capabilities

The following are expandable capability families, not a closed channel whitelist:

| Parameter/role | Domain measurements and cross-run questions | Prerequisites and limits |
| --- | --- | --- |
| Water/process/motor/ambient temperature | Initial/final/peak and time, rise/fall, heating/cooling rate in declared windows, target attainment, hold duration/stability, overshoot and inter-sensor differences. | Verify location and units; temperature-labelled channels at different locations are not interchangeable. |
| Pressure or level | Baseline/peak, fill/drain slopes, threshold crossing/dwell, settling, oscillation, response during valve/pump activity. | Pressure-to-level/volume needs a verified calibration and applicable operating range; no inferred litres from pressure alone. |
| Measured flow | Instantaneous profile, fill events, integrated supported volume, phase volume and flow stability. | Integrate flow over real time with valid dimensions and coverage; distinguish missing periods from zero flow. |
| Water/energy quantity | Initial/final, valid increase, per-stage increments and reset/rollover events. | First establish cumulative counter versus instantaneous stored quantity. Final-minus-first is not valid across an unexplained reset. |
| Electrical power/current/voltage/PF | Peak/inrush when sampling supports it, time-weighted levels, supplied energy, active/idle intervals and stage contributions. | Preserve measured active power versus estimates; V x I alone is apparent power without the necessary AC context. |
| Unbalance/vibration/torque | Magnitude, peaks, threshold dwell, speed-conditioned response, supported correction/retry relationships. | Keep scalar unbalance, vibration acceleration, displacement and torque distinct; do not derive one from another without a model. |
| Program selector/recipe/configuration | Selected values, changes, conflicts and test-context differences. | Usually categorical context; compare codes as codes until dictionaries are supplied. |
| Progress state/controller step | Ordered state/step sequence, occupancy, repeats, missing/additional steps and stage mapping. | Decode using a versioned dictionary; numeric order does not imply process order. |
| Device-state arrays/packed registers | Per-field transitions, dwell and decoded bit changes. | Require field/bit semantics; preserve opaque code comparison otherwise. |
| Remaining time/budget | Revisions, countdown pauses/jumps and estimate error against an established end time. | Confirm encoding and units separately for each source; no end-time accuracy when completion is unknown. |
| Foam/low pressure/rinse hold/motor fault/error code | Flag episodes, onset, clearing, recurrence, dwell, code sequence and co-occurring measured changes. | Distinguish logged status, commanded state, stored last error and a newly occurring fault. No new error count from a static last-error register. |
| Acquisition status/diagnostic clock | Invalid-status intervals, timing quality, rollovers and impact on metric availability. | These support evidence quality; they are not automatically appliance faults or physical process measurements. |
| Future custom field | Structure-appropriate generic metrics, user-defined semantics, reusable profile operations and supported relationships. | Unknown meaning remains explicit; adding a field must not require a new UI or report implementation. |

Include a configurable relationship-rule layer for command/feedback mismatches, actuator response, temperature rise during heating, level change during fill/drain, simultaneous activity, delay and sequence constraints. Findings must quote the observed relationship and rule; correlation or timing alone must not be narrated as a proven root cause or hardware failure.

## 11. Point-by-point comparison without distorting the runs

Support original acquisition time, elapsed run time, confirmed start/event anchors, manual offset and matched stage-relative views. Distinguish common-origin alignment from independently rebasing each channel. A late-starting channel must retain its offset relative to its run.

Calculate original per-run metrics before any display normalisation. A normalised stage-progress plot may help compare shape, but must not replace real durations, ramp rates or latency. Optional lag estimation or dynamic time warping is a diagnostic overlay with declared constraints; it must not hide delays/retries or drive duration/acceptance metrics.

On common valid time support, calculate signed difference, absolute error, time-weighted MAE/RMSE/bias, maximum deviation and its time, area of absolute difference, coverage and tolerance breach intervals for compatible analog channels. State channels instead receive agreement/mismatch duration and transition timing comparison; do not present enum-code RMSE as a useful semantic difference.

Use native samples and exact supported interval/event boundaries for measurements. Plot decimation must not change peaks, event counts, durations or numerical results. Avoid dense Cartesian joins, uncontrolled global resampling and quadratic matching on long recordings. State the interval integration/interpolation model in the report and test it against hand-calculated cases.

For a scalar metric, use signed delta `B - A`. Use relative delta `100 * (B - A) / abs(A)` only when the metric's scale admits a meaningful percentage and the baseline is safely nonzero. Show percentage-point change for proportions/duty cycle separately from relative percent. An offset temperature value or opaque code must not receive a misleading percentage merely because the denominator is nonzero. A zero/near-zero denominator produces a reasoned N/A rather than infinity or an invented percentage.

Compare only matching metric definitions/versions, roles/instances, units, scopes, stage/event correspondence and sufficiently compatible test contexts. Flag differences in recipe/load, supply, environment, acquisition resolution or calibration. Retain useful descriptive differences without implying controlled equivalence. Single-run versus single-run differences do not justify statistical significance claims.

Reference/golden roles are explicit. For three or more runs, reuse the same results for a selected baseline, pairwise comparisons and an aggregate table with declared weights. Prevent one run with more samples from dominating by accident. No assumed better/worse direction without a declared engineering rule.

## 12. One auditable result contract

Use typed/versioned records shared by analysis, UI and exports. A metric record must contain, as applicable:

`metric_id`, definition/algorithm version, role and instance, run/channel IDs, stage/event scope, value/unit, statistic/weighting convention, required inputs, evaluated interval, supported duration, coverage denominator, sample/event counts, source sample references, boundary uncertainty, transform/mapping provenance, parameters, evidence basis, result status, warnings and acceptance status.

Keep separate:

- Result status, such as computed, partial, not observed, missing input, needs mapping/scaling, invalid, unsupported or not comparable.
- Evidence basis, such as direct measurement, documented derived quantity or heuristic inference.
- Engineering acceptance, such as Pass, Fail, Indeterminate or Not Evaluated, with the rule/limit version and source.

Zero events is a result only when the needed observation support and event definition justify it. Missing a signal or having a censored interval is not zero. Partial totals must say supported-time total/lower bound where that interpretation is valid; do not extrapolate missing time. Unknown uncertainty is unknown, not zero.

Comparison records must retain both source metric records, matching decisions, common support, conversion, delta semantics and the reason a comparison is unavailable. Distinguish full-run metric delta from common-window pointwise error.

Every event carries type, instance, onset/offset and observation brackets, censoring, source evidence, detector/version and stage assignment. Every inferred stage carries its rule and source channels. Explainable categorical confidence is adequate; report calibrated numerical uncertainty only when it can be calculated from a stated model.

Do not label a default 5% or 10% colour band as acceptance. Use a configured rule with a defined decision policy and sufficient data. Partial/inferred results may be descriptive while remaining Indeterminate or Not Evaluated for formal acceptance. Display rounding must not alter acceptance decisions.

## 13. Report and UI workflow

Make the workflow useful for someone who imports two unfamiliar runs:

1. Inspect detected fields, quality, proposed roles and unmatched data.
2. Review uncertain mappings, units, scaling and pairings; reuse compatible saved templates.
3. Choose the baseline, scope/alignment and optional stage definitions.
4. Run the applicable analysers; show progress and allow cancellation.
5. Review a readable comparison with links back to source plots/events.

Provide a concise summary followed by Run A / Run B / signed delta / meaningful relative change / evidence / comparability / acceptance columns. Allow expansion into per-stage and per-event measurements. Show what changed, when it changed, how much and what evidence supports it. Keep all unavailable requested metrics in a readiness appendix with a specific reason and a practical remedy such as mapping a state dictionary.

Include run context, original and aligned plots, event/actuator raster where useful, stage timeline, native extrema, matched/unmatched events, critical findings, quality limits and a complete parameter inventory. Distinguish unknown data from OFF/zero visually. A reader must be able to understand a conclusion without opening a second file.

Reuse PDF and workbook export paths and add/version machine-readable JSON evidence as needed. The same computed record must produce the same values and reasons in UI/PDF/Excel/JSON. Keep the main PDF readable and offer detailed tables separately when they are long. Generate narratives from the computed evidence and deterministic templates. No network/LLM dependency is required to calculate metrics; any optional language model must not invent metrics, silently supply semantic definitions or transmit source data without an explicit user choice.

Use compact top-accessible controls consistent with the current UI. Keep role/unit/decoder review inspectable, display legends clearly with transparency, reuse a single set of zoom controls, and size dialogs to content. Keep analysis off the GUI thread, with bounded memory, cancellation and actionable errors. Preserve source data and make changes to mappings/projections reviewable and reversible.

## 14. Required acceptance cases

Write meaningful numerical, integration and UI/export tests. Use hand-calculated synthetic fixtures to establish correctness. Use the private reference recordings for regression when available, and report honestly if they are not available in the execution environment. Do not commit private source recordings, internal paths, device identifiers or extracted traces as part of this prompt task; use synthetic fixtures for public tests.

| Test | Required outcome |
| --- | --- |
| Unknown channel names and a new sensor omitted from every built-in profile | Inventory and generic results still appear; semantic results wait for mapping. |
| New appliance/custom profile using existing operations | Added through configuration with no changes to UI/report/core algorithms. |
| New mathematical analyser | Registered through the documented trusted-plugin interface with compatibility validation. |
| Different channel counts/rates/start times/order and missing fields | No row-index pairing, no shifted late channel and no silent channel loss. |
| No usable clock, empty channel, one sample, all-NaN, text enum, constant analog | Useful sample-domain/categorical/metadata output or explicit insufficiency; no fabricated seconds or physical state. |
| Three valves with observed intervals V1 `[1,4)`, V2 `[2,5)`, V3 `[3,6)` | Each has 3 s ON occupancy; V1/V2 overlap 2 s; all-three overlap 1 s; union 5 s. A surrounding observed OFF state is needed to count each activation as a proven rising edge. |
| ON at recording start, ON after a gap and ON at recording end | Censoring/unknown boundaries are reported; no fabricated initial start or gap-spanning pulse. |
| Pulse crossing a stage boundary | One onset count; duration split between stages without double counting. |
| Unequal sampled edge timing and nearly simultaneous valve starts | Order is tied/indeterminate where uncertainty prevents a conclusion. |
| Extra pulse/rinse in B; repeated, missing or split stages | Ordered matching exposes unmatched/ambiguous events and avoids ordinal mispairing. |
| Speed in documented raw encoding versus already-normalised values | Equivalent physical results after exactly one verified transform; opaque scale functions and contradictory flags require review. |
| Negative speed, unsigned direction encoding, command versus feedback | Direction and tracking metrics follow declared semantics; no mechanical reversal from unexplained numeric signs. |
| Same peak but different plateau duration/ramp/retry patterns | Comparison reports these differences instead of only peak RPM. |
| Stationary dwell without stage evidence; speed dip without retry evidence | Neutral observed dwell/changes or labelled candidate segments; no confirmed soak/unbalance correction. |
| Low-rate data presented to shock/spectral analysis | Unsupported/insufficient bandwidth result, not invented impact/frequency metrics. |
| Counter reset, rollover, instantaneous level and countdown | Each follows its declared type/policy; no false negative consumption or invented counter increase. |
| Units such as Celsius/Fahrenheit and seconds/minutes | Correct absolute/difference/rate conversion; dubious source units stay flagged. |
| Zero baseline, proportional metric, offset-scale metric and categorical code | Correct signed delta, meaningful relative/percentage-point change or reasoned N/A. |
| Sparse and dense samples representing the same supported waveform | Time-weighted metrics agree within declared tolerance; oversampling does not change the verdict. |
| Display decimation and different export formats | Full-resolution extrema/events remain unchanged and all outputs agree. |
| Unmapped state codes, new firmware dictionary, bit fields | Opaque codes remain intact and incompatible templates are not reused silently. |
| Bad quality flags, large gaps, duplicates, backward clocks and truncation | Explicit quality policy, correct support and partial/censored results; no fabricated faults or timing. |
| Time-shifted copy, unit-converted copy, changed file/column order and restored workspace | Predictable invariance of physical metrics, explicit alignment deltas and stable identity/provenance; no double scaling. |
| Existing saved profiles, workspaces, analysis and comparison exports | Backward compatibility preserved through tested schema migration/adapters. |
| Large synthetic recording, cancellation and analyser failure | Responsive UI, bounded resource use, clean cancellation and useful partial/error results. |

For the valve fixture, add sufficient samples before/after the intervals and an explicit held-state acquisition policy. Test both exact event timestamps and sampled observation brackets; do not assert precision that the fixture does not supply.

## 15. Delivery and implementation order

First inspect the current code and document a concise gap analysis. Then implement in coherent slices:

1. Common inventory, quality, typed result/provenance contract and compatible profile evolution.
2. Capability resolution and generic analysers that work on unseen fields.
3. Reusable events, stage instances and sequence matching; detailed speed and arbitrary-actuator capabilities.
4. Additional domain/relationship operations and reliable scalar/pointwise comparison.
5. Existing UI/report integration, readable evidence exports, extension documentation and regression checks.

Within each slice, connect import -> computation -> UI -> export and validate it before expanding. Choose module boundaries consistent with the repository. Do not replace functioning code simply to introduce the registry. Do not stop at a design document when executing this implementation prompt.

Deliver working changes, focused tests, profile/decoder/analyser extension examples, migration notes, a metric/availability dictionary, and a concise explanation of what changed and how it was validated. Show one entirely new synthetic dataset and custom role working through configuration, plus a plugin example where a new algorithm is needed. Report unsupported cases and unverified physical assumptions explicitly. Do not promise perfect semantic understanding of an unknown sensor or encoded protocol.

Completion means an engineer can load two new compatible datasets, see every source field accounted for, obtain useful type-appropriate comparison, review any uncertain meaning once, save that mapping and reproduce the same evidence-based report later.
