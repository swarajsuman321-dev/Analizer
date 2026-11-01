# Plot, analyse and compare recordings

This guide describes the **v2.5.0 development build**. It is not a publication or Windows acceptance claim. Use the version manual packaged with your installed application for released controls.

## Start with the graph

1. Choose **Open Data Files** and load a supported recording. Loading opens **Data Portal** so the signal checkboxes are accessible.
2. Check the signals you need. A checkbox controls plotting; clicking a row selects that signal for an operation. Ctrl/Shift selects several rows. Each file has its own Select All/Deselect All control.
3. Click a graph to select it. Use the single navigation bar beside **Analysis / Comparison** for Zoom X, Zoom Y, Zoom XY, Pan, zoom in/out and Reset View.
4. Choose **Add Graph** to add a blank graph below the selected graph. Its arrow menu also adds a graph to the right, moves a graph or removes a graph. Double-click chosen channels to put them in the selected graph. Drag the dividers to resize graphs.
5. Move cyan **A** or orange **B**. Time-based split graphs share the same pair; **Readout** contains the combined values. A line can be drawn in several canvases while representing one common time.

Removing a graph leaves the source channels loaded. Unchecking a signal hides its trace; **Close Dataset** unloads the file without deleting it. Use **Save workspace** to preserve your arrangement, settings and source snapshot.

**F11** expands the visible workspace, including its splits. **Shift+F11** expands just the selected graph. **Esc** returns. Frequency and sample-index graphs retain their own coordinate domains; a minute cursor is not converted into a frequency or a sample number.

The primary toolbar focuses on Open, Analyse Selected Signals, Compare Selected Signals, workspace save/restore and Export Report. **Panels**, **More Tools** and the permanent **Tools** menu expose supporting controls. Properties, Channel Math, Channel Table and Interval Measurements start folded; expanding them does not reset their data. Saved workspace layouts take precedence over new defaults.

## Analysis and Comparison have different jobs

| Task | Use | Result |
| --- | --- | --- |
| Inspect a recording or a set of plotted signals | Analysis workspace | Your plots, shared cursor readings and interval inspection |
| Measure one or several selected signals without choosing a reference | Analyse Selected Signals | Independent statistics, observed events and within-recording actuator overlaps |
| Overlay chosen signals from one or more files | Comparison workspace / More Tools → Compare Data | A separate plot arrangement; source measurements remain unchanged |
| Compare two, three or more selected signals numerically | Compare Selected Signals | One chosen reference compared with each other selected signal; PDF, Excel and JSON evidence |
| Review every original field, its meaning or its scaling | More Tools → Analyse & Compare Recordings… | Complete inventory, optional semantic review, explicit pairings and detailed evidence |

Opening the Comparison tab alone does not choose a reference, find matching channels or declare a test successful. **Compare Two Signals** remains available under More Tools as the retained pair-specific workflow; the primary Compare Selected Signals command has no fixed two-signal limit.

## Compare three or more signals

1. Open the recordings you want to inspect.
2. Select the signal rows in Data Portal. If no rows are selected, the quick action uses the visible signals in the active workspace.
3. Choose **Compare Selected Signals**. The first selected signal is the reference; each remaining signal is compared with it.
4. To choose a different reference, alignment, scope or supported gap, use **Tools → Engineering Diagnostics → Choose Comparison Signals & Timing…**. This also provides a file-partitioned chooser when the current selection is unclear.
5. Review **Summary** first. The other result tabs contain exact measurements, comparisons, source inventory, readiness, quality and events. Select a record to inspect its reasons and provenance.
6. Open the generated PDF, workbook or JSON using the result buttons. Reports use unique names in the remembered report folder.

Signals can come from the same file or different files. The quick workflow compares the loaded numeric/ON-OFF interpretations; it does not certify that similarly shaped signals have the same physical meaning. Incompatible units or state/numeric types receive a reason instead of a fabricated error value.

The default alignment is **elapsed time from each recording's start**. A channel that starts late retains that delay within its recording. **Original time coordinates** keeps original coordinates rather than independently rebasing channels. Alignment changes comparison projections; it does not change the original measurements or the per-run metrics.

The direct comparison uses whole-recording scope. The chooser can instead use the current shared A–B interval in native coordinates. **Analyse Selected Signals** follows the Readout's Cursor interval / Whole recording selection for time data; it keeps independent measurements and overlap rather than introducing a reference comparison.

## Shared cursors and mouse inspection

- Cursor A uses `#00D2FF`; Cursor B uses `#FF9F1C` in lines, handles and value labels.
- Moving A or B in any compatible time graph updates the shared positions and combined readout. A graph with fewer samples does not move the shared pair onto its own sampling grid.
- **Snap to Samples** anchors the manipulated cursor to a real observation. Each other channel is read using its own clock and supported interpretation.
- **Lock Cursors…** can anchor either cursor to a chosen channel sample. Left/Right steps A; Shift+Left/Right steps B. Other signals follow the same common time.
- Moving the mouse shows an observation marker for each available visible signal, including compatible split graphs. Pointer X and the nearest observation's X are different concepts and remain labelled.
- Missing readings, unsupported gaps and time outside a signal's recording remain **Unknown**. The inspector does not borrow a distant endpoint and present it as a measurement at the pointer.

The main graph time display uses minutes. Machine-readable evidence retains explicit units, including seconds for event boundaries and supported durations, so calculations remain reproducible.

## CSV timestamps and import options

The parser accepts ordinary timestamp strings and acquisition exports containing spreadsheet text literals such as `="2026-01-02 10:20:30.123"`. It removes only that complete literal wrapper in the parsing projection. It does not evaluate spreadsheet formulas, execute source expressions or rewrite the original cells. Milliseconds and available fractional precision are retained.

Open, engineering import and native source inventory use the same timestamp interpretation. Separate Date/Time columns can form one clock. Invalid or backward timestamps remain in original evidence; plotting projections may exclude invalid clock rows and sort usable rows. Absence of a usable clock does not prove a one-second sample rate.

Use **Channel → Import Text with Options…** for a different separator, header row, decimal separator, encoding, time column, coordinate unit or acquisition policy. An unknown extension offers explicit **Import as Text** options; arbitrary binary files are not silently understood as CSV. A file with no usable timebase can still receive sample-domain analysis.

## Valve and actuator overlap

1. Plot or select the actuator channels from the same recording.
2. Check their interpretation. An existing ON/OFF interpretation treats finite zero as OFF and finite nonzero integers as ON; missing/fractional readings remain unknown. Ordinary numeric sensors and opaque enums must not be forced into this interpretation.
3. Choose **Analyse Selected Signals**. The summary includes ON time, duty, pairwise simultaneous-ON time, any-selected-ON time, all-selected-ON time and all-selected-OFF time where support permits them.
4. Inspect the evidence for observation support, event brackets and censoring. Adjust the maximum supported gap through the comparison timing options when the acquisition contract requires it.

Overlap is a simultaneous relationship **within an original recording**. Elapsed-aligned valves from unrelated recordings are compared as separate histories; they are not treated as physically ON together. Pairwise overlap uses pair-specific shared known support. A missing interval is not an OFF interval.

State occupancy uses half-open intervals `[start, end)`. Already ON at recording start is left-censored, not an observed OFF→ON edge. Activity after a gap has an unknown start; activity at the end may be right-censored. A pulse spanning two stages has one observed onset, with occupancy clipped into each stage. Debounce, minimum duration and merge rules are explicit parameters; suppressed events remain evidence.

## Clean reports

Cursor lines, cursor labels and cursor lock markers are hidden in exported plots by default. Cursor times, values, selected interval and statistics remain in the report evidence. On-screen cursor visibility and locks are unchanged.

For an annotated plot, choose **More Tools → Report Details & Conclusions…** and enable **Include cursor lines in exported plots**. Save the workspace to retain this preference along with your notes. The ordinary cursor display selector controls the screen; the report checkbox controls exported appearance.

The parameter report has four main sections with readable continuation pages:

1. Overview, run context and pairing review.
2. Original/aligned plots and available event/stage timelines.
3. Measurements, signed comparisons and event/stage evidence.
4. Quality, complete field inventory, unavailable results and practical next steps.

The PDF presents the supplied computed results. Excel and strict JSON retain every record, including long lists, unavailable values, unmatched fields, exact units, support and provenance. Display decimation affects illustrations only. UI, PDF and numerical exports use the same result bundle; exporters do not recalculate metrics.

The four sections are not an exactly-four-page constraint. Long native event/sample tables belong in the complete companion evidence rather than unreadable miniature PDF tables. User-provided conclusions and recommendations remain clearly identified as user notes.

## Optional: review unfamiliar data once

Generic plotting and quick analysis do not require this review. Use it when physical meaning, an encoded value, a state dictionary or repeatable source mapping matters.

1. Open **More Tools → Analyse & Compare Recordings…**. Every original field appears, including clocks, quality companions, text, metadata, empty fields and unsupported structures.
2. Select a field and choose **Review Selected Field…**. Structure, role/instance/location, measurement/command/feedback, unit, raw-versus-engineering encoding and clock policy are separate choices.
3. Supply the documented evidence and confirm only what is established. Use the optional Transforms, State Dictionary, Analysis Parameters and Decoder tabs for supported advanced definitions.
4. Under **Template Compatibility**, enter documented source-schema, device-family and firmware-family information when it exists. A source-provided declaration can supply it. Encoding signatures are part of compatibility.
5. Save the review. Save your workspace to reproduce that exact analysis. For a later file that lacks family declarations, explicitly choose **Use Saved Source Family…** for its reference recording. Only compatible field/encoding reviews are applied; new or incompatible fields still require review.
6. Add and confirm field pairs under **Reviewed Field Pairing**. Choose the baseline, scope and alignment; then **Analyse & Prepare Report**.

A display-name match is only a suggestion. It is not permission to reuse a scale, decoder or enum dictionary from another firmware. Incomplete family metadata does not block useful raw analysis, but it blocks silent cross-file semantic-template reuse.

Transforms read original arrays each time. Reviewed raw values may pass through supported sentinel/dictionary/bit decoding, scale/calibration and unit conversion. Already-engineering values skip raw decode/scale/calibration operations. Unknown stored-value state or contradictory units produce `needs_scaling`; opaque source function names remain inert metadata.

Advanced alignment supports native, elapsed, explicitly confirmed anchors, manual offsets and selected stage-relative display. Scope boundaries use native seconds before display alignment. Stage-progress normalisation is an illustration; it cannot replace real duration, ramp-rate or latency measurements. Documented codes, confirmed boundaries, bounded rules and explicitly labelled neutral heuristics have distinct stage evidence.

## Metric and availability dictionary

| Family / example identifiers | Meaning | Required support / limitation |
| --- | --- | --- |
| `sample_count`, `valid_sample_count` | Source observations and valid observations in scope | Counts are not elapsed duration |
| `minimum`, `maximum`, `peak_absolute`, `first`, `last`, `range` | Native observations, extrema and original sample references | Available for numeric fields without inventing a physical role; not an average of enum codes |
| `sample_percentile_p5/p50/p95` | Explicitly labelled unweighted native-sample percentiles | Sampling-density dependent; method and requested percentiles retained |
| `time_mean`, `time_rms`, `time_std` | Supported-time moments | Trustworthy clock plus declared interpolation/support policy; standard deviation is a difference quantity |
| `supported_duration`, `coverage_fraction` | Known supported time and its stated denominator | Recording span, supported time and complete process duration are distinct |
| `minimum_slope`, `maximum_slope`, `dwell:<name>` | Supported segment slopes and declared threshold/band occupancy | Gap policy and explicit thresholds; source unit per second is labelled |
| `state.on_duration_s`, `state.off_duration_s`, `state.duty_cycle` | Known ON/OFF occupancy and ON fraction | Held/event policy, known state meaning and supported denominator |
| `state.rising_count`, `state.falling_count`, `state.episode_count`, `state.occupancy` | Observed edges, episodes and state occupancy | Initial/gap/end censoring and sampled timing brackets retained; enums stay categorical |
| `actuator.pair_overlap`, `actuator.union_duration_s`, `actuator.all_on_duration_s`, `actuator.all_off_duration_s` | Within-run simultaneous activity | Pairwise/all-selected common known support; unknown support remains unavailable |
| `counter.increment/reset_count/rollover_count` | Supported increments and documented reset/rollover observations | Declared counter structure and policy; an unexplained decrease prevents a complete consumption claim |
| `countdown.upward_revision_count/pause_duration/jump_count/final_estimate_error` | Estimate changes and explicitly defined pause/jump/error | Pause/jump parameters required; actual completion must be established for remaining-time accuracy |
| `speed.rotation_duration/stationary_duration`, bands and target/ramp/plateau results | Reported-speed activity under declared rules | Reviewed rotation units/role and explicit stationary/target/ramp parameters; direction requires documented encoding |
| `measured_flow.supported_volume` | Integrated measured flow over supported time | Verified flow dimension and measurement/feedback meaning; valve ON time is not litres |
| `active_power.supported_energy` | Integrated measured active power over supported time | Verified active-power meaning/units; heater command or V×I alone is insufficient |
| Common-window analog bias/MAE/RMSE/max/area/coverage | Candidate minus Reference over joint supported intervals | Compatible numeric quantities, original-resolution support and declared alignment |
| Common-window state agreement/mismatch | Time with matching/different supported states | Compatible state meanings; enum-code RMSE is not substituted |
| Stage/event sequence correspondence | Ordered matched, missing, extra, ambiguous and split/merge candidates | Type/context gates and declared matching costs; no forced ordinal pairing |

Scalar difference is **B − A**. Relative percent is `100 × (B − A) / abs(A)` only for an established ratio-scale metric with a safe nonzero baseline. Absolute temperature, opaque codes and unknown raw-unit meaning do not receive a misleading percentage. Duty/proportion change uses percentage points. Both original metric records, conversion and comparison reasons remain attached.

| Result status | What to do |
| --- | --- |
| `computed` | Read the stated scope/support and evidence; this alone is not Pass |
| `partial` | Review missing support or unresolved boundaries; do not extrapolate a complete-cycle total |
| `not_observed` | The applicable observation rule found none; check observation support and censoring |
| `needs_mapping` / `needs_review` | Confirm structure, meaning, dictionary, pairing or acquisition contract |
| `needs_scaling` | Resolve raw/engineering state, units or verified transform authority |
| `missing_input` | Supply the named required source, threshold, completion boundary or relationship |
| `not_comparable` | Check roles/instances, units, scopes, timing and test context; retain independent results |
| `insufficient_data` | Inspect empty/single-point/invalid fields, gaps and time coverage |
| `unsupported` | Preserve the field; use an appropriate reader, scalar projection or trusted capability |
| `invalid` / `error` | Read the actionable reason; correct configuration or the trusted capability |
| `cancelled` | Completed evidence may be retained, but the operation is not a complete report |

Availability, evidence basis and engineering acceptance are separate. New generic/quick results default to **Not Evaluated** for acceptance. Established engineering reporting retains its configurable acceptance rules. Neither match accents nor a default percentage band establishes a Pass/Fail rule. Manufacturer phase meanings, calibration curves, success criteria and physical fault diagnoses are not supplied automatically.

## Supported fields and explicit limits

Supported readers cover CSV/text, Excel, TDMS, tabular ZIP, JSON and Parquet according to their installed adapters. Every source field is inventoried. Scalar numeric values can plot; categorical text can receive categorical analysis; clocks and quality fields support evidence; metadata can remain metadata. Empty, all-invalid, vector, complex and other unsupported fields receive a disposition rather than disappearing.

The application does not promise to plot arbitrary binary structures or decode an unknown device protocol. Sample-index input cannot establish seconds, frequency, energy or physical ramp rates. No automatic clock-reset repair, undocumented bit masks, sensor calibration, controller stage dictionary, soak/retry/unbalance diagnosis or hardware-fault conclusion is inferred from a name alone. Spectral/impact conclusions require suitable acquisition/bandwidth evidence; the generic waveform path explicitly reports unavailable spectrum evidence rather than manufacturing it.

## Extend using configuration or trusted code

**New meaning with existing maths:** load [the synthetic force profile](../examples/parameter_profiles/force_fixture.json) using **Load Analysis Profile…** in the advanced dialog. Its schema-2 role `clamping_force` uses the existing extrema/moment operations. Alias matches remain suggestions until reviewed. Confirm the fixture's force unit, encoding and time policy, pair its source fields and run the same UI/report workflow. No force-specific UI or report implementation is needed. The [schema-2 profile schema](../profiles/parameter-profile-v2.schema.json) and Python validator define accepted keys/operations.

For a synthetic trial, create two CSVs with `elapsed_s,Synthetic force` headers, timestamps `0,1,2` and values `10,20,30` versus `10,25,35`. These invented demonstration values are defined as engineering Newtons by the fixture author; they are not calibration or acceptance limits. Review both fields accordingly and use the custom profile. Native maxima and means remain regular generic metrics, source-qualified by run.

**New maths:** [the trusted MAD example](../examples/parameter_plugins/native_median_absolute_deviation.py) registers a native-sample median absolute deviation analyser. Install reviewed Python code using **Tools → Presets / Extensions → Manage plugins…**, run selected-signal or advanced analysis, and inspect `example.native_mad` in the same result/evidence tables. This example needs no physical clock and labels its sample weighting. Disable/remove it through the same extension manager.

| Extension point | Contract |
| --- | --- |
| Readers | `ReaderSpec` and `register_reader` in `app_reader_registry.py`; emit named source tables and declared options/native inventory |
| Transforms | Versioned, bounded operations in `app_parameter_semantics.TRANSFORM_REGISTRY`; no file-supplied code or `eval` |
| Analysers | `CapabilityDefinition` + `CapabilityRegistry`; trusted plugins use `manager.register_analyser(definition, callable)` |
| Event detectors | `EventDetectorRegistry` / `event_registry()` in `app_parameter_events.py`; declared detector IDs, versions and native evidence |
| Stage resolvers | `StageResolverRegistry` / `stage_registry()` in `app_parameter_stages.py`; documented/manual/rule/neutral-heuristic inputs |
| Comparators | `comparator_registry()` in `app_parameter_comparison.py`; trusted plugins use `manager.register_comparator(definition, callable)` |

Analyser callables receive `(projection, context)` and emit through `context.emit(...)`. Definitions declare structure/role/dimension gates, inputs, scopes, parameters, units and support policy. Long methods call `context.check()` for cancellation. Arrays are original immutable observations; drawing budgets do not become measurement budgets. Duplicate/conflicting registration is rejected; registration rollback and per-capability error records preserve unrelated analysis.

Extensions are executable trusted Python, installed deliberately by the user. CSV cells, source function names, profile JSON, decoders and rule files are not arbitrary Python. Bounded configuration and registered operations keep mathematical execution reviewable.

## Existing workspaces and templates

Existing workspace JSON/NPZ snapshots retain stable identities, plots, masks, cursor settings, native source tables and supported metadata. The current reader understands older workspace encodings; new typed cells preserve native integer/complex/vector/category evidence without pickle. Move a JSON workspace and its referenced NPZ generation together.

Schema-1 appliance profiles remain valid and have an explicit schema-2 adapter. Original profile files and historical TDMS display-name/unit templates are retained. A legacy display label is not silently promoted into a confirmed physical meaning, firmware dictionary or scale. Schema-2 semantic mappings live in a separate versioned template, so incompatible saved evidence remains reviewable rather than overwritten.

Both installed and standalone editions use the same source features. Existing edition-specific verified update, proxy/offline, recovery and saved-folder behavior remain in place. Distribution publication and native-platform acceptance must be established separately in release evidence.
