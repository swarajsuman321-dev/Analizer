# Reconstructed modern frontend

This implementation was rebuilt from the 14 October 2026 handover against GitHub
main. The lost archive was unavailable. Its old 245-test and benchmark results do
not describe this source. The reconstruction has its own regression suite and
validation evidence.

| Capability | Implementation |
| --- | --- |
| Legacy compatibility and default Qt entry | main.py, app_legacy.py, windows_entry.py |
| Stable channel identity, hierarchy, revisions, immutable arrays and batched events | app_channel_store.py |
| Generic readers and original-source preservation | app_ingestion.py |
| Hierarchical portal, regex, bulk selection and drag/drop | app_channel_portal.py |
| Multi-axis linked layouts, per-view state, cursors and annotations | app_plot_workspace.py |
| Cached dense-data envelopes and prepared curve paths | app_fast_plot.py, app_plot_workspace.py |
| Span-weighted interval summaries, safe formulas and processing | app_signal_processing.py |
| Original engineering alignment/comparison adapters | app_analysis_service.py, app_workbench.py |
| Portable snapshots, processed data and dedicated reports | app_workspace_io.py |
| OS palettes, delayed tooltips and limits | app_qt_style.py, app_workbench.py |
| Worker generations, preview/apply guards, dock and source restoration | app_workbench.py |
| Source/bundle smoke validation | app_workbench_selftest.py, windows_entry.py |
| Recording checks and painted dense benchmark | tools/validate_recordings.py, tools/validate_workbench.py |

Array projections remain separate from original source frames. Last duplicate
samples drive exact cursor sampling. Unknown samples and masked support remain
unknown; processing needing uniform finite support explicitly rejects unsupported
clocks and asks for resampling. Zero-time jumps contribute no integration area;
unknown positive-duration spans reset cumulative integration. Temporal calculus
uses seconds, including displays in minutes; frequency and histogram coordinates
keep their own units. Descriptive statistics use finite sample weighting; interval
Mean/RMS use covered coordinate span.

Rendering uses precomputed min/max envelope levels, binary-search viewport
selection, a workspace point budget, cached numerical summaries and prepared
QPainterPaths with stable bounds. Missing support is conservatively retained during
downsampling. Workers perform import/processing without widget dependencies;
restoration invalidates obsolete completions using generation and store identity.

Calibration, plugins and the original comprehensive engineering interface remain
available through the retained legacy application. The modern Engineering Controls
provide recording alignment and original-source comparison, without reproducing
all legacy configuration screens inside Qt. The UI uses a standard Qt editable
command chooser rather than a custom searchable command overlay. Formulas support
restricted arithmetic and unit conversion rather than arbitrary scripting.

Derived results are materialized and do not automatically recompute after parent
edits. Shifts use numeric preview/apply, with no drag-to-shift gesture. Commercial
DIAdem formats, plugins and scripting interoperability are not certified. Native
Windows packaging and sustained 60 FPS remain unverified.
