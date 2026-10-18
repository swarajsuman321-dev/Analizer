# Header graph controls and non-obstructing hover — v2.2.2

> Superseded placement criterion: the latest user requirement puts zoom/pan beside Analysis/Comparison inside the graph header. The global-toolbar placement is an open defect. See [current requirements](USER_WORKFLOW_ACCEPTANCE.md) and the real-recording audit.

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

The fixed strip keeps readout text away from traces and handles during pointer and cursor movement.

## Compatibility

Saved workspace views add an optional `navigation_mode` value (`x`, `y`, `xy`, `pan`). Existing workspaces without it use Pan; old channel identities, axis bindings and cursor settings remain intact. Existing toolbar state restoration is followed by selecting the active workspace's header toolbar, keeping the controls accessible.

The TDMS template and fresh-runtime updater fixes from v2.2.1 are included unchanged.

## Validation

The five focused header/readout tests passed locally: native-style mode button clicks and inherited constraints, tab switching and cursor-lock access at minimum width, fixed strip/canvas separation throughout hover and resize, cross-pane hover ownership, and mode roundtrip/legacy fallback. The prior eleven desktop-finalization checks passed after updating placement assertions to the clarified header requirement; their numerical synchronization and restore assertions remain intact.

A rendered 1440×960 dark layout was visually inspected. Final local regression ran **214 tests: 213 passed and one Windows-only case was skipped**. Source GUI/export/workspace smoke also passed. **v2.2.2 is published and verified.** The [Windows workflow](https://github.com/swarajsuman321-dev/Analizer/actions/runs/39095566797) passed all **214 tests with zero skips**, the updater/channel/cursor-drag preflight, portable and single-file builds, both runtime smoke checks and the fresh-runtime restart check. The public latest-release manifest reports **2.2.2**, EXE size **154,309,326 bytes**, SHA-256 **`ff687da4867512afc0f2c93d35742512df72d9c97129b3201967a9e1ff66f831`**. [Release evidence](validation/release-v2.2.2.json) records the tested source commit and manifest. [Download v2.2.2](https://github.com/swarajsuman321-dev/Analizer/releases/tag/v2.2.2). Machine-specific DPI appearance still requires acceptance on the target PC.

Windows verification initially found a shortcut assertion still expecting the previous “Reset Scale” label after its rename to “Reset View”. That expectation is corrected. The build runner also now configures UTF-8 console/child output so a Unicode failure message cannot itself crash the logger under Windows cp1252. Subprocess regressions verify Unicode survives in console/log output and a failing child retains its real exit code. Failure summaries are bounded to GitHub’s annotation limit.

Cursor lines/handles now sit above passive hover crosshairs in the scene's hit order. The native drag regression verifies the cursor receives hover priority and supplies explicit held-button move events through Qt, avoiding Windows native pointer-state coalescing. It still requires the cursor to move and remain inside the recorded range; it is also run in the early native preflight.
