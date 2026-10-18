# Requirements review — v2.2.3

Reviewed 18 October 2026 (India time). This separates implemented behavior, test evidence and limitations. Historical requests are retained below; subsequent explicit layout corrections take precedence.

| User requirement | Current behavior and evidence |
| --- | --- |
| Quick zoom in the screenshot's unused area | Zoom In (+), Zoom Out (−), Reset View and X/Y/XY/Pan selector occupy the top-right **Analysis / Comparison tab row**. Shared actions preserve shortcuts and active-workspace state. Seven header/hover tests cover placement, modes, actual zoom, tab switching and narrow widths. Existing upper controls remain. |
| About beside Tools | Top menu order ends Tools, About. About contains only User Manual and Updates. Manual remains searchable/nonmodal with F1; Updates opens the existing modal version/build/changelog/license/update window. Manual/defaults and update tests verify access. |
| Distinct colors for channels sharing units, especially valves | Per-channel automatic colors persist in channel metadata. Traces and legend swatches match; same-unit channels receive distinct colors. Custom colors remain authoritative, including deliberate duplicates. Legends default on; explicit saved visibility is preserved. Two dedicated tests cover distinct colors, hide/rebind stability, custom colors, file removal and light-theme contrast. Reports use the same color mapping. |
| Engineering Controls default tab; no extra dock | Existing tabified Engineering Controls is selected on fresh launch. Explicit workspace layouts restore their saved state. |
| All View panels enabled initially | Default-panel checks pass; saved choices remain restorable. |
| Channel toggles and strict file isolation | Per-channel checkboxes; per-file Select All/Deselect All and Close Dataset/context menu. No global Select All. Multi-file tests verify closing one file preserves the other. |
| Direct loading; no preview/legacy package | Data loads into workspaces. Packaging excludes old frontends; retained feature modules remain available. |
| Minutes and unit detection | Elapsed time is numerically converted to minutes; sample/frequency domains stay distinct. Import tests cover metadata, names, explicit units and ambiguous clocks. |
| Multi-axis overlays and synchronized navigation | Independent unit axes, linked time viewports, X/Y/XY rectangle/wheel/button constraints, reset and shortcuts. Navigation, native drag and resizing regression tests cover these paths. |
| Cursor A/B, locks and useful values | Fixed cyan/orange lines/readouts, sample snapping, per-channel locks and sample stepping. Locked-channel value/anchor is visible; all selected channels update at that time. Interval statistics and absolute HUD deltas handle crossing. Signed detailed B−A differences remain available. |
| Non-obstructing mouse X/Y hover | Fixed separate strip below the graph tabs; hover guides do not move A/B. Nearest-channel sample/value and independent axis coordinates are available. Long text elides with complete tooltip. |
| Actuator ON/OFF handling | Contextual automatic detection plus explicit override; zero OFF and nonzero finite integer ON where interpretation applies. Unknown/fractional/missing samples remain unknown; sensors and codes are not universally treated as binary. |
| No repeated channels after alignment | Existing channel identities refresh; unchanged projections do not accumulate duplicate channels. Alignment, clock and multi-TDMS tests cover these cases. |
| TDMS review/templates in both import paths | Open and Engineering Controls share review/template handling. First import reviews parameters; later known identities reuse saved mappings and unknown variables prompt. |
| Reporting and output folders | Header Export Report offers PDF/PNG and interval CSV/Excel without a wizard. Exports retain cursor/trace/statistics/color information. Persistent outputs and per-user settings/templates have distinct documented directories. |
| Dataset removal | Close Dataset/Remove recording and Clear workspace update both workspaces, locks, dependencies and sources. |
| Old templates/workspaces | Known JSON/XML/INI containers and prior workspace/preset schemas migrate without modifying originals. Tests restore bindings, colors, cursor settings and ranges. Unknown third-party schemas cannot be inferred universally. |
| Updates, icon and Python DLL restart failure | Bundled identity/icon; manifest hash/size verification, corporate proxy/offline update paths, recovery and independent frozen-runtime restart. Native packaged checks are required before publishing. Network/DNS/security policy on a particular PC can still prevent downloads. |
| Clean lifecycle | Per-user migration and ownership-verified legacy cleanup after successful startup/restore. Unrecognized libraries, modified files and undiscoverable folders are retained rather than deleted indiscriminately. See desktop finalization reference. |
| Installed rather than portable app | Benefit/complexity assessment completed in INSTALLATION_OPTIONS.md. **No Windows installer is shipped**; EXE and complete portable ZIP remain supported distributions. |
| Complete manuals and future reference | Version-filtered offline manuals, searchable help, status/reference docs and release evidence are tracked on GitHub. Archived manuals remain unchanged. |
| Confirmation rule | Ask before removing/hiding a feature. Ask when intent or screenshot target is ambiguous before dependent implementation. Moving Manual/Updates into About and placing quick controls beside graph tabs were explicitly requested. |

## Verification and scope

Final local regression: **218 tests run, 217 passed, one Windows-only transaction test skipped**. The focused post-review legend checks and source GUI/workspace/export smoke also passed. Native Windows packaging, full regression, one-folder/one-file smoke, independent restart and publication must be verified separately; see `validation/release-v2.2.3.json` when available.

Earlier real-file tests cover the supplied TDMS and three CSV recordings; their channel counts, imports and scenario results are retained in `validation/four-file-audit-v2.1.9.json` and `validation/tdms-engineering-v2.2.1.json`. Private recordings are not bundled or committed. This UI change does not claim a new exhaustive run of every possible data combination. Automated tests cannot guarantee a bug-free application on every PC.

The attached advanced-engineering roadmap was reviewed as context. Its complete new appliance-profile/KPI/phase/tolerance analytics system has **not** been implemented by this UI patch; existing engineering/reporting capabilities remain available. Future implementation of that roadmap requires its own explicit scope review.
