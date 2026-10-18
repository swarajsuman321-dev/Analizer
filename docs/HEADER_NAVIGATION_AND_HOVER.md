# Header graph controls and non-obstructing hover — v2.2.2

## Layout correction

The navigation tools are now in the **upper application toolbar**, immediately below Open/Save/Report and above the graph tabs, matching the user's clarified placement. No navigation toolbar is parented to a graph viewport and no plot margin is reserved for a floating toolbar.

The visible tools are **Zoom X**, **Zoom Y**, **Zoom XY**, **Pan**, **Zoom In**, **Zoom Out**, **Reset View**, **Lock Time Axes** and **Lock Cursors**. Zoom X/Y/XY and Pan form an exclusive mode group, so the selected behavior stays visibly pressed. Menus and existing shortcuts use the same state. New panes inherit the chosen mode, and Analysis/Comparison keep independent selections. Zooming and resetting retain synchronized-axis behavior; time and non-time plots stay separate.

**Lock Cursors** opens the existing channel/sample anchor dialog. Anchored channel readings remain available in the Readout table/cursor cards; other channels update at the anchor times.

## Mouse readout

Mouse text no longer exists as a floating label inside PlotPane. Passive crosshairs and the nearest-sample marker remain on the graph; a signal updates one fixed-height strip above the workspace canvas.

- First line: mouse X in the coordinate unit and Y in each independent axis scale.
- Second line: nearest channel, actual sample timestamp, value and unit.
- Long text is elided to fit; its complete content is available on the strip's tooltip.
- Text changes never resize the plot, steal focus or move/unlock A/B.
- Leaving the plot or clearing channels resets the transient readout. A different pane's range update cannot clear the pane currently being inspected.
- Hover remains enabled by default and stays out of plot/report snapshots.

This addresses the reported obstruction during pointer/cursor movement. The user's trailing sentence about movement was incomplete; no additional lag or jump defect has been inferred from that text alone.

## Compatibility

Saved workspace views add an optional `navigation_mode` value (`x`, `y`, `xy`, `pan`). Existing workspaces without it use Pan; old channel identities, axis bindings and cursor settings remain intact. Existing toolbar state restoration is followed by selecting the active workspace's header toolbar, keeping the controls accessible.

The TDMS template and fresh-runtime updater fixes from v2.2.1 are included unchanged.

## Validation

The five focused header/readout tests passed locally: native-style mode button clicks and inherited constraints, tab switching and cursor-lock access at minimum width, fixed strip/canvas separation throughout hover and resize, cross-pane hover ownership, and mode roundtrip/legacy fallback. The prior eleven desktop-finalization checks passed after updating placement assertions to the clarified header requirement; their numerical synchronization and restore assertions remain intact.

A rendered 1440×960 dark layout was visually inspected. Final local regression ran **214 tests: 213 passed and one Windows-only case was skipped**. Source GUI/export/workspace smoke also passed. Native Windows package verification is recorded after the build completes. Machine-specific DPI appearance still requires acceptance on the target PC.

Windows verification initially found a shortcut assertion still expecting the previous “Reset Scale” label after its rename to “Reset View”. That expectation is corrected. The build runner also now configures UTF-8 console/child output so a Unicode failure message cannot itself crash the logger under Windows cp1252. Subprocess regressions verify Unicode survives in console/log output and a failing child retains its real exit code. Failure summaries are bounded to GitHub’s annotation limit.
