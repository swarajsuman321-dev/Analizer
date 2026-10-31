# Versioned manual source

Each topic records the first version that supports it. For the current unpublished
draft, run `python scripts/build_manuals.py 2.5.0` after changing this source.
Keep published version manuals unchanged.

## Quick start | 2.1.0

1. Choose **Open**, select one or more recordings, and wait for loading to finish.
2. In **Data Portal**, check the channels you want to plot. Clicking a row selects it for operations; its checkbox independently controls visibility.
3. Click inside the plot you want to work on. Choose an appropriate layout and use the navigation controls to inspect the interval.
4. Position cyan **A** and amber **B**. Read their values and interval measurements in **Readout**.
5. Choose **Export Report** for a deliverable, or **Save workspace** to resume the complete analysis later.

The Analysis and Comparison workspaces keep separate plots and selections. Source tables and derived channels remain distinguishable. Loading, alignment and processing show their completion/error in the status bar. Wait for the current processing task before starting a conflicting edit.

## View menu and panel layout | 2.1.0

{{DEFAULT_VIEW}}

Use **View** to show or hide a panel. Drag a panel title to dock, move or float it; select its dock tab when it shares an area. Closing a panel hides that panel without deleting data. Restore it through View.

| View item | What it provides | Typical use |
| --- | --- | --- |
| Data Portal | Dataset/channel tree, search and visibility checkboxes | Select signals and control traces |
| Properties | Name, unit, group, kind, custom JSON and limit metadata | Correct or inspect channel metadata |
| Readout | Cursor positions and channel measurements | Read values while scrubbing |
| Interval Measurements | ΔX, ΔY, Mean, RMS, Min, Max, Peak-to-Peak, Slope, Integral and Coverage | Quantify an interval |
| Channel Table | Source/diagnostic dataset selector and table | Inspect original rows or calculated tables |
| Channel Math | Formula editor, processing operation and its parameters | Create derived channels |
| Engineering Controls | Recording paths, synchronization, comparison and scorecard | Align and compare tests |
| Show channel kind | Analog/discrete column in the Data Portal | Identify interpolation/step behavior |

Saved workspaces restore their own panel layout. A saved layout can therefore differ from the defaults for a new workspace.

## Open recordings | 2.1.0

Use **Open** or **Ctrl+O**. Supported table inputs are CSV/text, Excel `.xlsx`/`.xls`, ZIP files containing CSV, Parquet and JSON tables. Multiple selected files load into the active workspace. A ZIP must contain CSV data; a simulation package has its own reference loader described below. A workspace JSON is restored with **Restore**, not opened as a table recording.

Check the detected coordinate and units before interpreting measurements. A file without recognizable time data uses sample indices; do not assume these are seconds. Invalid clock rows are excluded from plotting projections; original source tables remain available through Channel Table. Missing numeric values appear as gaps/Unknown rather than fabricated readings.

## Import with coordinate settings | 2.1.0

Use **Tools → Data → Import with coordinate settings…** when automatic coordinate detection is unsuitable. Select the file, then choose **Automatic**, a particular coordinate column, or **Sample index**. Select **Auto**, seconds, minutes, hours or samples for the coordinate unit. The file then loads into the workspace.

Example: a logger's `Elapsed` column contains seconds. Choose `Elapsed` and `s`; a coordinate of 120 becomes 2 minutes. Choose Sample index for an untimed sequence instead of inventing its sampling frequency. The selector lists columns from the first table in a multi-table input.

## Time and value units | 2.1.0

Recognized time coordinates are presented in **minutes**, including seconds/milliseconds/hour imports. Time-valued measurements such as remaining time also use minutes when their source unit is declared. Frequency-domain channels retain Hz; sample-indexed channels retain sample units. Original source tables are not rewritten by these display conversions.

Editing a unit label in Properties is a metadata edit, not an arbitrary numerical conversion. Use a supported **convert** formula when numerical unit conversion is required. Confirm ambiguous units with the recording's documentation before comparing measurements.

## Unit detection improvements | 2.1.1

Normal table imports also recognize unit rows, declared units, common unit suffixes and supported signal names. Explicit units take precedence over name-based guesses. Unknown units remain editable rather than inferred from magnitude alone.

For example, a pressure reading declared Pa remains Pa. A large number by itself does not establish whether a pressure-related signal is Pa, mbar or a pulse period. Confirm the source unit before conversion or comparison.

## Data Portal selection and visibility | 2.1.0

Each channel has a checkbox. Check it to show its trace and uncheck it to hide it immediately. The master checkbox selects/deselects all channels, including ones hidden by the filter. Use individual checkboxes or channel mapping when working with a subset. Deselecting all channels leaves a clean empty plot. A selected tree row identifies the channel for Properties, math and channel actions; selection and visibility serve different purposes.

Type in the filter to find names, units, sources or metadata. Enable **Regex** to use a regular expression; fix an invalid expression if the field indicates an error. Clear the search to see all channels. Double-click selected channels to plot them in the active workspace. Dataset and group nodes organize the channels; they are not extra measurement traces.

## Layouts and independent axes | 2.1.0

The main layout selector offers **Single**, **Horizontal split**, **Vertical split**, **2×2**, **Stacked**, **3 stacked**, **10 panels**. Click a plot to make it active before changing that plot's settings. Compatible time plots share synchronized X navigation. A frequency result is placed in a compatible viewport rather than overlaid on a minute axis.

Channels with different units use independent Y-axes. Trace colours match their corresponding axis colours. Crowded unit groups are arranged into readable stacked plots, normally up to three unit axes per plot. Extra panels scroll; resizing refits the plot canvas. Use channel mapping to explicitly choose a panel/axis when the automatic arrangement does not match your analysis.

## Pan, zoom and fit | 2.1.0

Choose **Zoom X**, **Zoom Y** or **Zoom XY** and drag a rectangle over the desired region. **Pan** changes drag behavior to move the view. The wheel zooms according to the enabled dimensions. **Reset zoom / Fit** returns the active plot to its data range. **Back** and **Forward** navigate recorded view history.

X navigation operates on the common coordinate; each Y-axis has its own scale. Moving the view changes the region you inspect, not the stored readings. If nothing is visible, check the channel checkboxes and use Fit before editing the source data.

## Navigation shortcuts | 2.1.1

| Action | Shortcut |
| --- | --- |
| Zoom X / Y / XY | Ctrl+1 / Ctrl+2 / Ctrl+3 |
| Pan | Ctrl+4; Escape while the plot has focus |
| Fit / reset zoom | Ctrl+0; R while the plot has focus |
| Zoom in / out | Ctrl+= / Ctrl+- |
| Previous / next view | Alt+Left / Alt+Right |
| Lock cursors to channels | Ctrl+L |
| Step cursor A | Left / Right with plot focus |
| Step cursor B | Shift+Left / Shift+Right with plot focus |
| Export Report | Ctrl+P |
| Channel Math | Ctrl+M |
| Save workspace | Ctrl+S |
| Open recordings | Ctrl+O |
| Shortcut reference | F1 |

Typing in an input field keeps normal text-editing behavior. Click the plot before using single-key plot commands.

## Zoom behavior correction | 2.1.3

X-only rectangle zoom preserves Y scales; Y-only rectangle zoom preserves X. XY changes both. The selection band reflects the chosen mode. This corrects the earlier rectangle behavior in 2.1.0–2.1.2. Use an updated version if a rectangle appears to change both axes despite choosing only one dimension.

## Cursor A, cursor B and snapping | 2.1.0

**A is cyan** and **B is amber** in plot lines, handles and readouts. Choose **dual**, **point** or **off** in the toolbar. Drag a handle or click the plot to position A; Shift-click positions B in dual mode. **Snap** follows recorded sample coordinates. Use **Tools → Plot → Move cursors…** to enter positions numerically, or its endpoint controls to jump to the recording bounds.

Cursor positions are clamped to supported ranges. Interval calculations handle either cursor order: ΔX is the positive span; signed ΔY follows B minus A. Readout values follow all visible channels at the cursor times, respecting each channel's clock and interpolation kind. Unknown/masked/out-of-range readings are shown as Unknown.

## Lock cursors to channel samples | 2.1.1

Choose **Lock cursors…** on the navigation toolbar or **Tools → Plot → Lock cursors to channel…**. For each cursor, choose **Unlocked** or a visible channel. The lock anchors that cursor to an actual sample of that channel. A and B can lock to different channels. Moving/stepping an anchor updates the other visible channels' readings at that time.

Use Left/Right to step A and Shift+Left/Right for B. Panning moves the view without changing the anchored sample; stepping can bring the sample into view. A lock is useful when following an event in one signal while comparing all the others. It does not grant only that channel permission to pan or zoom. Choose Unlocked to return to free cursor movement.

## Readout and interval measurements | 2.1.0

Open **View → Readout** for A/B channel values and the interval inspector. Open **View → Interval Measurements** for the full measurement table. Select a readout row to inspect that channel. ΔX describes the time/sample span; ΔY is the value change from A to B.

Min/Max describe the supported interval; Mean and RMS are calculated over supported spans. Coverage indicates the span with usable data, not an assumed full recording. Missing spans are not silently bridged. Slope and displayed interval Integral use the plot's coordinate units (for time plots, per-minute and value·minute presentation). A single-point or unsupported interval can have undefined statistics.

For synchronized engineering data, the cursor caption can also show measured power/energy at A when those source columns are available. **Tools → Plot → Copy cursor readout** copies the available readout fields to the clipboard for pasting into a spreadsheet.

## Extended statistics and pinned lock values | 2.1.2

Readout includes **Channel, Unit, A, B, Δ value, Min, Max, Average** and a Match column when channel match metadata exists. The **Cursor interval / Whole recording** selector changes the range used for Min, Max and Average. A, B and Δ still refer to the current cursors. The compact inspector follows the selected readout row; the other channels retain their table readings.

Locked channel values are pinned in the caption with matching A/B colours, channel name, value/unit and timestamp. These make the locked parameter easy to find without scrolling through every row. Range means are span-weighted; the separate Descriptive statistics operation reports arithmetic statistics of finite samples.

## Properties and channel metadata | 2.1.0

Select a channel in Data Portal, then open **Properties**. Edit **Name**, **Unit**, **Group**, **Kind**, custom properties JSON, warning/fault minimum and maximum, then choose **Apply properties and limits**. Use valid JSON for custom properties. These settings describe the channel; they do not rewrite original source tables.

Choose **analog** for interpolated physical signals and **discrete** for held states/codes. Set a unit only when you know its meaning. Warning/fault fields store limit metadata; use the Threshold annotation action when you want an explicit horizontal plot line. The match-percentage colours used in comparison are a separate measure.

## Actuator interpretation and ON duration | 2.1.4

For recognized actuator commands, **0 means OFF** and **any other integer means ON**, including negative integers. Missing, infinite and fractional readings remain Unknown. Heater watts, motor speed, pressure and enumerated program/fault codes remain numeric. Auto recognition is contextual; it is not applied to every integer-valued channel.

Under **Properties → Value interpretation**, choose **Auto (identify actuator commands)**, **Numeric / original readings**, or **Actuator ON / OFF**, then Apply. Numeric restores original source codes when retained. Use the override when a vendor's names do not describe the signal clearly.

Binary plots use steps and OFF/ON ticks. Readout and inspector show A/B states, transitions, ON time, duty percentage and known time. Duty is based on supported known spans; unknown gaps do not count as OFF. Reports retain these readings and original values where supported. Changing interpretation refits the affected Y scale without moving A/B positions.

## Channel organization and annotations | 2.1.0

Select one or more channels and choose **Channel actions…**. Available operations include Rename, Duplicate, Delete, Move/group, Move to dataset, Merge groups, Move up/down, Assign axis, Mask interval, Clear masks, Marker, Threshold and ROI. The Channel menu exposes frequently used actions. Save a workspace before a large organization change if you want to keep a recoverable copy.

**Duplicate** creates a separate channel identity. **Delete** removes the selected channel from the workspace. Move/group and dataset actions organize the tree; assigning an axis changes the plotting binding. **Mask interval** excludes samples between A/B from that channel's analysis without deleting the source table; Clear masks removes channel masks.

**Marker** uses a cursor coordinate; **ROI** marks the interval between A/B. **Threshold** asks for a Y value and uses the selected channel's axis when applicable. Enter a useful annotation label. These annotations are saved with the workspace and included in report presentations where supported.

## Quick event notes | 2.1.2

Choose **Add note** (Ctrl+Shift+N), enter a description, and confirm. The note attaches at A in the active plot. Use this for observed events such as a heater transition, pressure anomaly or operator action. Notes survive workspace save/restore and appear in reports. They do not create or change source measurements.

## Channel mapping and appearance | 2.1.0

Open **Tools → Plot → Channel mapping & appearance…** after loading data. Each row offers Show, source/channel, Label, Unit, Panel, Right axis, Style, Width, Color and Y bounds. Choose the channels to show, their panel numbers (1–10), a line style/width, and optionally a custom colour. Double-click the colour cell to choose it. Enter Y bounds as minimum,maximum when you need a fixed range.

Apply the entries to update the workspace. Appearance changes do not scale numeric measurements. Channels sharing a unit/binding share an axis; use panel/axis assignment for independent scales. A hidden trace remains in the dataset and can be shown again with its checkbox.

## Display options and themes | 2.1.0

Use **Tools → Plot → Display options…** to edit the report/plot title, plot font size, Grid, Legends, Peak power marker and Inlet/drain overlap highlighting, then Apply. Grid is initially enabled; the other optional overlays are initially disabled. Enable only the overlays needed for the current analysis. Peak/overlap features require recognizable relevant signals and do not create measurements where those channels are absent.

Choose **System**, **Dark** or **Light** in the main toolbar. System follows the operating-system theme. The theme changes presentation, not values, units or matching rules. Saved studio display settings restore with the workspace.

## Normalized stacked tracks | 2.1.0

Choose **Tools → Plot → Normalized stacked tracks** to put the active plot's channels on visually separated normalized tracks. Choose it again to restore the prior unit-axis bindings. This is useful for comparing event timing across very different magnitudes.

Only the drawing is normalized. Cursor readouts, processing and exports retain physical/source values and units. Do not read a normalized track's display height as a physical measurement.

## Playback, seeking and recorded phases | 2.1.0

Open **Tools → Plot → Playback & recorded phases…** with nonempty channels visible. Press **Play/Pause**, change the playback speed (0.1×–128×), or move the slider to seek. Cursor A and its readouts follow playback; the view pans when the play position leaves it. Playback stops at the end.

The phase strip/table reflects recorded state/code intervals in the selected data. Click the strip to seek to an interval. It does not invent semantic phase names from an arbitrary code. If no phase/state channel is visible, the dialog reports that rather than fabricating a cycle. Closing the playback dialog pauses playback.

## Subsystem views | 2.1.0

Choose **Tools → Plot → Subsystem view…** and select All, Thermal, Mechanical, Water/valves or Controller. The view selects channels using name keywords. Use checkboxes or channel mapping to correct a vendor-specific channel name that the shortcut cannot recognize.

A subsystem view changes the visible channels/panel arrangement; it does not delete the others. Choose All or select individual channels to return to a broader analysis.

## Formulas and local units | 2.1.0

Open **Analyze / View → Channel Math**. Enter a formula and result name, then **Create formula channel**. Refer to a uniquely named channel with `Ch("Power")`, or use its channel ID if names are duplicated. Supported expressions are numeric constants, parentheses, unary signs, `+`, `-`, `*`, `/`, and `convert(channel_expression, "unit")`.

Examples: `convert(Ch("Power"), "kW")` performs a supported scale conversion; `Ch("Sensor A") - Ch("Sensor B")` calculates a difference on matching clocks; `Ch("Voltage") * Ch("Current")` multiplies the values and retains a product unit label. Multiplying by a scalar alone does not relabel units.

Combining channels requires identical coordinate systems and sample coordinates. Explicitly resample mismatched clocks first. Equal sampling steps alone are not sufficient if grid origins or extents differ; use synchronized channels on a shared timeline when appropriate. Addition/subtraction also require compatible units. Arbitrary Python functions, attribute access and indexing are not formula features. **Define local unit** records a unit name, dimension and scale for supported scale conversions; it does not establish a sensor's unknown calibration.

## Processing workflow and preview | 2.1.0

Select one source channel in Data Portal. In Channel Math choose an operation and set its displayed parameters. **Apply to workspace** creates a derived result channel. The source channel remains available. Derived channels retain recipe/parent information.

For review before adding a result, choose **Tools → Processing → Preview selected operation…**. Inspect the temporary result, then Apply to workspace or close the preview. A changed source requires a fresh preview before applying it. This optional processing preview is separate from the removed permanent sample-preview pane.

Some operations require at least three finite samples on a strictly increasing, uniformly sampled clock. If the app requests resampling or finite data, inspect gaps and choose suitable processing rather than assuming an unknown interval is measured.

## Offset and scale | 2.1.0

Choose **Offset and scale**, enter scale and offset, then Apply. Each output value is `source × scale + offset`. The source clock is retained. Example: scale 2 and offset 1 turns a source reading of 3 into 7. The operation does not infer or automatically relabel the resulting engineering unit; set verified metadata appropriately.

## Time shift | 2.1.0

Choose **Time shift**, enter Shift in the channel's coordinate units, then Apply. Positive values move a time trace later; a negative value moves it earlier. In a minute-based plot, a 30-second shift is 0.5. Original source samples are retained through the derived channel's time shift. For alignment between recordings, use the synchronization strategy instead when event-based matching is appropriate.

## Resampling | 2.1.0

Choose **Resampling** and enter the new coordinate step. For minute-based channels, 1 second is `1/60` minute (approximately 0.0166667); a step of 1 means one minute. Analog data uses supported interpolation; discrete data uses held readings. Duplicate source coordinates are handled explicitly in the projection.

Inspect the resulting sample count and gaps before frequency/filter analysis. A regular output clock does not make an unknown source span known, and selecting a small step does not add actual sensor resolution.

## Moving average | 2.1.0

Choose **Moving average** and enter a window in samples. The window must be positive and fit the data. This smooths uniformly sampled finite data. Unsupported edge positions are left unknown rather than presented as full-window averages. Larger windows suppress more short-term variation but can obscure brief events; inspect the source alongside the result.

## Savitzky–Golay | 2.1.0

Choose **Savitzky–Golay**, enter the sample window and polynomial order, then Apply. Use a window appropriate to the data and greater than the polynomial order; invalid combinations are rejected by the filter. The operation requires a finite uniform clock. Compare against the source to check whether smoothing preserves the peaks important to the test.

## Butterworth low-pass | 2.1.0

Choose **Butterworth low-pass**, enter filter order and Cutoff in **Hz**, then Apply. The cutoff must lie below half the sampling frequency, and the recording must be long enough for the filter. The app uses forward/backward filtering. The time axis can be minutes while filter frequency remains Hz: a 1-second sample interval has a 1 Hz sampling frequency, so its cutoff must be below 0.5 Hz.

## Differentiation | 2.1.0

Choose **Differentiation** to create the numerical rate of change. A finite uniform clock is required. For time channels, the calculation uses seconds and the result is labelled value/second, even though the plotted time coordinate is minutes. Differentiation amplifies noise; inspect or appropriately smooth the source first.

## Cumulative integration | 2.1.0

Choose **Cumulative integration** for an accumulated value over supported spans. Analog signals use trapezoids; discrete signals hold their prior value over an interval. Time calculations use seconds, so a W input produces a W·s result. A positive-duration unknown gap restarts the accumulation on the next supported segment rather than silently bridging missing data.

Do not interpret W·s as Wh without an explicit conversion (3600 W·s = 1 Wh). Use the engineering energy KPI when you need its established Wh calculation. The processed integral channel's SI units differ from the compact interval table's coordinate-based integral presentation.

## Descriptive statistics | 2.1.0

Choose **Descriptive statistics** to create a metric-indexed result containing arithmetic mean, RMS, minimum, maximum, peak-to-peak, standard deviation and count of finite source samples. A source without finite values cannot produce these statistics. The output coordinate is a metric index, not time; inspect its metric labels in the table rather than overlaying it as a time trace.

## Histogram | 2.1.0

Choose **Histogram**, enter a positive bin count, then Apply. The result counts finite values by value interval; its X coordinate represents source value and Y represents count. Histogram bins are not minutes. Missing/masked values are excluded. Compare distributions with the same binning when interpreting differences.

## FFT | 2.1.0

Choose **FFT** for a finite, uniformly sampled time channel. Resample explicitly if the recorded intervals differ. The result is a mean-removed one-sided amplitude spectrum, with frequency in **Hz**. It opens in a compatible frequency viewport. It describes frequency content, not the source's time evolution. The sampling interval limits the highest interpretable frequency.

## Welch PSD | 2.1.0

Choose **Welch PSD** for a finite uniform time series. The result is power spectral density with frequency in Hz and value²/Hz units, using supported segments up to 256 samples. The frequency resolution depends on the sampling rate and segment length. Use it to compare sustained spectral energy; use FFT when an amplitude spectrum is the desired output.

## Peak and valley detection | 2.1.0

Choose **Peak and valley detection** and set Prominence. The result contains source-coordinate/source-value points identified as peaks or valleys. A larger prominence filters smaller features. This operation requires supported finite uniform data. The detection threshold is in source value units; it is not a time interval or match percentage.

## Engineering recording controls | 2.1.0

Open **View → Engineering Controls** or **Tools → Engineering → Recording controls**. Choose a power recording and/or machine recording. At least one is required. Select a synchronization strategy and choose **Align recordings**. One recording can be analyzed without supplying a second file. The resulting channels and diagnostic tables load directly into Analysis.

The **Manual offset** field is in **seconds**, even though plots use minutes. The synchronization notes describe the chosen events, shifts and any unavailable channels. Inspect those notes before treating two traces as synchronized. The app does not rescale physical values to force a match.

## Synchronization strategies | 2.1.0

**Intelligent (Heater ON to >1.5kW Spike)** aligns the heater event with a measured power rise when recognizable inputs exist. If they are unavailable, inspect the warning/notes and choose another strategy. **First Drum Start to First Power Rise** aligns the detected drum and power events. **Raw Timestamps (No Shift)** keeps the source clocks. **Manual Time Offset (Minutes)** uses the manual offset entered in the UI (the UI field remains seconds and converts it for the engine).

Both recordings need recognizable timestamps for synchronization, and they must overlap after the selected shift. Diagnose a no-overlap message by checking dates/time zones and selected events; do not assume two relative-zero clocks establish the same physical event. Installed synchronization extensions can contribute additional strategies.

## Re-align recordings without duplicates | 2.1.1

When you choose Align recordings again for the same sources/columns, the app updates existing aligned channel identities and adds genuinely new channels instead of accumulating duplicate traces. Existing channel visibility, cursor locks and explicit interpretation/style settings are preserved where the refreshed source identity matches. A deliberate user-created duplicate remains a separate channel.

## Engineering KPIs and data quality | 2.1.0

Choose **Tools → Engineering → KPIs & data quality…**. For aligned recordings, inspect duration, measured energy, power, temperature/speed metrics and available quality/synchronization tables. For ordinary imports, the dialog provides available channel/data quality information. Missing columns cannot establish a KPI and are not fabricated.

Inspect missing/non-finite values, timestamp exclusions, duplicate handling and units alongside the headline metrics. The full diagnostic workbook exports the associated tables. A KPI computed over available data is not proof that a recording has complete coverage.

## Simulation reference loading | 2.1.0

Choose **Tools → Data → Open simulation reference…** for a supported simulation CSV, ZIP package or chart image. This can load reference curves without a bench recording. Use **Reference details…** to inspect extraction/units/package provenance, then plot the desired curves with checkboxes.

A simulation ZIP uses its supported run/package definitions; it differs from a generic ZIP-of-CSV import. Unsupported package structure or missing curves produces an actionable error. Original reference/package tables are retained in diagnostics where available.

## Reference units | 2.1.0

Use **Tools → Engineering → Reference units…** to choose supported simulation time, pressure and remaining-time metadata before running comparison. These choices describe reference interpretation; confirm them against the source file. Current pressure comparison retains original pressure numbers labelled Pa rather than silently scaling values based on a selected label.

After changing comparison/reference settings, run the comparison again to apply them. Metadata alone must not be mistaken for a sensor calibration.

## Image reference calibration | 2.1.0

Use **Tools → Engineering → Image reference calibration…** for a supported simulation chart image. Set duration in minutes, reference height, and plot bounds as left,right,top,bottom, or leave bounds blank for automatic extraction. Review per-signal calibration ticks/ranges and mark time/signal ticks verified only after checking the image.

Estimated calibration remains identified in diagnostics. The extractor supports the known simulator colour/tick profile; it is not universal chart OCR. Verify extracted curves against the image before quantitative comparison. **Reference details…** exposes calibration and extraction-quality information.

## Compare original recordings | 2.1.0

In Engineering Controls choose the machine/bench recording and simulation CSV/ZIP/image, then **Compare original recordings**. The Comparison workspace shows available bench/reference traces and a scorecard. Their checkboxes independently control visibility. Keep the original Analysis workspace for a separate inspection.

The scorecard reports supported comparisons, signed differences and match percentages. Unknown/unsupported metrics stay unknown. Digital heater states and measured heater watts are treated according to their different signal meanings, not subtracted as equivalent quantities.

## Comparison mapping and match colours | 2.1.0

Use **Tools → Engineering → Comparison signal mapping…** to override an ambiguous bench-column match. Choose Auto, None to disable that mapping, or the actual source column for each parameter. Run Compare again after applying the mapping. Reference settings and image calibration also apply when the comparison runs.

Match backgrounds/accents use **green for ≥90%**, **amber for 70–89%**, and **red for <70%**. Missing or invalid percentages stay neutral. The percentage remains the numerical result; colour communicates its band. Warning/fault channel limits and legacy tolerance metadata do not redefine these bands.

## Export Report | 2.1.0

Choose the prominent **Export Report** button or Ctrl+P, then choose PDF, Excel, CSV or high-resolution PNG and a destination. One save dialog controls format/location; there is no report wizard. The active workspace must contain at least one visible channel. Cancel leaves no new report.

PDF/PNG summarize the active plots, cursors and relevant scorecard/annotations. Excel/CSV provide active-interval data and supported cursor/summary information. Review cursor positions and the selected statistics scope before exporting. Transient UI guides, where available, are not measurement cursors in reports.

## Full and alternative exports | 2.1.0

**Tools → Export → Full diagnostic workbook…** includes retained source, aligned, curve, scorecard, quality and calibration/package tables that are available in the session. **Full synchronized CSV…** exports the aligned series and requires an aligned recording. **Complete processed channels…** exports full derived-channel data to CSV/Excel rather than only the active cursor interval.

**SVG / HTML / Markdown…** exports alternative presentation formats. Select the active workspace and appropriate visible channels first. Use SVG for editable vector output and a workspace save when you need to preserve interactive settings; a picture or PDF is not a restorable session.

## Save and restore workspace | 2.1.0

Choose **Save workspace** (Ctrl+S) and a JSON destination. A generation-named adjacent NPZ contains the numeric channel arrays; the JSON stores source/diagnostic tables, channel metadata and view/studio state. **Keep the JSON and its referenced NPZ together** when copying or sharing a session.

Choose **Restore** and select that workspace JSON. The session restores source values, processing results, plots, cursor settings and panel layout. Existing settings saved in that workspace take precedence over new-workspace defaults. Saving a new generation does not overwrite the original recording. Move/copy the matching pair as a unit; renaming only the NPZ breaks the reference.

## Channel presets | 2.1.0

Use **Tools → Data → Save channel preset…** for reusable channel/display choices, and **Load channel preset…** to apply them to matching channels. Presets can be loaded before the recording and applied when matching data becomes available. Legacy supported JSON presets are accepted.

A preset stores configuration rather than the full measurement arrays. Use a workspace JSON/NPZ pair for an exact session copy. Review labels/units/panel matches when applying a preset to a different recording layout. Interpretations are retained by presets in versions that support actuator interpretation.

## Extensions | 2.1.0

Open **Tools → Extensions → Manage plugins…**. Install a local Python extension, enable/disable it with its checkbox, Reload after edits, Remove an unwanted extension, or Open folder to inspect its files. The interface reports registration errors and descriptions. Extensions use the supported `register_patch(manager)` protocol and can provide synchronization, KPI or plot hooks.

**Run plot extensions…** opens registered plot hooks in the Qt-hosted plot dialog, with supported image/vector export. Synchronization/KPI hooks run with alignment. Extensions execute local Python code and can require libraries not bundled with the app; install only ones whose behavior you understand. Disabling an extension removes its active hooks from subsequent operations.

## Illustrative example and reset | 2.1.0

Choose **Tools → Examples → Load illustrative cycle into workspace** to explore the controls without a test file. These channels are explicitly labelled synthetic/illustrative and are not evidence from a real appliance. They load directly into the active workspace.

**Tools → Data → Reset workspace** clears the current analysis state. Saved files remain on disk. Save a workspace first if you need to return to unsaved session changes. Use Open/Restore to load actual data again.

## TDMS recordings | 2.1.6

Open `.tdms` directly; the reader is bundled, with no separate NI installation required. Supported inputs include LabSys Value/dTime/Status groups, explicit channel clocks and NI waveform sampling increments. Each measurement retains its own native timestamp sequence and sample count in the direct Analysis view; it is not aligned by row number to another channel's clock.

Declared units and source/group/channel metadata are retained. Already scaled engineering values are not scaled a second time. Metadata expressions are stored as information rather than executed. Invalid LabSys quality becomes unknown data. Units absent from the source remain unknown/editable. Recognized LabSys heater/pump/valve commands use contextual ON/OFF interpretation; program and error codes remain numeric.

TDMS also works in engineering alignment/comparison. The synchronization adapter derives a union of recorded timestamps and holds only preceding readings for up to five seconds, matching the engine tolerance. Direct plots still use native samples, and alignment retains the untouched TDMS source table separately. Untimed TDMS channels use sample indices for direct analysis; do not invent a clock for synchronization.

## Mouse X/Y hover | 2.1.6

Move the mouse inside a plot. A live crosshair and compact readout show **Mouse X** in minutes/the plot's coordinate unit, and **Mouse Y** in every independent Y-axis scale. The nearest trace is highlighted with its actual sample timestamp, value and unit. A pointer coordinate and the nearest sample coordinate can differ; both are labelled.

ON/OFF traces show state readings. Normalized tracks retain original physical readings in the sample readout. Hovering does not move A/B or alter their locks. Leaving the plot, hiding all channels, changing view ranges or closing the plot clears transient guides. Hovering is enabled by default and its guides stay out of saved reports.

## Updates and recovery | 2.1.5

Open **Info**, choose **Check for updates**, read the available version/release notes, and choose **Download update**. Downloads run in the background and can be cancelled. After verification, choose **Install update & restart**. The app saves a recovery workspace, replaces the executable, restarts and restores the saved analysis. Check/download actions are user initiated; recordings are not uploaded.

The Windows app folder must be writable. The previous EXE is retained as a backup; replacement/launch errors trigger rollback and an installer log. Keep remaining portable dependencies if using the backup of a portable build. A power interruption can require manually restoring the previous EXE. Automatic installation is for the downloaded Windows app; source checkouts are updated through their source workflow.

The first upgrade from 2.1.4 or earlier needs a manual download to gain the updater. Later releases can use this built-in flow. A failed connection or cancelled/corrupt download leaves the installed version unchanged. Offline analysis and the bundled manual remain usable.

## Info toolbar, version manuals and search | 2.1.7

Choose **Info & manual** in the main top toolbar. It opens a separate, resizable manual/update window; Analysis and Comparison remain the only graph-workspace tabs. You can keep the manual open while inspecting the analysis, and close/reopen it without changing data or the active plot.

**Tools → About version** opens this same window; F1 still opens the compact keyboard-shortcut reference. Select the app version whose features you want to read about. The **topic selector** jumps to a feature; the search field and **Find next** locate a keyword and wrap through the document. A no-match message applies to the selected manual only. The guide covers inputs, actions, results, units, defaults and common failure conditions for the supported features.

All panels listed in View, plus the channel-kind column, are enabled in a new workspace. The first automatic update from a pre-2.1.7 release applies this new default once; later update recoveries retain saved visibility preferences. **View → Show all panels** restores this layout in one click without clearing data. Panels sharing an area remain available as dock tabs. Hide any panel through View if you prefer more plotting space. Restoring a saved workspace still restores that workspace's own panel layout.

## Troubleshooting and useful checks | 2.1.0

| Symptom | Check/action |
| --- | --- |
| Blank plot | Check at least one channel; click its plot and Fit |
| Value is Unknown | Inspect source gaps, masks, quality status, cursor bounds and Coverage |
| Wrong time span | Check coordinate column/unit; minutes are the standard display |
| Curves seem to share an unsuitable scale | Verify units and use channel mapping/axis/panel assignment |
| Filter or FFT is rejected | Inspect finite data and strictly increasing uniform sampling; resample explicitly |
| Formula cannot combine channels | Resolve unique names/IDs, compatible units and identical clocks |
| Alignment has no overlap | Check source dates/time zones and chosen synchronization events/offset |
| KPI or comparison is missing | Check required channels, mapping, unit metadata and extraction quality |
| Panel is missing | Enable it through View; select its dock tab |
| Session restore lacks arrays | Keep the referenced adjacent NPZ with the workspace JSON |
| Export is empty | Select visible channels in the intended active workspace and review A/B |

Use Channel Table for source evidence, diagnostics for assumptions/quality, and a saved workspace to reproduce the analysis. The status bar and action messages identify invalid inputs; correct the cause before re-running an operation.

## Removing recordings and clearing the workspace | 2.1.9

Use **Data Portal → Remove recording…** (also in the Channel menu), choose the loaded dataset and confirm the selection. It unloads that dataset's channels and dependent derived traces from Analysis and Comparison, releases their cursor locks, and removes its source table. Other recordings stay loaded. Source-only diagnostic tables can also be selected in this picker. Independently imported aligned/comparison datasets remain separate entries; remove those entries too if you no longer need them.

**Clear workspace** unloads every recording, generated channel, table and plot from both workspaces after confirmation, and clears the engineering file fields. Original input files, saved reports, workspaces and parameter templates are kept. Hiding/deselecting a channel only changes visibility; removing a recording unloads it. Save a workspace before clearing if you want to resume that analysis later. Removal is unavailable while processing is in progress. Large workspace save and restore run in the background so the interface can continue repainting; wait for completion before modifying channels.

## TDMS parameter review and reusable templates | 2.1.9

On the first **Open** of a TDMS recording, review all measurement parameters before they are added to the workspace. The table shows original parameter names, suggested short names, editable units, interpretation, sample counts and numerical ranges. For example, `PDH_AAS_B_V1_0_R` is suggested as **Valve 1**; you can change it to the actual function you know. Unknown hardware labels remain descriptive rather than receiving an invented physical meaning.

Choose **Automatic**, **Raw numeric**, or **ON/OFF** per parameter. ON/OFF maps zero to OFF and finite nonzero integers to ON; fractional and missing readings remain unknown. Choose this for actual actuator commands, not temperature, speed, program states, error codes or sensor readings. The automatic interpretation keeps its contextual rules. Editing a unit declares metadata; it does not numerically convert values. Use an explicit conversion operation when a conversion is needed.

**Save template and load** stores reviewed choices in `templates/tdms-parameters.json` under the output folder. It stores labels, units and interpretation only, never measurement arrays. Future imports compare exact original group/channel identities and reuse known choices automatically; only unknown parameters prompt for review. The source filename may change without losing a template. Cancelling review cancels that import batch without adding data or saving choices.

To revise saved choices, use **Channel → Review TDMS parameters…** with a TDMS recording loaded. Changes apply to loaded TDMS channels and future imports. Original names remain in channel metadata, original source tables are retained, and raw actuator readings remain available. Save the workspace separately to persist a session. An unreadable template produces a review warning instead of silently applying invalid choices.

## Output folder and stored files | 2.1.9

The app creates **SignalStudio_Output** beside the executable (beside the source checkout when running Python). It uses **reports**, **workspaces**, **templates**, **diagnostics** and **presets** subfolders. If the application directory is read-only, it falls back to `Documents/SignalStudio_Output`. **Info & manual** shows the actual path and an **Open output folder** button.

Report/export and workspace/preset save dialogs start in these folders. You can deliberately choose a different destination. Nothing is exported without a save action. Keep workspace JSON and its named NPZ companion together. Reports and templates survive clearing the workspace and updating the executable. Do not keep personal recordings or generated output inside Git; the repository ignores the default output folder.

## Updates on managed networks and offline import | 2.1.8

If the check fails with a DNS/proxy error such as `getaddrinfo failed`, the installed app cannot reach GitHub through that connection. Starting in 2.1.8, the updater retries through Windows Internet Options' system proxy, including PAC/WPAD and signed-in proxy credentials. It keeps HTTPS verification and company policies in place. It cannot override a blocked domain or a network outage; ask IT to permit the official GitHub release download locations if needed.

For an approved offline update, put the official release's `update.json` and `ApplianceSignalStudio.exe` together in one folder. Choose **Info & manual → Import offline update…** and select that manifest. The app validates the official repository URL, version, file size and SHA-256, then offers installation on the packaged Windows app. Do not rename arbitrary executables to bypass validation. The same workspace recovery, backup and rollback process applies.


## File isolation and graph navigation | 2.2.0

Each file header in Data Portal has its own Select All/Deselect All checkbox. It affects only that file, including its channels hidden by a name filter. There is no global Select All control. Files and channel groups keep their stable dataset identities. **Close Dataset** beside each file unloads it from both workspaces without changing other files; right-click the file header for Select All, Deselect All and Close Dataset. Data tables without traces can still be closed. Independently generated aligned/comparison datasets are separate entries.

**Engineering Controls is the selected dock tab at a new launch**, sharing its existing area with Data Portal. No separate Engineering dock area is created. Switch to Data Portal to manage files. Explicit workspace restores retain saved dock layouts.

The active graph's top-right toolbar offers **Zoom In**, **Zoom Out**, **Box Zoom**, **Pan Graph**, **Reset Scale** and **Lock Time Axes**. It follows the graph you click, and uses an overflow menu in narrow panels. With Lock Time Axes enabled, compatible time viewports share X navigation; zoom buttons also scale each independent value axis once. Reset Scale fits the synchronized group to its full combined data extent. Disable Lock Time Axes to navigate the active plot independently. Time and frequency/sample coordinates remain separate.

Tools → Plot retains **Zoom Time Axis**, **Zoom Value Axes** and **Zoom Both Axes** with Ctrl+1/2/3; Pan is Ctrl+4, Reset is Ctrl+0/R. The floating HUD shows absolute |ΔY| and nonnegative ΔX even when A crosses B; signed B−A values remain available in the detailed table and export. Cursor A stays cyan and B orange. Restoring a saved workspace preserves offscreen cursor anchors while the layout settles; a deliberate drag resumes normal visible-data clamping.

## Separate About and User Manual windows | 2.2.0

**About / Updates** opens a modal window with version, build date, release notes, changelog, license information and update/offline-import controls. The project currently declares no repository distribution license; the window reports that fact and identifies third-party licenses without inventing a grant.

**User Manual** (or **F1**) opens a separate nonmodal documentation window. Choose a version, jump to a topic, or search for text/Find Next. You can leave it open while working on plots. Calculation tutorials are under Formula Channels, Moving Average, Resampling, FFT and the other processing topics. Cursor locking/stepping and keyboard navigation are documented in their dedicated topics. About does not contain a second embedded copy of the manual.

## Legacy configurations and installation lifecycle | 2.2.0

The app still reads schema-1 JSON/NPZ workspaces, version-2/3 channel presets and unversioned channel maps. It also adapts known JSON wrappers, XML presets (`signals/channel` elements with named attributes), XML with an embedded `json` element, INI sections `channel:Name` / `signal:Name` plus `options`, and INI workspace JSON under `[workspace] payload`. Original files and unknown metadata are preserved. Unsupported future schemas or unrecognized structures produce an error before modifying the workspace; arbitrary third-party XML/INI cannot be reconstructed without its schema.

Settings, reviewed TDMS templates, presets and extensions now use `%APPDATA%/ApplianceSignalStudio` (a per-user config directory on other platforms). Reports and saved workspaces keep their existing output locations. Earlier portable templates/presets/plugin settings are copied and checksum-verified before cleanup. Name conflicts are retained under `legacy-imports`, never overwritten. Migration reports remain in the settings folder.

After a normal packaged Windows startup and successful recovery restore, the app discovers its exact product registry entries and previously registered installation paths. It removes obsolete executable files only after checking the product/version resources or a stored file inventory. Unchanged dependency files are removed only when a prior ownership/hash inventory exists; directories are removed only when empty. The running EXE, user data and modified/unrecognized files are retained. Older portable libraries without an inventory cannot safely be attributed to the app and are retained. Permission or migration failures leave cleanup pending; there is no elevation or execution of registry uninstall commands. The process records removed/retained paths in `lifecycle.json`.

The updater retains a previous EXE while replacement is in progress. That obsolete backup is eligible for permanent removal only after the new application successfully initializes/restores. If recovery fails, it is retained. Self-tests and source launches never delete installed binaries.

## TDMS templates in Engineering Controls | 2.2.1

1. Choose a TDMS file in either recording field of **Engineering Controls**.
2. Click **Align recordings** or select the TDMS machine recording and a reference, then **Compare original recordings**.
3. On first use, review all new native TDMS parameters. Edit the short display names and units; choose Automatic, Raw numeric or ON/OFF. Save to continue. Cancel leaves the current workspace unchanged.
4. Previously reviewed exact TDMS parameter identities reuse the same template as **Open Data Files**. Only newly encountered identities need another review. Templates remain in the per-user settings folder across updates.
5. Alignment shows your reviewed channel names and interpretation. Comparison bench labels carry a **· bench** suffix; reference labels remain separate. Comparison traces retain their calculated reference units and comparison meaning. Display names do not rename raw source columns or silently change benchmark mappings.
6. Use **Review TDMS parameters** to revise saved choices. Original measurements remain available; choosing Raw numeric recovers actuator codes rather than losing them to ON/OFF normalization.

Sample-indexed TDMS channels without a clock can be reviewed through Open, but engineering alignment requires recorded timing. Reviewing a name does not calibrate raw motor speed into drum RPM or establish a correspondence between two unknown sensors.

## Update restart and Python DLL recovery | 2.2.1

Updates and rollback restart with a fresh bundled Python runtime, independent of the old temporary extraction folder. If an older updater shows **Failed to load Python DLL** immediately after replacing the executable, close the error and launch the saved executable directly from File Explorer. The updated updater takes effect once the new app has started.

If a direct launch also fails, download the portable ZIP from the same GitHub release, extract its entire folder, and keep `_internal` beside the executable. Preserve your workspaces and templates. Do not fetch individual runtime DLLs from unofficial download sites. If the complete portable folder cannot run, retain the exact error and check your machine's security/quarantine history with IT.

## Upper navigation toolbar and clear hover view | 2.2.2

The graph tools are in the **upper application toolbar, directly below the main file/report controls**, above the Analysis/Comparison graph area. They no longer float inside a plot.

- **Zoom X** (Ctrl+1): box zoom along time only; value axes stay fixed.
- **Zoom Y** (Ctrl+2): box zoom along value axes only; time stays fixed.
- **Zoom XY** (Ctrl+3): box zoom along both dimensions.
- **Pan** (Ctrl+4): drag to move the view.
- **Zoom In / Zoom Out** (Ctrl+= / Ctrl+-): scale the enabled dimensions.
- **Reset View** (Ctrl+0): fit the active compatible group to its data.
- **Lock Time Axes**: link compatible plots in the current workspace.
- **Lock Cursors** (Ctrl+L): anchor A and/or B to samples from chosen visible channels. Read the anchored values in the Readout table and cursor cards; the rest of the channels follow those times.

The selected navigation mode stays visibly pressed. Analysis and Comparison remember their own modes. New plots inherit that workspace's selection, and saved workspaces retain it. Older workspaces without a mode use Pan.

Mouse X/Y text is displayed in a **fixed strip outside the canvas**. The first line reports the mouse coordinate and the independent Y-axis coordinates. The second line identifies the nearest trace, actual sample time, value and unit. A stationary strip cannot cover traces, drag handles or cursor labels. It does not resize the graph as values change. Long content is shortened to fit; hovering over the strip reveals the complete readout. Moving out of a graph clears the transient readout and guides. Hover remains enabled by default and does not move or unlock A/B.

## Quick zoom beside Analysis and Comparison | 2.2.3

The unused top-right space on the same row as the **Analysis / Comparison** tabs now provides **+ (Zoom In)**, **− (Zoom Out)**, **Reset View**, and a mode selector displaying **Zoom X**, **Zoom Y**, **Zoom XY** or **Pan**. These controls stay above the canvas even when a stacked layout scrolls.

Click the mode selector to choose which axes a rectangle gesture or zoom button affects. The main header and quick controls share the same actions and checked mode, so keyboard/menu changes remain consistent. Zoom buttons operate on the active graph and respect Lock Time Axes for compatible plots. Analysis and Comparison each retain their own settings.

Mouse X/Y keeps its separate full-width readout below the tabs; no popup covers the plot. The strip keeps its existing height. Narrow windows use the quick toolbar's overflow menu for zoom actions; the mode selector remains directly available on the right. Coordinate text uses a compact X/Y presentation when space is limited; the tooltip retains the full wording and precision. Full hover text remains available on the readout tooltip. Existing header tools and shortcuts remain available.

## About menu and individual channel colors | 2.2.3

Choose **About → User Manual** beside Tools, or press **F1**, to open searchable help. Choose **About → Updates** for the version, build date, changelog, license and update controls. Both features remain available in their existing windows.

Every newly plotted channel receives its own stable trace color, including valves sharing a state axis. Legend swatches match their traces. Legends are enabled for new workspaces; **Tools → Plot → Display options → Legends** controls visibility. Saved visibility and custom channel colors remain respected. Automatic colors are saved with channel metadata and used by reports.

## Compact controls and workspace focus | 2.3.0

The **top application toolbar** is the only primary navigation control set. Magnifier +/− zoom, fit/reset and hand/pan icons have tooltips, keyboard access and checked mode state. Zoom X/Y/XY remain explicit. Duplicate graph-tab quick controls were removed with approval; functions and shortcuts remain. **Legend**, **Grid** and **Peak Power Marker** apply immediately to the active workspace without a dialog. Analysis and Comparison save their own display choices. Advanced title/font/overlap controls remain under **More → Plot Appearance / Layout → Display options**; changing checkboxes applies immediately. The retained Apply button closes after applying the complete form.

Small dialogs fit their content. Larger forms/tables remain resizable and use scrolling when a screen is small. Opening geometry is clamped to the current available screen; native 100%, 125% and 150% scaling checks are part of release validation. More shares the existing Tools menu actions: Import/Export, Appearance/Layout, Processing/Derived Channels, Engineering, Channel Management, Presets/Extensions and Preferences. Existing menu paths and shortcuts remain accessible.

**Playback** opens an inline strip, not a large popup. Play/Pause, speed, Previous/Next Sample, seek slider, current time and Close Playback remain visible. Observed phase details expand only when a selected discrete phase/code channel exists; otherwise a compact message is shown. Playback uses the existing clock service and stops on close/end. Speed is saved per workspace; playback pauses and closes before a workspace restore so controls cannot retain old channel references. Engineering named phases require confirmed configuration; raw firmware codes are not assigned invented names.

**More → Application Preferences → Focus Graph** (Ctrl+Shift+F) temporarily hides docks only when explicitly selected. Turn it off or choose Restore Normal Workspace to restore the saved previous dock layout, refitted by Qt when display geometry changes. The normal-layout snapshot is also retained when a focused workspace is saved. Engineering Controls remains the default dock tab on fresh launch. For more than twelve active graph channels, a scrollable legend strip above the canvas retains every entry without covering traces; smaller legends use compact translucent theme-aware styling. Custom colors are preserved; automatic colors survive presets and copied channels receive distinct automatic colors.

## Engineering Setup and appliance profiles | 2.3.0

Choose **Engineering Setup**. Select Washing Machine, Refrigerator, Dishwasher, HVAC or Generic Appliance. Each profile has a schema version, canonical channel definitions, physical domains, aliases, units, phases, KPI operations, calibration references, tolerance and acceptance configuration. Default phase names are available but have no guessed firmware mappings. Appliance-specific profiles provide appropriate starting measurements/KPIs; no profile constitutes standards certification.

Choose the **Analysis Run**, or **Reference Run** and **Candidate Run**, with an optional **Golden Run**. Roles refer to separate datasets; multiple files are never combined or chosen by first-file accident. A single dataset can be selected automatically for a single-run analysis. Close Dataset and per-file channel checkboxes keep their existing behavior.

On **Review Channel Mapping**, inspect each source name, source unit, recognition method and canonical parameter. Confirm or change the mapping. The source-unit column is editable: only confirm a unit you know the logger recorded. Editing metadata does not rescale raw samples. A blank/unknown unit must not be replaced based on magnitude. Explicit user choices take priority over previous templates, source canonical metadata, profile aliases and validated anchored patterns. Ambiguous or duplicate canonical matches are not silently chosen; they remain unavailable until reviewed. Full original source names remain in metadata and engineering synchronization.

Save Engineering Setup to retain configuration in the workspace and canonical mapping templates in the per-user templates folder. Confirmed source-unit choices can be reused without changing original samples. Import Profile and Save Profile manage reusable JSON configurations. Corrupt/future schemas and invalid rules are rejected before active configuration changes. The machine-readable schema is `profiles/profile.schema.json`; runtime validation additionally checks cross-references and finite numerical rules. Advanced edits use Profile Configuration; Refresh Mapping Review applies edited definitions to the review table.

## Phases, calibrations and acceptance configuration | 2.3.0

**Add Phase Rule** provides a named phase, canonical parameter, condition, value and minimum duration. For example, a known Cycle State code can be assigned to Wash only after its meaning is confirmed. Advanced rules can combine conditions, use `off_threshold` hysteresis, `debounce_seconds`, minimum duration and independently overlapping phases. Heating start/end/rate and spin stability/acceleration KPIs require their configured Heat/Spin phases; a whole-cycle slope is not substituted for a phase-specific performance metric. Drain evacuation rate requires a calibrated tub-volume channel, not a cumulative inlet counter. Named phase ribbons follow the active time graph and show start/end/duration tooltips; they stay outside the canvas. No observed configured phase means Not Available, rather than an invented cycle breakdown.

Example confirmed phase configuration (code 4 is illustrative, not a supplied manufacturer mapping):

```json
{"name":"Wash","conditions":[{"channel":"cycle_state","op":"eq","value":4}],"minimum_seconds":5,"debounce_seconds":2}
```

**Set Acceptance Limit** creates an explicit minimum/maximum with a KPI unit. Only these limits can produce Pass or Fail, and only when supporting coverage is complete. Blank limits, missing inputs and incomplete data produce Not Evaluated. **Set Tolerance** adds an absolute or relative comparison band; it is not formal acceptance.

Units include °C/K/°F, Pa/kPa/bar/mbar/mm H₂O, L/s/L/min/L, Hz/kHz, RPM, acceleration g, displacement mm, torque N·m, V/A/W/Wh/kWh, %, conductivity μS/cm and time units. Temperature conversion includes offsets. Sensor-frequency/pulse calibration requires an explicit verified calibration ID. Never label frequency as pressure or water volume by scaling an unverified value.

Example advanced calibration structure (replace every illustrative point with approved calibration data):

```json
{"id":"YOUR-CALIBRATION-ID","verified":true,"input_unit":"kHz","output_unit":"L","x":[1,2],"y":[0,10]}
```

Place it under `calibrations` and set the canonical channel definition's `calibration` key to its configuration name. Calibration never extrapolates beyond its supplied points. Pulse-volume KPIs instead require a verified `volume_per_pulse`, calibration ID and output unit. Unknown calibration stays unavailable. Standards/test-method names are metadata, not automatic compliance assertions.

## Engineering calculations and quality | 2.3.0

Choose **Analyze Engineering Data**, then Engineering Results under More/Tools → Engineering Diagnostics. Optional subsystem tabs show Water, Heating, Motor/Spin and Electrical results for washing-machine profiles. Other appliance profiles provide appropriate groups. Missing channels remain Not Available; zero remains a valid measured result. The generic profile can load unknown telemetry without inventing canonical meaning.

KPI definitions use whitelisted declarative operations, not unrestricted expressions or eval: duration, integral, mean, minimum/maximum, RMS, standard deviation, first/last, slope, counter increase, ON duration, calibrated pulse volume, difference and ratio. Required channels, units and phase scope are checked. Definitions are exported with results. Existing Calculate Channel arithmetic, filters and FFT remain unchanged.

Power integration uses seconds internally: `Wh = integral(W, seconds) / 3600`. Flow integration uses `L = integral(L/min, seconds) / 60`. Heating rate uses °C/min. Standard deviations use stable centered calculations. Counter resets are reported as unavailable rather than silently counted as a valid increase. Actuator mapping applies 0 OFF / nonzero finite integer ON conditionally; fractional/missing values remain unknown and raw command codes are preserved.

Continuous analog traces interpolate only within supported intervals; codes, states and counts use held values. Last duplicate timestamp is the established timing-analysis convention; all original rows and recorded peaks remain preserved. Duplicate timing is disclosed and cannot produce a formal Pass. No extrapolation is performed. By default intervals exceeding three times the median positive sampling interval are treated as unsupported gaps; set `extensions.max_gap_seconds` to an approved explicit gap limit. Existing heater/drum synchronization retains its separate five-second causal policy.

Detailed cursor statistics are reused. The compact readout adds RMS, slope, integral, coverage and interval power energy in Wh; signed B−A remains in detailed/export results, while the established crossed-cursor HUD uses absolute deltas. The original sample clocks, masks and locking behavior remain available.

Configured anomaly rules support explicit fault values, OOB thresholds, dropout gaps, temperature stalls and confirmed actuator-transition sequences. A stall requires a fully supported lookback window. Sequence rules specify ordered conditions and a `within_seconds` window; matching a forbidden configured sequence is evidence, not a guessed manufacturer fault. Results distinguish Detected, Not detected and Not evaluated. Default profiles provide data-gap quality rules; unspecified fault meanings remain unevaluated.

## Reference comparison and tolerance envelopes | 2.3.0

Select Reference/Candidate/Golden datasets in Engineering Setup and switch to Comparison before analysis. **Set Timeline Anchor** supports recorded coordinates, first confirmed actuator activation, configured phase transition or a cursor/event/manual time in seconds. Original heater/drum/raw/manual alignment remains under Engineering Controls. Source timestamps stay immutable; alignment is a separate transformation.

Recorded absolute origins are compared when available. Naive timestamps require a confirmed profile metadata `recorded_timezone` (for example UTC); absent/unknown origins preserve existing numeric coordinates and produce a warning. No timezone is guessed. Cursor/event fields use seconds in the configuration; plots continue to show minutes.

**Plot Engineering Comparison** creates explicit derived aligned traces in the existing Comparison workspace; original channels remain unchanged. **Toggle Tolerance Envelope** shows/hides configured envelopes and breach highlights. Rules may combine absolute width, relative percentage and uncertainty, or supply finite ordered `times_s`, `lower`, `upper` arrays. Different native sample rates stay intact; comparison projections use supported analog interpolation/held states and preserve gaps.

Breach results include intervals/count, supported comparison duration, total breach duration, maximum deviation, defined percentage deviation and first/last breach. Crossings are calculated within supported segments. Zero-reference percentages are neutral/undefined, never divided by zero. KPI delta tables show Reference, Candidate, signed Δ and Δ%; optional Golden-versus-Candidate results remain separate.

New KPI deviation accents use absolute deviation ≤5%, >5%–10%, >10%, and neutral undefined. These are visual deviation indicators, not acceptance verdicts. Existing simulation match-percentage scoring and its established colors remain a separate metric.

## Generate Engineering Report | 2.3.0

Choose **Generate Engineering Report**, select PDF or Excel and save. It recomputes the current configured session in a background task; no wizard is required. Use Cancel Engineering Task to stop analysis/report creation. Cancellation and errors retain the previous complete output and valid workspace. Existing Export Report, raw/processed exports and full diagnostic workbook remain available.

PDF uses four main sections with readable continuation pages and traceability appendices:

1. Executive summary: identification, appliance/model/scenario/date/boundary metadata, primary KPIs, configured limits and Pass/Fail/Not Evaluated.
2. Phase breakdown: only observed configured phases, durations and supported water/energy/temperature/speed/actuator metrics.
3. Graphical evidence: vector plots, engineering units, selected channels, cursor markers, phase annotations, reference/candidate/Golden overlays, tolerance bands and breaches.
4. Anomaly/fault analysis: timestamps, supporting rule definitions, quality limitations and distinct evaluated/unevaluated outcomes.

Excel contains Executive Summary, Test Metadata, KPI Results, Phase Breakdown, Comparison Results, Tolerance Breaches, Fault & Anomaly Log, Channel Mapping and Calculation Definitions. Long metadata is split into numbered cells rather than truncated. PDFs embed full generation metadata in the first-page annotation, with readable metadata and formula appendices. Source file hashes are included when files exist; otherwise preserved channel-array hashes are labelled explicitly. Reports include app/profile/schema version, generation timestamp, alignment, processing/masks/normalization, mappings, calibration, tolerances and unavailable-data limitations.

For repeatability, save the workspace and engineering profile with the report. Engineering results are invalidated when source channels change; analyze again after edits. Source-only data in an unrecognized physical unit can still appear as measured graphical evidence, but does not gain an invented engineering KPI. All work remains local; no cloud service is required.


## Install, upgrade and uninstall on Windows | 2.3.2

Download **ApplianceSignalStudio-Setup-2.3.2.exe** from the official GitHub release. Close the app, run Setup and follow the wizard. The per-user installation includes Python and dependencies and does not request administrator rights. Windows 10/11 x64 is the supported target. An optional desktop shortcut and a Start menu shortcut launch the installed runtime directly. The installer is currently unsigned; Windows or your organization may require publisher approval. Do not disable company security controls.

Application files live under `%LOCALAPPDATA%\Programs\ApplianceSignalStudio\versions\<version>`. The installer checks that the copied runtime starts before registering the new version. Prior installed runtimes remain available for recovery; no earlier application is bundled inside the new installer. Existing settings/templates remain in `%APPDATA%\ApplianceSignalStudio`. Installed-app reports default to your Windows Documents folder under `SignalStudio_Output`; existing portable outputs stay in their original folders. An `ANALIZER_OUTPUT_DIR` override is retained.

Choose **About → Updates → Check for updates**. The installed app uses `installer-update.json` and downloads a complete Setup package. **Install update & restart** saves a recovery workspace, closes the app, verifies Setup again and restarts the new runtime. If Setup fails, the previous runtime is restarted. For an offline update, put the matching Setup EXE and `installer-update.json` in one folder and choose **Import offline update**. Portable EXE updates remain supported separately and cannot replace an installed runtime.

To upgrade manually, close the app and run the newer Setup. To uninstall, use **Windows Settings → Apps → Installed apps → Appliance Signal Studio → Uninstall**. Uninstall removes only tracked application files and shortcuts. It preserves settings, templates, reports, workspaces and unowned files; delete personal data separately only when you intend to. Keep saved workspaces and source recordings outside application-version folders.

## Reviewed recording identity and safe removal | 2.4.0

With more than one recording loaded, legends, Readout, hover details, cursor selectors and reports show a short unique recording alias beside each channel. Full original identities remain available in tooltips and evidence exports. The Readout caption identifies the active pane; selecting another pane changes the inspected channels without losing other panes' traces.

Each file retains its own Select All / Deselect All checkbox. When filtering, use the separately labelled filtered-channel actions to affect matching channels only; file-wide actions still mean the complete file. Counts disclose matching/total channels. Invalid regular expressions display an explanation and no matching channel results until corrected. File roots and Close Dataset remain available. Switch to ordinary search when regular expressions are unnecessary.

Close Dataset keeps original files. If derived channels depend on that dataset, review the affected counts and expandable channel list before confirming. **Channel → Undo Dataset Removal** restores the last unload and its stable data/plot/cursor identities. New work created after the unload remains. Undo is an in-memory recovery action, not a replacement for saving a workspace, and does not survive closing the application.

## Graph header, pane menu and precise cursors | 2.4.0

Use the single navigation set beside **Analysis / Comparison**. At narrow widths, open its overflow menu to reach remaining controls. Toolbar, Tools menu, pane menu and shortcuts share commands and mode state. **Zoom X** changes only time, **Zoom Y** only values and **Zoom XY** both; magnifiers and mouse gestures respect the selected mode. **Hand / Pan** drags the view; **Esc** returns to Hand/Pan. Reset View fits data; **Revert Zoom** restores the preceding view instead.

Right-click the pane to inspect Cursor, Hand/Pan, X/Y/XY zoom, Revert, comments/move comments, Copy Chart and export. Cycle snapping is unavailable until reviewed cycle boundaries exist; it does not guess appliance phases. Frequency analysis uses the supported FFT operation with explicit clock validation rather than a framework transform of every plot item.

**Lock Time Axes** immediately adopts the active pane's numeric bounds for compatible temporal panes and preserves them through zoom, pan, resize, themes, layout changes and restore. Disable it for independent windows. This does not align physical recording events or shift original timestamps. Frequency/histogram/sample domains stay separate.

Cursor A is cyan `#00D2FF`; Cursor B is orange `#FF9F1C`. Choose a lock channel to identify an actual source row, then drag or step samples. Even at equal timestamps with different values, marker, Readout, pinned card and exports refer to the same locked row. Other channels are sampled at that time according to their supported interpolation/state policy. Crossed cursor HUDs show positive spans; detailed signed differences remain available. Split views allocate usable drawing space and scroll when necessary, rather than crushing traces.

## Compact forms, unit definitions and processing requirements | 2.4.0

Simple forms show required fields and actions first. Expand **Help** for optional explanations; it is reachable by keyboard. Long selectors elide display text but preserve the full selected identity in tooltips and accessible descriptions. Larger mapping/TDMS tables remain resizable and scrollable.

**Define Local Unit** has separate Symbol, Reference Unit and Scale fields. One value in the new unit equals Scale values in the reference unit: for mW relative to W enter 0.001. This defines a conversion, not a sensor calibration. Custom properties use a key/value editor; **Advanced JSON Editor** remains available for nested expert editing. Invalid edits are retained for correction without changing the channel.

For signal processing, select one source channel and review its requirements before Apply. Spectral operations display sample rate, Nyquist frequency and valid filter range. Duplicates, irregular clocks and missing/masked support require explicit reviewed resampling or another suitable operation; changing cutoff alone cannot fix an irregular clock. Unknown physical units remain labelled unknown and cannot imply energy or other engineering quantities.

Long operations show file/stage progress and Cancel Operation. Cancellation takes effect at safe checkpoints; a compression/writer/native numerical step may finish first. Cancelled calculations are not added, and cancelled exports do not replace the previous complete output. Normal Save/Restore and quick exports run in workers. Once an atomic output commit has completed, the completed file is retained and reported accurately. **Open File / Open Folder** appears after a successful quick export.

## Engineering readiness and supported-time results | 2.4.0

1. Open **Engineering Setup**, select profile and run roles, then **Review Channel Mapping**.
2. Confirm the actual physical role and logger unit. Target/command speed differs from actual/feedback speed. Choose the correct source; ambiguous proposals do not become accepted actual-speed results. Pressure pulse time needs a verified calibration before becoming pressure.
3. Check **Reviewed Role / Unit** only after review. Confirmed mappings persist; changing a friendly display name alone is not calibration evidence. Unknown units, ambiguous mappings and unsupported conversions block affected conclusions with an actionable reason.
4. Configure phases, calibration, test metadata and acceptance limits from your test plan; no manufacturer codes or limits are invented.
5. Analyze Engineering Data and inspect Readiness, Source Review and Timing Quality before interpreting KPIs.

Timing results show recorded span, supported duration/coverage, duplicate and missing counts, the effective gap rule and its acquisition policy. The conservative fallback uses three times the median positive interval; confirm an explicit acquisition policy where appropriate. This is not a universal coverage acceptance threshold. Supported-time actuator/integration totals do not assert a complete-cycle total. Missing intervals never become known OFF time or zero energy. Duplicate and partial-coverage flags remain visible together.

Data Quality, Rule Evaluation and Appliance Events are separate. Sampling gaps do not prove a motor/appliance fault. Missing rule inputs remain Not Evaluated. A peak observed sample, elapsed-time quantity and formal acceptance need different adequacy checks. Filename load/program hints are not reviewed test metadata or evidence of compliance.

## Concise PDF and complete report evidence | 2.4.0

Choose **Generate Engineering Report**, review the explicit whole-recording/cursor/both scope and expected PDF length, then choose the output. The audited regression fixture produces a ten-page default summary across four main sections. Mandatory/primary results and configured acceptance results add readable continuation pages when needed. Event count alone does not expand that summary; an explicitly checked complete event appendix can add many pages. Summary tables identify any displayed subset and direct you to complete evidence. Use readable pagination rather than shrinking text to force exactly four pages.

The PDF explains readiness, usable results, blockers and next actions; reviewed source roles, timing coverage, plots, KPIs and grouped events follow. The grouped view reports counts, interval-union affected time, longest interval, first/last times and representative event IDs. Grouping never merges or deletes the original evidence.

For a PDF named `Test.pdf`, keep `Test.evidence.xlsx`, `Test.events.csv` and `Test.evidence.json` beside it. They share the report ID and preserve every original event/KPI, mappings, definitions, source fingerprints and full configuration. The complete workbook retains its nine sheets. Shareable PDF metadata uses basenames instead of absolute workstation paths; the local evidence package retains full provenance. All files are staged before publication, with previous outputs restored if bundle publication fails.

Whole Recording is the default engineering scope. Active Cursor Interval and Both recompute timing-dependent results and comparisons consistently for the selected interval; displayed A/B values preserve locked sample identity. Unavailable required results retain reasons and corrective actions. Never interpret a deviation color as an acceptance verdict without configured limits.

## Installed and standalone updates together | 2.4.0

Installed Setup, standalone EXE and standalone ZIP/folder builds share the same code, features, version and manual. About / Updates identifies the edition and actual settings/output locations. Matching feeds are `installer-update.json`, `update.json` and `zip-update.json` respectively. Offline import requires the matching manifest and payload; changing edition is a deliberate separate installation, not an update side effect.

Updates stage verified complete payloads, save separate recovery JSON/NPZ snapshots, and wait for the old application to close. A visible new application restores the recovery workspace and acknowledges its version and executable path. Failure keeps the previous runtime and valid recovery snapshot. Complete ZIP updates replace the executable and `_internal` together, retaining unrelated files and measurements. Installed late-startup failure restarts the prior runtime; the recovery log explains when rerunning its previous official Setup is necessary to restore installation shortcuts/registration fully.

**One-time older ZIP migration:** v2.3.2 and earlier folder builds predate the ZIP update feed. Download the full v2.4.0 ZIP once, extract it into a separate writable folder and launch its EXE; retain the old folder and existing outputs until verified. Subsequent folder updates use the new complete-runtime mechanism. Older installed/onefile builds can use their matching existing update routes or a manual official download.

User settings/templates and outputs stay outside runtime replacements. Standalone and installed copies may coexist; updating one does not delete another supported edition or its backup. Keep saved source data outside runtime-version folders and retain recovery copies until you choose to remove them. This unsigned release may still require your organization's normal publisher approval.

## Aligned stacked graphs and a simpler Data Portal | 2.4.1

Stacked panes align their actual graph drawing edges even when they have different numbers of independent Y-axes. Axis-label space is coordinated so the same time and cursor positions line up vertically. This corrects the drawing geometry without changing numerical time bounds, source timestamps, cursor samples or physical values. Use **Lock Time Axes** when panes should share a numerical time interval; equal drawing widths alone do not synchronize unlocked ranges. Independent value axes remain available.

**Data Portal** shows **Channel** and **Unit**. File headers keep their own selection checkboxes. Right-click a file header to select/deselect that complete file, select/deselect its filtered channels or **Close Dataset**. These actions affect the chosen file only. Filtering counts, removal confirmation and Undo Dataset Removal remain available. **Kind** metadata remains in **Properties**; the former Kind and File Actions columns and Show channel kind View toggle are no longer used.

Use the main **About** menu beside Tools for **User Manual** and **About / Updates**. The duplicate Tools → About version entry is removed; the searchable version manual, build/release/license details, installed/standalone updates and offline update import remain available through the main About menu.

## Quiet installed-app updates | 2.4.2

In an installed copy, open **About → About / Updates**, check/download the matching update and choose **Install Update & Restart**. The app saves an independent recovery workspace and closes. Its updater runs the complete verified Setup package without the normal Setup progress window, then opens the new workbench and restores that workspace. A successful new version/path and recovery acknowledgement are still required before success is recorded.

Only the in-app installed-update path changes: it uses Inno Setup **/VERYSILENT** rather than **/SILENT**, which still displayed a progress window. Runtime staging and health verification, installation logs, process/exit-code checks, previous-runtime retention and recovery stay enabled. A failed Setup or startup/restore still follows the existing recovery route; inspect the transaction's **RECOVERY.txt** and Setup log when troubleshooting. Complete installer registration/shortcut recovery after a late failure can require rerunning the previous official Setup.

**One-time transition:** the updater belongs to the version already running. An installed **v2.4.1 or earlier** copy still contains its older **/SILENT** launch logic, so installing v2.4.2 through that copy can show Setup progress once. After v2.4.2 is installed and launched, future installed-app updates use its quiet updater. Downloading the new payload cannot retroactively change the old application's updater before it runs.

Opening a Setup EXE manually remains interactive for first installation, repair or manual upgrade. The change does not suppress Windows security/publisher prompts or bypass organizational policy. Standalone EXE and ZIP updates keep their existing matching mechanisms; they do not launch installed Setup or change edition.

## Change Trace Color directly | 2.4.2

Select a channel and choose **Channel → Change Trace Color…**, or use **Change Trace Color…** in Properties. Properties starts folded; expand it through **Panels → Expand Properties** if needed. Right-click a Data Portal channel for the same action, or right-click a graph and choose the channel under **Change Trace Color**. If no portal channel is selected, the direct action can ask which active trace to change. Selecting multiple channels applies the chosen color to that explicit selection.

Choose a trace color and confirm. The trace, its legend swatch and relevant axis/readout colors update while preserving the current zoom, cursor positions/locks, view history and channel identities. Cancel leaves colors and the view unchanged. The choice is channel appearance metadata and survives the existing workspace/preset/export routes. This control edits trace colors; it does not change the plot background. Normal theme controls remain available.

## Compare any loaded data | 2.4.2

1. Choose **Compare Data…** in the main toolbar. The chooser lists channels grouped by their recording, with units and a search field.
2. If another recording is needed, choose **Open More Files…**. The normal importer and TDMS parameter review load it, then return to the chooser. This route imports data only; it does not automatically plot the new recording in Analysis or Comparison. Confirm the desired channels before adding them.
3. Check individual channels or that file's checkbox. Each file checkbox affects only that file, including its channels hidden by the chooser search. There is no global cross-file Select All. Selection counts disclose the scope.
4. Choose **Add to Comparison**. Existing Comparison traces remain, newly chosen channel IDs are added, and already-present IDs are not duplicated. Unchecking a channel in this chooser does not remove a trace already in Comparison; use its ordinary Data Portal visibility checkbox to hide it.

You can also right-click selected Data Portal channels and choose **Add Selected Channels to Comparison**, or right-click a file header and choose **Add This File to Comparison**. These shortcuts use the same additive plotting route. Existing Analysis plots and original samples stay intact. Compatible channels overlay with independent value axes; incompatible coordinate domains use separate panes. At most ten coordinate families can occupy the available panes; a selection needing more is rejected without changing existing plots. Native clocks, units and colors remain; the action does not resample, infer alignment, generate similarity percentages or invent engineering results.

For a configured reference/candidate/golden evaluation, keep using **Tools → Engineering Diagnostics → Engineering Setup**, **Analyze Engineering Data**, **Engineering Results** and **Plot Engineering Comparison**. The general Compare Data chooser is available for ordinary loaded data without requiring an appliance profile.

## Fullscreen only the selected graph | 2.4.2

Click the graph you want to inspect, then press **F11**, choose **View → Fullscreen Selected Graph**, or use the graph-header action. The chart context-menu action is **Full Screen Graph** and targets the graph you right-click. Only that pane expands into the fullscreen graph window; the complete multi-pane dashboard is not expanded.

The fullscreen window keeps zoom X/Y/XY, pan, reset, cursor locking and the other shared navigation actions, with overflow when needed. Mouse X/Y stays in its fixed strip outside the canvas. Cyan A/orange B cards show cursor positions and locked parameter values; a channel readout table shows live A/B values and statistics for this pane. Min, Max and Average follow the current Readout scope (**Cursor interval** or **Whole recording**); A/B values and Coverage retain the cursor interval. The same original samples, independent units, missing-data behavior and cursor locks remain active. Existing Lock Time Axes synchronization still applies when enabled.

Drag the divider between the graph and its readout area to give either more space. The initial readout size follows its visible contents so an empty table does not reserve a large blank area.

Choose **Exit Fullscreen**, press **F11** again or press **Esc** to return. The original graph returns to its place in the workspace and its deliberate zoom/cursor changes remain. The previous pane arrangement and main-window geometry are restored rather than replacing the workspace with a copy. Layout/data changes or workspace restore can leave fullscreen safely before replacing the affected pane. Outside fullscreen, Escape retains its normal Hand/Pan behavior.

## Expand and fold supporting panels | 2.4.2

New workspaces start with **Properties**, **Channel Math**, **Channel Table** and **Interval Measurements** folded. **Engineering Controls** and **Readout** remain available, with Engineering Controls the default tab in its existing dock group. Data Portal remains available. These defaults supersede the older all-panels-open default; they do not remove a feature or discard panel contents.

Use the compact **Panels** button in the main toolbar. A folded panel has an **Expand [panel name]** action; an open panel has **Fold [panel name]**. Checked actions indicate open panels. The existing View menu can also reopen panels. Expanding one panel does not silently fold another or clear values; positions/sizes and dock tabs are retained where possible.

Save a workspace to keep your chosen layout. Explicit restores respect the saved open/folded/docked state, including legacy workspaces without the new folding metadata. New-workspace defaults are not forced onto a saved session. **View → Show all panels** remains an explicit way to reopen panels when that is what you want. Folding is separate from selected-graph fullscreen and the older Focus Graph preference.

In **Readout**, select a channel row for its interval detail card. Scroll within the card to read longer statistics; the dock can keep its compact height while the complete details remain available.

## Find advanced graph and engineering tools | 2.4.2

The **More** button opens the same menu as **Tools**. For channel mapping, legend/display options, playback or layout tools, choose **Tools → Plot Appearance / Layout**. For recording controls, measurements/data quality, reference settings and appliance analysis/reporting, choose **Tools → Engineering Diagnostics**. General Compare Data remains directly available in the main toolbar.

Coordinate imports and presets are under **Import / Export Utilities**; filters and previews under **Signal Processing / Derived Channels**; complete data/presentation exports under **Export Utilities**; plugins under **Presets / Extensions**. The main **About** menu retains User Manual and About / Updates. These names describe the visible compact menus; old manuals retain the labels used by their own versions.

## Remembered open and save folders | 2.4.2

Open and save dialogs remember the folder you last chose for that purpose, including recordings, workspace restore/save, profiles, presets, reports/exports, engineering source/reference files, extensions and offline update manifests. These choices survive closing the app and replacing its runtime during an update. Different purposes keep their own folders; for example, choosing a recording folder does not replace a previously chosen report destination.

On the first save for a purpose, the configured output folder remains the starting location. After you choose another destination, that purpose starts there next time and keeps its suggested filename. An open dialog without its own remembered folder uses its supplied starting location, then the latest selected folder if no starting location is supplied. If a remembered folder has been removed, the dialog uses its nearest existing parent. Cancelling a dialog leaves the remembered choices unchanged.

Only folder paths are stored in **dialog-history.json** under the per-user settings folder shown in **About → About / Updates**; selected filenames and measurement contents are not stored there. The normal Windows location is **%APPDATA%/ApplianceSignalStudio**. A configured settings-directory override applies as usual. Nothing is opened, saved or exported solely because a folder is remembered.

## Fullscreen the current split workspace | 2.4.3

1. Activate **Analysis** or **Comparison** and choose the split layout you want to inspect.
2. Press **F11**, choose **View → Fullscreen Workspace**, or use the graph-header fullscreen control.
3. All visible graphs in that workspace move into the fullscreen view together. Existing traces, units, cursor locks and split positions remain part of the same workspace.
4. Click a graph or use the graph selector to make its live values active. Shared zoom X/Y/XY, pan, reset and cursor controls remain available. **Lock Time Axes** continues synchronizing compatible time plots; independent frequency/sample panes keep their own coordinates.
5. Press **F11** again, **Esc**, or **Exit Fullscreen** to return. The original layout and main-window arrangement are restored while deliberate graph navigation is retained.

The readout shows the active graph's A/B values and statistics while the other graphs remain visible. Drag its divider to share space with the graphs. Very large stacked layouts retain scrolling so axes and values remain readable. **Shift+F11 / Fullscreen Selected Graph** remains available when you deliberately want only one graph enlarged; the graph-header fullscreen button's arrow also offers this option. Fullscreen does not duplicate or resample source channels.

## Stable mouse hover while navigating | 2.4.3

The fullscreen Mouse X/Y readout reserves a stable two-line area outside the canvas. Moving between its placeholder and a channel/sample value does not move the top edge of the graph. The area follows font/display sizing rather than changing height with each pointer value. This fixes the visible vertical bounce demonstrated during hover with Zoom X selected; it does not change time ranges or recorded measurements.

Choose **Zoom X**, **Zoom Y**, **Zoom XY** or **Hand / Pan** before using gestures. Mouse hover is an inspection aid, not a measurement cursor. Cyan A and orange B remain the report's measurement cursors, including any explicit sample locks.

## Compare Two Signals | 2.4.3

Use this workflow to compare one chosen parameter from each of two recordings without configuring an appliance profile. Examples include drum speed from two appliance tests, temperatures from two runs, or reviewed valve-state signals.

1. Open both raw recordings and complete any required TDMS parameter review.
2. Select the two channel rows in **Data Portal**, one from each recording. Choose parameters with the physical meaning and compatible units you intend to compare. The first channel in portal order is Reference; the second is Candidate. Source-qualified names identify both in the results.
3. Click **Compare Two Signals** in the main toolbar, or choose it under **Tools → Engineering Diagnostics**. Exactly two selected rows compare directly. If fewer than two rows are selected and exactly two channels are plotted, those form the pair. Otherwise a compact Reference/Candidate chooser asks you to pick the pair; more than two selected channels never cause an arbitrary pair to be chosen.
4. The comparison uses **elapsed time from each recording's start**, as requested. A channel that starts later in its recording keeps that delay; its first sample is not silently treated as the recording start. This alignment is a separate report calculation and leaves original timestamps and plots unchanged.
5. Read the concise results, then choose **Open Report**, **Open Workbook** or **Open Folder**. A uniquely named PDF, matching Excel workbook and evidence JSON are saved together in the report output folder or the remembered destination for this comparison-report purpose.

The report identifies Reference, Candidate, units, time scope and supported comparison coverage. It explains signed Candidate−Reference differences alongside magnitude/error statistics, the largest observed difference and its time, and supported activity/timing differences where applicable. Difference statistics use supported elapsed time rather than giving more weight to a logger merely because it recorded more samples. The complete workbook/evidence keeps the detailed difference intervals and events so a short PDF summary does not discard the supporting records.

Difference duration excludes floating-point interpolation or unit-conversion roundoff. This calculation resolution is separate from measurement accuracy and engineering acceptance limits; raw differences and full error statistics remain in the evidence.

Mismatched sampling rates are compared only on supported overlapping time. Missing values, masks and acquisition gaps remain limitations; they are not filled with known zero or extrapolated beyond a recording. Duplicate timestamps and the effective timing policy remain disclosed. Incompatible or unverified physical units, insufficient overlap or unsupported coordinates produce an explanation rather than an invented physical result.

Activity depends on the reviewed signal interpretation. A confirmed actuator uses ON/OFF state behavior; arbitrary numeric parameters are not automatically converted to actuator states. For declared rotation-unit signals, the report describes supported nonzero-signal time and numeric zero/nonzero transitions or sign changes. Negative values can be command readings, feedback or unreviewed protocol codes; a numeric sign change alone does not prove mechanical reversal. Transitions require known contiguous evidence. These observations do not establish a manufacturer operating threshold or a formal appliance acceptance decision. Configure engineering limits separately when a test plan requires Pass/Fail.

Source data, current plots and saved channel configurations remain intact. Cancellation or failure must retain the previous complete outputs; the PDF/workbook/JSON bundle is staged before publication. Optional report notes are described below and are not a mandatory wizard step.

## Detailed comparison reports | 2.4.3

For an existing multi-channel **Comparison** workspace, keep using **Export Report** or Ctrl+P. PDF uses readable pagination across four main sections: report/source scope, plotted evidence, channel/cursor results, and quality/provenance with reviewed notes. All selected visible panes and their channel evidence remain represented; additional channels continue onto readable pages rather than a single increasingly tall figure.

A Comparison PDF also saves its matching Excel workbook and evidence JSON atomically. For a PDF named `Comparison.pdf`, keep `Comparison.xlsx` and `Comparison.evidence.json` beside it when sharing the complete report evidence. Cancellation or failed publication preserves the previous complete bundle.

Check A/B positions, sample locks and the selected statistics scope before exporting. Tables identify channel and recording, units, cursor values and their signed difference, interval/statistical scope, and supported coverage. Plot traces, independent axes and valid percentage-match accents remain associated with their original channels. The configured scope and available data determine the results; a familiar channel name does not establish a cross-file reference/candidate pairing.

Comparison **Excel** retains active-interval samples and cursor summaries and adds source, quality, report-detail, view and processing/provenance evidence. An explicit two-signal comparison includes its paired metrics, detailed difference intervals and events. **PNG** remains a high-resolution graph snapshot; **CSV** retains active-interval sample exports. Use the workbook or JSON when further calculations and complete comparison evidence are needed.

General channel plots and a configured engineering evaluation remain distinct. Ordinary comparison does not invent appliance phase meanings, calibration curves, tolerance bands or engineering acceptance limits. Source fingerprints identify their method: a hash of an available source file is distinguished from a preserved loaded-data fingerprint when that file is unavailable.

## Report Details & Conclusions | 2.4.3

Open **Tools / More → Export Utilities → Report Details & Conclusions…** to add optional report information. The same action is available under **Engineering Diagnostics**, and the engineering report dialog provides an optional button for these shared details.

- **Report title**, **Prepared by** and **Reviewed by** identify the document and people supplied by the user.
- **Test conditions** records the context needed to interpret the two runs.
- **Observations** records what you reviewed in the evidence.
- **Conclusions** and **Recommended actions** support final report preparation.

Choose Save to apply the notes to both comparison and engineering reports, or Cancel to retain the previous details. Blank entries remain unprovided rather than fabricated. Save the workspace to retain these details for a later session or update recovery. Existing advanced/custom engineering metadata remains supported.

These are user-provided notes. Entering a reviewer name does not digitally sign the report, and a written conclusion does not change calculated results, configured tolerances, mappings, calibration or formal Pass/Fail status. Reports label the evidence and limitations independently. Long notes continue onto readable pages as needed.

## Complete engineering comparison evidence | 2.4.3

**Generate Engineering Report** retains its explicit Whole Recording / Active Cursor Interval / Both scope and four main sections. Comparison results can continue onto additional pages so all comparison rows are available instead of only the first few. Cursor evidence identifies the source and run, including Reference/Candidate counterparts and available selected-channel values. User-provided report observations, conclusions, conditions and actions are included with the evidence.

Review the page estimate after choosing scope and optional notes. Readable pagination may add pages for comparison results, cursor evidence or long reviewed text; the report is not forced into exactly four pages. The established Analysis regression fixture remains the baseline for a concise default summary, rather than a universal page count for every data combination.

The complete companion workbook and JSON retain the detailed results, source fingerprints, mappings, quality/coverage, definitions and configuration; the event CSV retains every original event. Data-quality gaps remain distinct from demonstrated appliance faults. Unconfigured or unsupported results retain their reasons and next actions. Manual notes and deviation colours do not invent acceptance limits or turn missing evidence into a pass.

## Program starts and shared time inspection | 2.5.0

Open **Align Program Starts** and choose each recording. Enter the original source
time in minutes for the actual program start, or activate a graph for that
recording and use **Use Cursor A**. Describe the recorded start signal, reviewed
rule or observation establishing the point, then Apply. Every time-based channel
in that recording receives the same physical offset. Time zero is program start;
pre-program data stays at negative time. Original timestamps, samples and source
tables remain available. Save the workspace to retain the confirmed origin.

The app does not assume that the first recorded sample, first nonzero valve or
motor movement establishes program start. If the evidence is unclear, obtain a
reviewed start point before comparing. Numeric comparison and default engineering
comparison require confirmed origins; advanced engineering anchor overrides must
be selected explicitly. Ordinary plots can still inspect original recording
coordinates before confirmation; they are not evidence of program alignment.

A/B is one shared pair across compatible time graphs. Shorter channels read
Unknown outside their sample range and cannot pull the pair back onto their
clocks. Panning/zooming does not move the pair. Time axes belonging to one
recording stay linked even if the general time lock is off. Readout combines
compatible time graphs; frequency and sample-domain graphs retain their own
coordinates. Hover marks each available trace at its nearest actual sample, on
its own value axis. The mouse-readout tooltip retains the complete sample values.

When restoring an older workspace or showing hidden graphs, compatible time
graphs adopt the active time graph's A/B positions and sample locks. Conflicting
independent pairs from older versions are not retained as separate cursors.

## Freely arranged graphs | 2.5.0

**Add Graph** creates an empty active graph. Choose its channels using Data Portal.
Right-click a graph and open **Arrange Graphs** to move it up/down, change its
relative row height or remove it. Removing a graph retains its source channels.
Order, channel bindings and row proportions persist with the workspace. Existing
fixed layouts remain available. A workspace supports up to 32 retained graphs.

For numerical comparison of three or more signals, select their rows and choose
**Compare Signals**, then review the reference and checked candidates. For two
signals in one recording, use **Compare more signals** in the source chooser.
Unknown units or incompatible interpretations remain explicit blockers for each
pair rather than disappearing. Confirmed actuator channels receive pairwise ON
overlap using supported time only; unknown samples and gaps are excluded.
