# Desktop finalization — v2.2.0

Updated 17 October 2026. This document supersedes the layout/selection details in the historical [v2.1.9 audit](APP_STATUS_AND_REFERENCE.md). The existing raw-file audit remains useful; private recordings are not packaged or committed.

## Status

Implementation and local verification are complete. Windows release verification is pending in this source commit; publication evidence will be recorded here after the workflow succeeds.

## Final interaction decisions

- **Engineering Controls is the default selected tab in its existing dock group.** The user's clarification explicitly rejected a separate dock area. Data Portal remains one adjacent tab away. Explicitly restoring a saved workspace preserves its own layout.
- File headers each have a native **Select All / Deselect All** checkbox, independent partial state, **Close Dataset** button and file context menu. No global Select All checkbox exists. Filtering does not change which dataset owns a channel or allow a file control to affect another file.
- Zoom In, Zoom Out, Box Zoom, Pan Graph, Reset Scale and Lock Time Axes live in the active graph's top-right toolbar. It moves with the active graph and supplies an overflow menu in narrow viewports. A reserved canvas header prevents covering trace/cursor content.
- Zooming synchronized graphs scales X exactly once across the group, then each Y scale once. Reset fits the group’s combined extent. Disabling Lock Time Axes allows independent graph navigation. Frequency/sample domains stay separate from time.
- **User Manual / F1** is a searchable nonmodal window. **About / Updates** is a distinct modal window with version, build date, release notes, changelog, license and updater. The repository currently declares no app distribution license; About reports that fact rather than assigning a license. Scientific abbreviations remain in numerical readouts; action labels use explicit verbs and domain names.
- Cursor colors remain A `#00D2FF`, B `#FF9F1C`. The HUD shows nonnegative ΔX and absolute |ΔY| when cursors cross. Detailed/export B−A values remain signed. Match indicators remain percentage-driven accents; color names are not status messages.

## Compatibility

`app_config_migration.py` adapts old configuration data before UI mutation. Workspace schema 1 and its adjacent NPZ arrays remain supported unchanged. Version-2/3 presets and bare historical channel maps remain readable; known version-1 preset wrappers upgrade in memory. The migration preserves original files and unknown fields in the parsed record.

Supported textual containers:

- JSON workspace/preset wrappers; `channel_configs` and `settings` aliases.
- XML preset/channel elements with attributes and nested option values; an embedded `<json>` payload also preserves a complete workspace.
- INI `[channel:Name]` / `[signal:Name]` and `[options]` / `[settings]` sections; complete workspace JSON under `[workspace] payload`.

Scalar parsing uses JSON/booleans, never eval. XML DTD/entity declarations are rejected. Unknown future versions and structures are rejected before channels are modified; arbitrary third-party XML/INI cannot be reconstructed without its schema. Old formats cannot restore fields they never saved. Existing workspace fields for axes, styles, percentage rules, cursors, locks, annotations and dock layouts retain their values.

## Installation lifecycle

Settings, TDMS parameter templates, presets and extensions now use `%APPDATA%/ApplianceSignalStudio`; other platforms use the per-user configuration location. Explicit `ANALIZER_SETTINGS_DIR` / test output overrides are supported. Reports and portable workspaces keep their existing output destinations. About shows both actual locations with folder buttons.

Before constructing the normal application, portable settings/templates/presets/plugins and known registry-discovered installation settings are copied and SHA-256 verified. Outside the app’s templates/presets/settings/workspaces/plugin folders, only named app-configuration files are migrated; unrelated files beside a portable EXE are not swept into the profile. Arbitrarily named files elsewhere remain in place and can be opened through the legacy-format loaders. Conflicts are preserved in `legacy-imports/<source-id>/…`, not overwritten. Original configuration files are retained. Migration failure prevents cleanup.

After a **normal packaged Windows startup** and successful requested recovery restore, lifecycle finalization runs in the background. It discovers exact product uninstall/registration entries plus previously recorded installation paths. It never runs registry uninstall commands or elevates privileges.

Cleanup eligibility is deliberately narrow:

1. Current/running executable is excluded.
2. An older executable must match the app's Windows ProductName/version metadata or a stored ownership/hash inventory.
3. Libraries are eligible only through a previous app-generated file inventory, with unchanged hashes. Active portable dependencies are excluded.
4. Relative path traversal, symlinks and directory junctions cannot extend deletion beyond the owned location.
5. User documents, modified files and unrecognized files are retained; directories are removed only when empty.
6. The updater's previous EXE is retained until the new app initializes/restores successfully; it is then eligible for permanent removal. Failed startup/restore retains it.

`migration.json`, `installations.json` and `lifecycle.json` record migration evidence, file ownership and removed/retained paths. HKCU product registration is updated for future versions. Source runs and packaged self-tests do not delete installed files.

**Limits:** Older portable packages did not record ownership inventories or register every location. Unregistered folders elsewhere on disk cannot be reliably discovered. Uninventoried libraries cannot be safely attributed to the app and are retained; protected/modified files may also remain. No blanket directory deletion or claim of complete system-wide cleanup is made.

The Windows entry parser now accepts `--restore`; this fixes a previously uncovered mismatch between the updater's recovery launch command and EXE argument parsing.

## Verification

Local full regression: **196 tests passed, one Windows-only test skipped**. The expanded focused finalization suite passed all **10 cases**, including two additional restore guards after that full run (198 distinct tests in the final source). Source/bundle smoke now checks separate windows, graph controls, per-file selection availability and Windows product/version resources.

Ten focused finalization cases cover:

- Default Engineering tab, distinct modal/nonmodal windows.
- Native checkbox clicks: File A selection does not toggle File B, including with filters; closing File B keeps File A plotted.
- Top-right toolbar placement/focus, synchronized zoom factor applied once, independent axes and Reset Scale.
- Previous schema-1 workspace restored through JSON/XML/INI with identical bindings, ranges, color/rule attributes and locked cursor settings.
- Crossed cursor HUD absolute deltas, with signed detailed measurements preserved.
- XML/INI/legacy wrapper parsing, unknown metadata, safe rejection of XML entities.
- Verified settings copy with conflicting new settings retained and old originals intact.
- Inventory-only cleanup preserving changed/user/current/unrecognized files and rejecting traversal outside the install root.
- Invalid saved views rejected before replacing the open workspace.
- Early source-only workspaces rebind every viewport without leaving stale store references.

Existing regressions still cover data loading, sampling/nulls, unit/time conversion, processing, reports, alignment deduplication, updates/offline import and responsive save/restore. The supplied machine CSV and WT500 power CSV were imported together in the new UI: selecting only the machine dataset kept the power dataset unchecked; closing power preserved all 24 machine channels. An actual mouse click into another graph also transferred the corner toolbar correctly. The real-file audit tools remain available for rerunning the four supplied inputs; this release does not alter their ingestion projections.

Reproduction (use a venv with `requirements-build.txt`):

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p test_desktop_finalization.py -v
```

For Linux automation, set `QT_QPA_PLATFORM=offscreen` and writable cache/output directories. Native Windows CI validates platform behavior and both EXE modes. High-DPI appearance and a specific company's registry/proxy permissions still require that machine’s acceptance pass.

## Maintenance

- Domain/schema adapters: `app_config_migration.py`.
- Per-user paths, migration, registry discovery, verified cleanup: `app_lifecycle.py`.
- Per-file UI and removal: `app_channel_portal.py`, `app_workbench.py`.
- Active canvas controls and synchronization: `app_plot_workspace.py`.
- Separate windows and manuals: `app_info.py`, `manuals/v2.2.0.md`.
- Version/build metadata: `app_version.py`, `version_info.txt`.

Keep release versions, Windows metadata, bundled manual and CI artifact names synchronized. Publish only after the workflow succeeds; existing published EXEs remain immutable. Record the workflow, tested source commit, public update manifest size/hash and release URL below when verified.
