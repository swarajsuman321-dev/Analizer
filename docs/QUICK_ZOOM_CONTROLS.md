# Quick zoom beside Analysis / Comparison — v2.2.3

## Requested change

Use the blank right side of the Analysis / Comparison tab row for convenient graph navigation. The upper application toolbar and the fixed non-obstructing readout remain in place.

The inspected baseline was v2.2.2, commit `c8dda8b`, with working header navigation, cursor priority and native release verification. The attached advanced-analytics specification was reviewed as context. This patch implements the user's explicit quick-controls request; it does not implement the separate appliance-profile/KPI/reporting roadmap.

## Implementation

- Compact + (Zoom In), − (Zoom Out) and Reset View occupy a compact toolbar on the right of the graph-tab row.
- A directly accessible mode selector offers Zoom X, Zoom Y, Zoom XY and Pan. Its caption and checked selection reflect the existing workspace mode.
- Quick controls share the original QAction objects with header controls. There is one navigation implementation, preserving keyboard shortcuts, synchronized X axes, independent Y axes and workspace-specific state.
- Mouse coordinates and nearest-sample values retain their separate full-width strip below the tabs. The strip does not increase graph header height or overlay the canvas.
- In narrow center columns, zoom actions move into Qt's toolbar overflow menu. The mode selector remains directly available. Readout text elides and retains its full tooltip.
- Each workspace owns its quick controls; a stacked widget in the top-right tab corner switches to the active workspace, so ten-panel layouts do not duplicate controls or scroll them away.
- No new dependencies, source-data transformations or workspace schema changes are introduced.

## Verification

Focused checks cover action identity, actual quick Zoom In/Out/Reset clicks, X-only zoom without changing Y, synchronized viewports, mode changes from either location, tab switching, narrow widths, and strip/canvas separation. Existing hover/layout checks also pass. A 1440×900 light rendering was visually inspected with synthetic data; controls and coordinate text are separate from traces and cursor handles.

The final combined local regression ran **218 tests: 217 passed and one Windows-only updater transaction test was skipped**. The source GUI/export/workspace smoke passed with its additional shared-action check. A ten-panel layout was scrolled to the bottom and its quick toolbar stayed visible at the same screen position. Native Windows verification passed all 218 tests, both builds and their smoke checks, plus independent update restart. The release is published; see [evidence](validation/release-v2.2.3.json). No user recording or supplied private document is bundled or committed.

Native Windows verification found that full-text quick buttons could shorten the coordinate line too much. The zoom buttons now use compact +/− labels with explicit accessible names/tooltips; header and overflow actions retain their full names. Layout reserves coordinate space first, using a compact X/Y display only when needed. The full-precision tooltip is unchanged. The hover regression requires both X and Y labels and the temperature unit to remain visible in this case.

## Additional requested changes

About is immediately after Tools and contains only User Manual (F1) and Updates. Both existing windows remain available. Channel colors are assigned per channel rather than unit, persisted in metadata and reused in reports and appearance settings. Legends default to visible; explicit saved visibility and user colors are preserved. The user requires confirmation before any future feature removal or hiding.
