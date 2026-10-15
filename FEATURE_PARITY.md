# Feature parity — Studio 2.1.0

The audit compared every available repository revision: `2a9bf5d`, `eb931d1`,
`042bb9e`, `97fe305`, `38d3128`, and `54fba7a`. Earlier user capabilities are
integrated into one Qt application. Tk application copies are not bundled.

The default view stays small: channel checkboxes, Analysis / Comparison plots,
cyan/amber cursors, the interval inspector and Export Report. Tools opens the
advanced capabilities only when needed.

| Earlier capability | Current location / behavior |
| --- | --- |
| CSV, text, Excel and original-table inspection | Open; View → Channel Table |
| Parquet, JSON and ZIP-contained CSV | Open |
| Explicit coordinate column and units | Tools → Data → Import with coordinate settings; time projections automatically convert to minutes |
| Load simulation ZIP/CSV without a bench file | Tools → Data → Open simulation reference |
| Simulation PNG/image reference digitization | Same reference loader; Tools → Engineering → Image reference calibration |
| Image duration, plot bounds, reference height, per-signal tick calibration and verification | Image reference calibration; estimated values remain identified in diagnostics |
| Simulation time/pressure/remaining-time metadata | Tools → Engineering → Reference units |
| Run-specific ZIP definitions and package provenance | Reference details; complete workbook includes package files/metadata |
| Power-only, machine-only or synchronized inputs | Engineering recording controls; at least one input is sufficient |
| Heater, drum-start, raw-clock and manual alignment | Sync strategy; manual offset control is in seconds |
| Automatic channel discovery and editable labels/units | Open / Align; Channel mapping & appearance |
| Per-channel visibility and select/deselect all | Native channel-tree checkboxes |
| Per-channel panel, color, style, width, left/right axis and Y bounds | Tools → Plot → Channel mapping & appearance |
| Automatic readable overlays | Compatible minute-based channels share a plot; crowded unit groups are arranged into full-width stacked plots, with at most three unit axes per plot by default |
| Ten independent panels | Layout → 10 panels; scrollable canvas with synchronized compatible clocks |
| Title, font size, grid and legends | Tools → Plot → Display options |
| Peak power annotations and inlet/drain overlaps | Display options; generated overlays do not alter source signals |
| Hand, X-only, Y-only and XY zoom | Tools → Plot navigation; Escape returns to pan |
| Zoom back/forward and fit | Tools → Plot; R fits the active plot |
| Dual/point cursors, snapping, endpoint jumps and numeric positioning | Toolbar; Tools → Plot → Move cursors |
| Cursor A/B values, signed deltas, min/max/mean and other interval metrics | Readout; Interval Measurements |
| Live power and measured energy | Cursor inspector for an aligned recording |
| Copy cursor values | Tools → Plot → Copy cursor readout |
| Engineering duration, energy, power, temperature and speed KPIs | Tools → Engineering → KPIs & data quality |
| Data-quality warnings, timestamps and sync details | Same dialog; complete diagnostic workbook |
| Simulation/bench comparison and individual source visibility | Comparison; check the sim/bench channels independently |
| Explicit bench-channel overrides | Tools → Engineering → Comparison signal mapping |
| Signed differences, match percentages, heater state vs watts and unknown metrics | Comparison scorecard; original engineering rules remain |
| Full raw/aligned/curve data, heater states, source-unit and calibration exports | Tools → Export → Full diagnostic workbook |
| Full synchronized CSV | Tools → Export → Full synchronized CSV |
| Complete processed-channel CSV/Excel | Tools → Export → Complete processed channels |
| PDF summary, high-resolution PNG and active-interval Excel/CSV | Export Report (one save dialog) |
| SVG, HTML and Markdown presentations | Tools → Export |
| Reusable old JSON presets and new style presets | Tools → Data → Save/Load channel preset; may load before importing data |
| Portable full-session save/restore | Save workspace / Restore; original tables, diagnostic tables and studio settings persist |
| Playback, seek, speed and subsystem views | Tools → Plot; recorded phase/state intervals only |
| Normalized stacked tracks | Tools → Plot; only the drawing is normalized, readouts/exports retain source values |
| Explicitly illustrative example cycle | Tools → Examples; loads directly into the active workspace, labelled synthetic |
| Plugin install, enable/disable, remove, reload and directory access | Tools → Extensions → Manage plugins |
| Custom synchronization and KPI plugin hooks | Existing register_patch(manager) protocol; executed on alignment |
| Custom Matplotlib plot hooks | Tools → Extensions → Run plot extensions; Qt-hosted plot with image/vector export |
| Channel metadata, organization, formulas, unit definitions, filters, calculus, statistics, FFT/PSD, masks and annotations | Existing channel actions and Analyze tools |
| Processing preview followed by apply | Tools → Processing → Preview selected operation; no permanent sample-preview pane |
| Reset workspace | Tools → Data; saved files are retained |
| Light, dark and system themes | Toolbar |
| Native Windows portable and single-file builds | Versioned Windows CI artifact; version also appears in the title bar and EXE properties |

Compatibility boundaries: arbitrary Python extensions may need their own extra
libraries, and plot hooks use the current pane layout. Image digitization retains
the known simulator color/tick profile; it is not OCR for arbitrary charts. Old
acceptance-tolerance values remain compatibility metadata: current visual bands
are based on the documented match percentage, not invented acceptance limits.
The old sample-preview window and duplicated legacy application are intentionally
replaced by direct loading and the unified Qt controls.

Time display policy: all recognized time clocks and time-valued channels use minutes.
Old session view ranges, cursors, masks and time annotations are converted together.
Interval slope and integral presentation use per-minute / value·minute units. Source
tables remain unchanged, and frequency-domain calculations retain Hz.

## 2.1.1 follow-up

Unit detection now includes dedicated unit rows and recognized suffixes in normal
imports. The navigation toolbar and F1 reference expose zoom, pan and reset
shortcuts. Cursor A/B can independently lock to a channel sample and retain that
anchor during panning, shifts and session restore. Repeated recording alignment
updates existing source/column identities rather than adding duplicate traces.

## 2.1.2 workflow improvements

Every unit axis participates in vertical navigation without selecting a primary
channel. Locked readings are pinned beside the main readout. That table includes
A/B, differences and Min/Max/Average, with cursor-interval or whole-recording
statistics. Quick event notes attach to cursor A, survive session restore and
appear in reports. These adopt practical measurement-workbench ideas without
reproducing the reference interface.
