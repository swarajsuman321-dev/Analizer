# Current frontend

The application has two workspaces: Analysis and Comparison. Channels, plots and
a compact cursor inspector are visible by default; advanced tools are optional
View docks. Imports and processing results load directly into the active workspace.

- Native per-channel and master visibility checkboxes track the current workspace.
- Unit groups use synchronized independent Y axes with matching trace/tick colors.
- Cursor A is #00D2FF; B is #FF9F1C, including handles, inspector and exports.
- Cursors clamp/snap to data; inverted intervals preserve positive spans and signed differences.
- Report export is one save dialog: PDF, 300-DPI PNG, active-interval Excel or CSV.
- Match indicators use numeric percentages, with shared visual threshold rules.
- The sample-preview pane, redundant Telemetry workspace and Tk application are removed.
- Legacy Tk telemetry, plugin, zoom, dashboard and image-digitizer modules are removed.
- Engineering parsing, synchronization and comparison mathematics remain shared.

The regression suite covers the current Qt frontend; obsolete Tk controller tests
were replaced with current service and Qt interaction/export tests. Native Windows
validation is performed by the Windows build workflow.
