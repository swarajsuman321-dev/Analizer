# TDMS engineering imports and update restart — v2.2.1

## Reported problems

Engineering Controls bypassed Open's TDMS parameter review and template application. Its derived channel names were different from the full TDMS identities used by saved templates. A known file could therefore appear unreviewed or lose its reviewed labels and interpretation in alignment.

The updater launched a replacement at the same executable pathname while inheriting PyInstaller worker/runtime variables from the exiting app. The old single-file extraction directory disappears when that app closes. An inherited `_PYI_APPLICATION_HOME_DIR` can then point the replacement at a deleted `_MEI` directory, producing “Failed to load Python DLL”. This code path matches the supplied screenshot; other DLL-load causes on a particular PC remain possible.

## Changes

- Open, Align recordings and Compare original recordings use the same review function and template storage.
- Engineering imports review **all native TDMS parameters** before analysis, not only the subset a comparison happens to plot. Known exact identities reuse saved entries; unknown identities prompt. Cancel keeps the current workspace and analysis results.
- Original TDMS paths remain template keys. Engineering channel/source identities remain stable for alignment refresh, exports and comparison mapping. Both recording slots and same-name channels in two TDMS sources are supported.
- Saved units and interpretation are read before creating the engineering projection. Original technical names remain the engine's column names so a display rename cannot break mappings. Raw samples are preserved.
- Alignment traces receive reviewed names, units and interpretation. Comparison bench traces receive the reviewed name with a `· bench` suffix; reference traces keep their own labels. Comparison values retain the engine's reference units and comparison semantics rather than relabelling already-converted numbers as raw values.
- Both updater restart and rollback start with `PYINSTALLER_RESET_ENVIRONMENT=1` and without private `_PYI_*` / `_MEIPASS2` state. Proxy, user settings and unrelated environment variables are retained. The PowerShell script repeats the reset before launching either executable.
- The Windows build checks normal portable/single-file startup and an additional single-file restart with an environment sanitized from a stale runtime state.

The template schema stays at version 1. Existing reviewed files do not require conversion or a new review. Templates contain metadata, never measurement samples.

## Immediate recovery for an already affected update

1. Close the DLL error and any running copy of the application.
2. Start the saved `ApplianceSignalStudio.exe` directly from File Explorer. A normal fresh launch does not inherit the old app's temporary runtime state.
3. If it still fails, download the release's portable ZIP, extract **the entire folder**, and launch its executable while keeping `_internal` beside it. Retain existing workspaces/output files and templates.
4. If that complete portable folder also cannot start, retain the exact error and check the machine's security/quarantine history with IT. Do not download individual Python DLLs from third-party sites.

Updating from an older updater still uses that older updater's restart code once. If its automatic restart fails, the direct launch above is needed; v2.2.1's corrected updater is active after v2.2.1 starts.

## Validation

The supplied real TDMS recording was reviewed and reused with **27 channels** and **zero unknown parameters** after saving. Alignment succeeded in each recording slot with **124,585 projected rows**; comparison with the supplied simulation completed with **14 traces and 11 score rows**. This checks the import/template workflow, not physical calibration or equivalence of unknown parameters. [Sanitized source-run evidence](validation/tdms-engineering-v2.2.1.json) contains no measurements.

Local regression ran **206 tests: 205 passed and one native-Windows-only test was skipped**. The additional focused suite, including the subsequently added real background/UI-thread review case, passed **7/7**. Source GUI/export/workspace smoke and dependency consistency checks also passed. **v2.2.1 is published and verified.** The [Windows workflow](https://github.com/swarajsuman321-dev/Analizer/actions/runs/39053857156) passed all **207 native regression tests**, updater preflight, both executable builds and smoke checks, and the additional independent single-file restart smoke. Its [verified manifest and source commit](validation/release-v2.2.1.json) identify the immutable release. [Download v2.2.1](https://github.com/swarajsuman321-dev/Analizer/releases/tag/v2.2.1). Regression coverage includes cross-path template reuse, unknown-only review, atomic cancellation for both engineering actions, reversible raw actuator codes, both alignment slots, two-file name collisions, deduplication, benchmark/reference label isolation, and updater environment/rollback behavior.

## Installed application assessment

See [Installed Windows application: benefits and implementation scope](INSTALLATION_OPTIONS.md). This patch retains the existing EXE and ZIP distribution; the assessment does not claim an installer was implemented.
