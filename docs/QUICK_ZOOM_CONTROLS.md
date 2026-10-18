# Quick zoom in the mouse readout strip — v2.2.3

## Requested change

Use the blank right side of the existing Mouse X/Y strip for convenient graph navigation. The upper application toolbar and the fixed non-obstructing readout remain in place.

The inspected baseline was v2.2.2, commit `c8dda8b`, with working header navigation, cursor priority and native release verification. The attached advanced-analytics specification was reviewed as context. This patch implements the user's explicit quick-controls request; it does not implement the separate appliance-profile/KPI/reporting roadmap.

## Implementation

- Zoom In, Zoom Out and Reset View occupy a compact toolbar on the right of the existing 48-pixel strip.
- A directly accessible mode selector offers Zoom X, Zoom Y, Zoom XY and Pan. Its caption and checked selection reflect the existing workspace mode.
- Quick controls share the original QAction objects with header controls. There is one navigation implementation, preserving keyboard shortcuts, synchronized X axes, independent Y axes and workspace-specific state.
- Mouse coordinates and nearest-sample values remain on the left. The strip does not increase graph header height or overlay the canvas.
- In narrow center columns, zoom actions move into Qt's toolbar overflow menu. The mode selector remains directly available. Readout text elides and retains its full tooltip.
- There is one strip per Analysis/Comparison workspace, above its scrollable graphs, so ten-panel layouts do not duplicate controls or scroll them away.
- No new dependencies, source-data transformations or workspace schema changes are introduced.

## Verification

Focused checks cover action identity, actual quick Zoom In/Out/Reset clicks, X-only zoom without changing Y, synchronized viewports, mode changes from either location, tab switching, narrow widths, and strip/canvas separation. Existing hover/layout checks also pass. A 1440×900 dark rendering was visually inspected with synthetic data; controls and coordinate text are separate from traces and cursor handles.

Local regression ran **216 tests: 215 passed and one Windows-only updater transaction test was skipped**. The source GUI/export/workspace smoke passed with its additional shared-action check. A ten-panel layout was scrolled to the bottom and its quick toolbar stayed visible at the same screen position. Native Windows release verification will be recorded after completion. No user recording or supplied private document is bundled or committed.
