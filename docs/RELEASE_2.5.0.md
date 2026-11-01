# Appliance Signal Studio 2.5.0 — candidate changes

**Draft / not published.** This document describes the intended v2.5.0 candidate. It does not claim that a new Windows download exists, that the complete regression suite passes or that native packaged acceptance is complete. Replace this status only after recording actual source, test, packaging and public verification evidence.

## Plot, inspect and compare with fewer controls

- The primary toolbar focuses on Open Data Files, Analyse Selected Signals, Compare Selected Signals, workspace save/restore and Export Report. More Tools folds secondary controls; Panels and the full Tools menu retain supporting features.
- Data Portal comes forward after loading so its file-partitioned signal checkboxes are reachable. Engineering Controls remains available in its dock tab. Properties, Channel Math, Channel Table and Interval Measurements retain expandable/folded behavior and saved layouts.
- Add Graph creates a blank graph below the selected graph. Its menu adds one to the right, moves graphs and removes a viewport while keeping source data. Row/column dividers resize the arrangement. Custom layouts and channel assignments save with the workspace; reselecting channels retains prior pane assignments where applicable.

## One time-cursor pair across split graphs

Cyan A and orange B represent one shared pair across compatible time graphs. Shorter channels no longer pull the pair onto their endpoints or sampling grids. The combined value table shows every visible time signal once, including Unknown outside supported data. Native sample locks and duplicate-sample identity remain part of the cursor contract.

Mouse inspection marks each supported visible trace on its own value axis and supplies At Mouse readings, source indices/timestamps and missing-data reasons. The fixed readout stays outside the canvas. F11 shows the full split workspace and combined time values; Shift+F11 retains deliberate single-graph inspection. Frequency/sample plots keep their own coordinate domains.

## Timestamp import and source evidence

CSV timestamp parsing accepts complete spreadsheet text literals such as `="2026-01-02 10:20:30.123"` without evaluating formulas. Open, engineering import and native source inventory share the parser. Milliseconds and original source text remain intact, and graph time is displayed in minutes.

Reader options allow explicit delimiter, header, decimal, encoding, time-column and acquisition review. Complete inventory accounts for clocks, status companions, categorical/metadata fields, empty/all-invalid fields and unsupported structures. Scalar plotting support does not imply that an unknown binary protocol or vector field has been decoded.

## Analysis and comparisons of more than two signals

Analyse Selected Signals reports independent measurements, events and within-recording actuator overlap, using the current applicable cursor/whole-recording scope. Compare Selected Signals accepts two, three or more signals; an explicit reference is compared with each candidate in a separate Comparison arrangement. The chooser exposes reference, alignment, scope and gap settings. Existing pair-specific and overlay workflows remain accessible.

Arbitrary selected actuators can report pairwise, any-selected-ON, all-selected-ON and all-selected-OFF duration over their stated shared support. Half-open intervals, sampled brackets, unknown gaps and initial/final censoring remain explicit. Cross-recording elapsed alignment is not physical simultaneous operation. Command duration is not flow or energy.

## Optional reviewed meanings and reproducible reports

The advanced inventory/review path separates structure, meaning, units, encoding and authority. Reviewed transforms read original arrays. Compatible source-family/firmware/encoding templates can reuse confirmed definitions while new variables stay reviewable. Versioned capabilities and examples support unfamiliar roles and deliberately installed trusted numerical analysers.

A versioned computed result is shared by UI, readable four-section PDF, complete workbook and strict JSON. Native metrics do not depend on display reduction. Unpaired/unavailable fields retain reasons and practical next steps. Generic/quick acceptance remains Not Evaluated; the established engineering workflow retains configured limits.

Exported plots hide cursor lines, labels and lock markers by default while retaining times, interval values and statistics. Report Details & Conclusions provides an explicit annotation opt-in without changing on-screen cursors.

## Compatibility and verification to complete

Existing workspaces/NPZ companions, profiles, TDMS display templates, presets, trace colors and source data remain supported. Schema-1 profiles have an explicit adapter; an old display label is not silently promoted into physical calibration authority.

Installed Setup, standalone EXE and complete ZIP/folder continue sharing application features with edition-specific verified update/recovery workflows. The prior-update fixture is the verified v2.4.3 delivery. Older runtime libraries are CI upgrade inputs, not bundled legacy software.

Before publication, record the complete local regression/source workflow results, actual native tests, all three packaged workflows, updater/recovery outcomes and independent public artifact/feed hashes. Physical display scaling, accessibility, corporate networks and prolonged device/graphics behavior remain separate checks unless evidence establishes them. No test totals or completed Windows claims are asserted by this draft.

See the [plot-first user guide](PARAMETER_COMPARISON.md) and [implementation / acceptance map](EXTENSIBLE_COMPARISON_PLAN.md).
