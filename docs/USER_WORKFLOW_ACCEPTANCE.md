# User workflow acceptance requirements — 18 October 2026

These requirements record the user's latest explicit clarification and supplied chart-menu reference. They supersede earlier documentation/tests that accepted a global application navigation toolbar. Current implementation does not meet them; see the [measured audit](audits/2026-10-18-real-user-workflows/README.md).

## Graph navigation placement

Place the primary navigation set in the graph panel's header, on the same header row beside the Analysis and Comparison tabs:

`[Analysis] [Comparison]  [Zoom X] [Zoom Y] [Zoom XY] [Hand] [+] [-] [Fit] [Lock time axes] [Lock cursors]`

Keep the tabs visible. At narrow widths use accessible overflow within this graph header. Do not put this set in the global application toolbar, float it over data, or duplicate conflicting controls. The active tab/pane determines action scope. Header, menus and shortcuts share the same selected mode and command state.

## Right-click chart menu

Right-click must act on the clicked pane and provide familiar chart tasks in this order: Hand/Pan (Esc), Cursor, Zoom XY, Zoom X, Zoom Y; Snap to cycles and Revert zoom; Comments/Add annotation and Move comments; Copy chart and application export. Revert restores the preceding view, distinct from Fit all. Explain or disable unavailable actions, such as cycle snapping before a cycle definition exists. Do not imply IEC/STGS certification or invent unsupported evaluation functionality from the reference screenshot.

Route analysis through the application's own processing services; unsupported native framework transform/downsampling controls must not bypass data/coordinate rules or raise callback errors. Keyboard and mouse choices must agree visibly.

## Reliable time locking and cursor identity

Given compatible temporal panes, enabling Lock time axes adopts the active pane's numeric interval immediately. Panning, box/wheel/button zooming, fitting, resizing, visibility changes, layout changes, themes, tab switches and restoring a workspace preserve identical numeric X limits. Turning it off permits independent intervals. Frequency, histogram and sample coordinates remain separate. Empty support stays unknown; locking a view never shifts source recording timestamps. Aligning physical test events is a separate, explicitly configured operation.

A locked cursor identifies one actual source sample. Its marker, readout and interval endpoint must agree, including duplicate timestamps, discrete states, masks and gaps. Keep original duplicate rows. Define the chosen sample identity consistently rather than fixing a display discrepancy by deleting observations.

## Dialogs, density and recovery

**Applies to every dialog, popup, configuration form and similar transient window, including future features.** Size the initial window around the required fields and action buttons. Optional descriptions, usage instructions and keyboard guidance belong in accessible tooltips or collapsed Help; they must not determine the initial window width or height. Wrap text inside expanded Help rather than stretching the window. Keep essential labels, required choices and actionable validation messages visible.

The user's Lock Cursors screenshot is the concrete example: keep Cursor A, Cursor B and Apply visible; move the sentence about panning, dragging and arrow-key stepping into Help or tooltips. Apply the same rule to Reference Units and every other form with explanatory prose. Elide long channel/source names in compact selectors and expose the complete value on hover and through accessible text. Help must also be reachable by keyboard; essential instructions cannot depend solely on hover.

Acceptance checks for each such window: open with default and longest realistic values; verify optional prose does not enlarge the collapsed form; open and close Help; verify long values remain discoverable; verify keyboard access and reachable actions at the minimum supported size and Windows scaling. A wrapped always-visible paragraph alone does not satisfy the request to remove unnecessary descriptions from the initial form.

Simple forms should keep Apply/Cancel reachable. Long channel names must not force excessive window width. Tables may need larger resizable dialogs; preserve readable columns with scrolling. Verify minimum supported screen size and Windows scaling independently. Split panes must remain usable or scroll rather than collapse to tiny traces. The audit's 150 logical-pixel drawing-height threshold is an explicit diagnostic heuristic, not a claimed external standard.

Before Apply, explain valid filter ranges in the signal's units and sample rate. Label missing physical units instead of implying energy/derivative units. Show source and selected/visible/all scope before processing or export. Long save/export work needs visible progress, safe cancellation where possible and an unchanged recoverable workspace after failure. Preserve original source cells and numerical clocks.

## Acceptance scope

Use the committed real fixtures and mixed layouts as well as synthetic edge cases. A green regression suite does not override these user requirements. Record observed results, expected safety rejections, source-inspected risks and untested platform behavior separately. Require a fresh native Windows build/runtime check before claiming executable acceptance.
