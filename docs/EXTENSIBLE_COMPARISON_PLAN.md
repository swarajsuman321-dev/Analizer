# Extensible comparison implementation — 30 October 2026

Status: **implementation and acceptance work in progress for the v2.5.0 candidate**. The published baseline is v2.4.3 (`84fb831` documentation / `4fc6367` tested application). This document describes working-tree code, not a new download or completed Windows acceptance. Exact source/test/packaging/public verification belongs in final release evidence.

## Original gap analysis

This table records the starting gaps against v2.4.3. The implementation map below describes the code now present and its remaining acceptance boundaries.

| Area | Existing capability | Required work |
| --- | --- | --- |
| Import and source preservation | Original tabular datasets, native TDMS clocks/properties, immutable numeric plot projections and JSON/NPZ workspaces | Account for empty, all-invalid, categorical, metadata and unsupported fields; preserve raw unsupported structures and original ordering; register readers and explicit import options. |
| Recognition and transforms | Reviewed TDMS names/units, appliance profiles, bounded engineering operations, verified unit conversion/calibration | Separate structure, role, encoding and authority; scope reusable mappings to compatible schemas/encoding; prevent repeated transforms and expose unresolved scaling. |
| Measurement and comparison | Gap-aware engineering traces, interval statistics, elapsed-time two-signal integration, activity evidence, engineering KPIs | Resolve reusable capabilities for every field; typed state/counter/countdown analysis; reviewed semantic operations; structured availability, coverage, uncertainty and acceptance. |
| Events and stages | Existing phase rules, activity intervals and event evidence | Reusable censored episodes and observation brackets, arbitrary actuator overlaps, stage instances and ordered matching; no inferred appliance meaning from names/codes alone. |
| Workflow and report | Analysis/Comparison plots, direct two-signal report, detailed PDF/Excel/JSON, optional report notes | Whole-run inventory/review/pairing workflow; one computed result contract rendered identically in UI and exports, including unmatched fields and remedies. |
| Export presentation | Cursor values and overlays retained in current reports | Hide cursor plot overlays by default while retaining times/statistics/evidence; provide a persistent explicit opt-in without changing on-screen cursors. |
| Extensibility and migration | Trusted user-installed patch host and schema-1 appliance profiles | Versioned reader/transform/analyser/event/stage/comparator contracts, declarative custom-role example, trusted new-algorithm example and tested schema adapters. |

## Implementation slices

1. Add a source inventory and typed/versioned evidence contract. Keep the existing plotting channel model compatible; original non-plotted fields remain available for analysis and review.
2. Add reviewed schema-scoped mappings and transforms, and select generic/semantic capabilities conservatively. Delegate existing numerical methods to the current trace/unit/comparison services.
3. Add half-open event/occupancy timelines, censoring and brackets, stage instances, ordered matching and reusable actuator/rotation relationships.
4. Compare compatible results and common supported windows with explicit alignment, delta semantics and test-context qualifications. Keep unknown and unpaired data visible.
5. Connect the result to compact review/results controls and existing PDF/workbook/evidence delivery; document examples, migration and the availability dictionary.

Each slice must connect input, computation, UI and exports before release. Unknown roles/scaling receive raw or sample-domain results and a specific reason for unavailable physical metrics. No appliance phase dictionaries, calibration factors, timing filters or engineering acceptance limits will be invented.

## Shared interfaces

- `inventory_runs(store, dataset_ids=None)` returns every run with an explicit field inventory; `source_field(store, field)` retrieves original values, native coordinates, original indices and quality support without mutating plot projections.
- Reviewed mappings keep structure, role/instance/location, command/feedback kind, units/dimension, encoding/transform authority, acquisition policy and version separate. Display aliases do not replace source identity.
- `metric_record(...)` and versioned result bundles carry source identities, metric definition/version, scope, supported duration/denominator, counts, provenance, status, evidence basis and independent acceptance status.
- Event records retain half-open occupancy, observation brackets, censoring, detector parameters and stage assignment. Stage instance IDs distinguish repeated or nested steps.
- New orchestration delegates existing analog pair integration and trace/unit operations. Typed state/counter results do not become enum-code RMSE or inferred physical faults.
- `Include cursor lines in exported plots` is an export-only metadata flag, false by default. It never edits cursor positions, locks, live visibility or statistics.

## Validation and delivery

Use hand-calculated synthetic analog, state, actuator-overlap, event, stage, counter, countdown and scaling cases. Cover absent clocks/fields, native sampling differences, gaps/reset/duplicates, unknown codes, compatible/incompatible templates, ordered insertions/deletions, cancellation and output agreement. Reuse existing approved regression recordings read-only where available; do not add private recordings or extracted traces to Git.

Preserve old profiles, workspace manifests/NPZ companions, mappings, plot controls, proxy/update behavior and both installed/standalone forms. All forms must pass the same Windows gates and verified update feeds before the next release. Physical platform checks remain explicitly qualified in release evidence.

## Working implementation map

The user's subsequent real-use feedback changed the immediate priority: plotting first, a smaller primary toolbar, shared split cursors and values, freely arranged graphs, correct CSV timestamps, useful multi-signal comparison and clean report plots. The [plot-first user guide](PARAMETER_COMPARISON.md) leads with these tasks; advanced semantic review remains optional.

| Area | Working-tree implementation | Acceptance or limits to retain |
| --- | --- | --- |
| Import and source preservation | Reader registry; explicit text import options; complete field inventory; native per-field clocks/order/indices; safe typed workspace cells/NPZ evidence; timestamp literal parser shared by Open, engineering and inventory | Invalid/reset/backward clocks remain evidence. Unknown binary formats require an adapter. Complex/vector fields can be retained with an unsupported disposition without implying the scalar plot can render them. |
| Plotting and custom layout | Blank Add Graph below/right; move/remove; draggable dividers; persisted custom positions; remembered hidden-channel placement; existing presets retained | Removing a viewport keeps source channels. Custom layout restoration, graph removal and undo need regression acceptance alongside legacy presets. |
| Shared cursors and hover | One native-time A/B authority across time splits, combined value table, colored per-trace native hover markers and At Mouse values outside the canvas | Short/missing signals show Unknown rather than clamping the pair. Frequency/sample plots retain their own domains. Actual Qt dragging, rebind/reset, foreign locks, duplicates and fullscreen need acceptance. |
| Recognition and transforms | Separate structure, role/instance/function, command/feedback, encoding, units and authority; reviewed versioned operations; source-family/firmware/encoding-scoped templates | Source function names remain inert. Aliases are suggestions. Unresolved encoding blocks physical claims; stored engineering values skip raw decode/scale/calibration. |
| Generic/domain measurements | Source-resolution statistics, supported-time moments, state/counter/countdown and conservative rotation/flow/power capabilities; structured availability and evidence | Sample-only input cannot establish seconds, energy, physical frequency or ramp rates. Thresholds and domain prerequisites must exist. Unsupported results keep reasons instead of false zeros. |
| Events, stages and relationships | Half-open held/event timelines, brackets/censoring/suppressed-event evidence; arbitrary actuator overlaps; repeated/nested stage instances and bounded ordered matching; declared relationship rules | Commands do not prove actuation or flow. No rinse/soak/retry/fault meanings from labels or stillness. Matching retains missing, added, ambiguous and split/merge review results. |
| Quick analysis/comparison | Independent Analyse Selected Signals; reference-versus-each Compare Selected Signals for two, three or more; same-file/cross-file choices; native cursor/whole scope and timing options | Within-recording overlap differs from elapsed-aligned cross-recording history. Raw-number differences do not establish controlled physical equivalence. Retained pair/overlay tools remain accessible. |
| Advanced comparison | Whole-run inventory/review, explicit field pairing, native/elapsed/anchor/manual/stage-display alignment, typed scalar/common-window comparisons and equal-run descriptive aggregates | Units, roles/instances, scope and timing gate comparability. Stage progress display cannot replace real durations. Unpaired/unavailable fields remain in evidence. |
| Reports and appearance | One schema-2 result for UI, readable four-section PDF, complete workbook and strict JSON; original/aligned plots, available raster/timeline, readiness and inventory | Exported cursor overlays default off; times/statistics remain. An explicit report preference opts in. Export must not mutate live positions, locks or source arrays. |
| Extension and migration | Versioned reader/transform/analyser/event/stage/comparator interfaces; schema-1 profile adapter; custom-force profile and trusted MAD analyser example | New roles using existing operations need configuration; new mathematics needs deliberately installed trusted code. Historical workspace/profile/template files remain supported. |
| Distribution/lifecycle | Existing installed/standalone update, proxy/offline, recovery and packaging gates retained; real previous-update fixtures advanced to verified v2.4.3 assets | Shared code is not packaged acceptance. Publish only after native gates and independent public artifact/feed checks; physical DPI, accessibility and network acceptance remain qualified. |

## Evidence boundaries

- Availability, evidence basis and engineering acceptance are separate. Generic/quick results default to **Not Evaluated**. Established engineering reporting retains configured decision rules; the generic orchestration must not be described as automatically applying arbitrary profile acceptance fields.
- File hashes and loaded-array fingerprints are labelled independently. Plot reduction never becomes the measurement input.
- Recording span, supported time, common comparison support, active duration and proven process duration are distinct. Missing support is not OFF/zero or proof of an appliance fault.
- Manufacturer calibration curves, phase dictionaries, success criteria and limits remain user-configurable. Unknown uncertainty is not zero.
- Every unfamiliar source field is accounted for, but an unknown protocol cannot receive automatic semantic understanding. Unsupported structures retain a review/adapter route.

The [user guide](PARAMETER_COMPARISON.md) includes the metric/availability dictionary, family review path, registry contracts and migration notes. The [synthetic force profile](../examples/parameter_profiles/force_fixture.json) demonstrates a new role with existing operations; the [trusted MAD analyser](../examples/parameter_plugins/native_median_absolute_deviation.py) demonstrates new mathematics. Neither supplies manufacturer calibration or acceptance values.

## Completion gate

Focused tests are implementation evidence, not release acceptance. The final candidate must pass the complete regression suite and source workflow profile without unexpected application callback errors. Installed Setup, standalone EXE and complete ZIP/folder must then pass the same native packaged workflows and updater/recovery checks.

Newly supplied private recordings, device identifiers and extracted traces must not be committed. New public fixtures use hand-calculated synthetic data. Record actual commands, totals, limitations, tested source, artifact bytes/hashes and public feed checks only after they have run.
