# Versioned manual source

Each topic records the first version that supports it. Regenerate the bundled
manuals with `python scripts/build_manuals.py` after changing this source.

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

Tools → Plot retains **Zoom Time Axis**, **Zoom Value Axes** and **Zoom Both Axes** with Ctrl+1/2/3; Pan is Ctrl+4, Reset is Ctrl+0/R. The floating HUD shows absolute |ΔY| and nonnegative ΔX even when A crosses B; signed B−A values remain available in the detailed table and export. Cursor A stays cyan and B orange.

## Separate About and User Manual windows | 2.2.0

**About / Updates** opens a modal window with version, build date, release notes, changelog, license information and update/offline-import controls. The project currently declares no repository distribution license; the window reports that fact and identifies third-party licenses without inventing a grant.

**User Manual** (or **F1**) opens a separate nonmodal documentation window. Choose a version, jump to a topic, or search for text/Find Next. You can leave it open while working on plots. Calculation tutorials are under Formula Channels, Moving Average, Resampling, FFT and the other processing topics. Cursor locking/stepping and keyboard navigation are documented in their dedicated topics. About does not contain a second embedded copy of the manual.

## Legacy configurations and installation lifecycle | 2.2.0

The app still reads schema-1 JSON/NPZ workspaces, version-2/3 channel presets and unversioned channel maps. It also adapts known JSON wrappers, XML presets (`signals/channel` elements with named attributes), XML with an embedded `json` element, INI sections `channel:Name` / `signal:Name` plus `options`, and INI workspace JSON under `[workspace] payload`. Original files and unknown metadata are preserved. Unsupported future schemas or unrecognized structures produce an error before modifying the workspace; arbitrary third-party XML/INI cannot be reconstructed without its schema.

Settings, reviewed TDMS templates, presets and extensions now use `%APPDATA%/ApplianceSignalStudio` (a per-user config directory on other platforms). Reports and saved workspaces keep their existing output locations. Earlier portable templates/presets/plugin settings are copied and checksum-verified before cleanup. Name conflicts are retained under `legacy-imports`, never overwritten. Migration reports remain in the settings folder.

After a normal packaged Windows startup and successful recovery restore, the app discovers its exact product registry entries and previously registered installation paths. It removes obsolete executable files only after checking the product/version resources or a stored file inventory. Unchanged dependency files are removed only when a prior ownership/hash inventory exists; directories are removed only when empty. The running EXE, user data and modified/unrecognized files are retained. Older portable libraries without an inventory cannot safely be attributed to the app and are retained. Permission or migration failures leave cleanup pending; there is no elevation or execution of registry uninstall commands. The process records removed/retained paths in `lifecycle.json`.

The updater retains a previous EXE while replacement is in progress. That obsolete backup is eligible for permanent removal only after the new application successfully initializes/restores. If recovery fails, it is retained. Self-tests and source launches never delete installed binaries.
