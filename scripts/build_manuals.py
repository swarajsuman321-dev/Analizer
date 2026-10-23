"""Generate complete, version-filtered offline manuals from reviewed feature topics."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
NOTES={'2.4.1':'Stacked graph drawing edges align across different value-axis counts without changing numerical time ranges. Data Portal shows Channel and Unit only; per-file selection, filtered selection and Close Dataset remain in the file context menu. Kind metadata remains in Properties. The main About menu retains User Manual and About / Updates without a duplicate Tools entry. Installed, standalone EXE and standalone ZIP builds retain matching update support.',
       '2.4.0':'Approved audit improvements: exact time locking and cursor identity, graph-header navigation, readable splits, safer dataset handling, reviewed engineering readiness and concise four-section report summaries with complete evidence. The audited fixture produces ten pages; required results can add readable continuation pages. Installed, standalone EXE and standalone ZIP updates retain matching packaging and verify restored startup.',
       '2.1.0':'Streamlined standalone analysis with retained engineering, processing and reporting tools.',
       '2.1.1':'Unit detection improvements, visible navigation shortcuts, cursor locks and duplicate-free realignment.',
       '2.1.2':'Pinned lock values, extended readouts/statistics scope and quick event notes.',
       '2.1.3':'Rectangle zoom respects X-only, Y-only and XY modes.',
       '2.1.4':'Contextual actuator interpretation, ON time/duty, original readings and application icons.',
       '2.1.5':'Verified GitHub release updates, recovery restart and offline version manuals.',
       '2.1.6':'TDMS recording support and live mouse X/Y hover.',
       '2.1.7':'Top-toolbar Info/manual access, complete searchable version manuals, and every View panel enabled by default.',
       '2.1.8':'Windows system-proxy fallback, verified offline update import and actionable connection guidance.',
       '2.1.9':'Complete recording removal, reviewed TDMS parameter templates, persistent output folders, and real-file import corrections.',
       '2.2.0':'Per-file channel controls, active-graph navigation, separate About and User Manual windows, legacy configuration migration and verified installation cleanup.',
       '2.2.1':'Shared TDMS parameter review and saved templates for Engineering Controls and Open, plus independent frozen-runtime restart after updates.',
       '2.2.2':'Header Zoom X/Y/XY, Pan, Reset View and cursor locking; fixed mouse X/Y readout outside the plot canvas.',
       '2.3.2':'Per-user Windows installer with bundled runtime, Start menu and optional desktop shortcuts, separate verified Setup updates, runtime health checks and data-preserving uninstall.',
       '2.3.1':'Repaint rendered legend labels immediately on theme changes and prevent report table text clipping; includes all v2.3.0 engineering and compact-workbench features.',
       '2.3.0':'Compact workbench controls, configurable appliance profiles and KPIs, run comparisons with tolerance envelopes, and traceable engineering PDF/Excel reports.',
       '2.2.3':'Quick zoom controls beside Analysis/Comparison, distinct stable channel colors and visible legends, and About menu access to User Manual and Updates.'}


def generate(versions=None):
    source=(ROOT/'manuals/feature-guide.md').read_text(encoding='utf-8')
    parts=re.split(r'^## (.+) \| (\d+\.\d+\.\d+)\n',source,flags=re.M)
    topics=[(parts[i],tuple(map(int,parts[i+1].split('.'))),parts[i+2]) for i in range(1,len(parts),3)]
    for version,note in NOTES.items():
        if versions and version not in versions:continue
        number=tuple(map(int,version.split('.')))
        default=('All View panels and Show channel kind are enabled in a new workspace. Data Portal/Engineering Controls, Properties/Channel Math and the bottom measurement/table panels share dock tabs.' if number>=(2,1,7) else 'New workspaces start with Data Portal and Readout visible; advanced panels can be opened through View.')
        if number>=(2,4,1):
            default='All View panels are enabled in a new workspace. Data Portal/Engineering Controls, Properties/Channel Math and the bottom measurement/table panels share dock tabs. Engineering Controls remains the default tab in its existing dock group.'
        text=f'# Appliance Signal Studio — {version}\n\nComplete feature reference for this version. Use the matching version when following controls; later releases can change their placement.\n\n## Changes in this version\n\n{note}\n\n'
        for title,introduced,body in topics:
            if introduced>number:continue
            if number>=(2,2,0):
                body=body.replace('The master checkbox selects/deselects all channels, including ones hidden by the filter.','Each file header selects/deselects only that file’s channels, including ones hidden by the filter. There is no global Select All checkbox.')
                body=body.replace('Open **Info**,','Open **About / Updates**,').replace('**Info & manual →','**About / Updates →')
                body=body.replace('under the output folder','under the per-user settings folder')
                if title=='Info toolbar, version manuals and search':
                    body='\nChoose **User Manual** in the top toolbar or press **F1** for the separate nonmodal, searchable documentation window. Choose **About / Updates** for the modal version, build date, release notes, changelog, license and updater window. Analysis and Comparison remain the only graph tabs. The manual version selector, topics and Find Next remain available.\n\nAll View panels are enabled initially; Engineering Controls is the selected tab in its existing dock group. Explicit workspace restores retain their layout.\n\n'
                if title=='Output folder and stored files':
                    body=body.replace('It uses **reports**, **workspaces**, **templates**, **diagnostics** and **presets** subfolders.','Reports, workspaces and diagnostics use this output directory. Templates and presets use the per-user settings directory in %APPDATA%/ApplianceSignalStudio.').replace('**Info & manual**','**About / Updates**')
                body=body.replace('The previous EXE is retained as a backup;','The previous EXE is retained until a successful new startup/recovery restore, then removed by verified lifecycle cleanup;')
                body=body.replace('| Shortcut reference | F1 |','| User Manual and shortcut guide | F1 |')
            if number>=(2,2,2):
                if title=='File isolation and graph navigation':
                    body=re.sub(r"The active graph's top-right toolbar[^\n]+", "The upper application toolbar offers Zoom X, Zoom Y, Zoom XY, Pan, Zoom In, Zoom Out, Reset View, Lock Time Axes and Lock Cursors. It sits above graph tabs and controls the active graph. Mode buttons show the current selection; shortcuts use the same mode state. With Lock Time Axes enabled, compatible time viewports share X navigation; zoom buttons scale each independent value axis once. Reset View fits the synchronized group to its combined data extent. Disable Lock Time Axes to navigate the active plot independently. Time and frequency/sample coordinates remain separate.", body)
                if title=='Mouse X/Y hover':
                    body=body.replace('compact readout','fixed readout strip above the graph')
                body=body.replace('**Reset zoom / Fit**','**Reset View**')
            if number>=(2,2,3):
                body=body.replace('**User Manual** in the top toolbar','**About → User Manual** in the top menu').replace('**About / Updates**','**About → Updates**')
            if number>=(2,3,0):
                if title=='Quick zoom beside Analysis and Comparison':body='\nNavigation uses a single primary control set in the top application toolbar. Duplicate quick controls beside graph tabs were removed with user approval. Zoom In/Out, Reset and Pan have accessible icons; X/Y/XY retain text and shortcuts.\n\n'
                body=body.replace('The unused top-right space on the same row as the **Analysis / Comparison** tabs now provides','The top toolbar provides')
            if number>=(2,4,0):
                body=body.replace('The previous EXE is retained until a successful new startup/recovery restore, then removed by verified lifecycle cleanup;', 'The previous runtime is retained for recovery after verified new startup;')
                body=body.replace('**About → Updates**','**About → About / Updates**')
                if title in ('File isolation and graph navigation','Quick zoom beside Analysis and Comparison','Upper navigation toolbar and clear hover view'):
                    body='\nOne navigation toolbar sits inside the graph header beside Analysis and Comparison. Zoom X/Y/XY, Hand/Pan, magnifiers, Reset View, Lock Time Axes and Lock Cursors share actions with menus/shortcuts. Narrow headers use accessible overflow. Lock Time Axes adopts the active numerical interval immediately and keeps compatible temporal panes at identical bounds; frequency/sample panes remain independent. The fixed Mouse X/Y strip stays outside the canvas.\n\n'
                    if title=='Upper navigation toolbar and clear hover view':title='Graph-header navigation and clear hover view'
                if title=='Properties and channel metadata':
                    body='\nSelect one channel. Edit name, declared unit, group, interpretation and warning/fault limits, then Apply Properties and Limits. Custom metadata uses a structured key/value table; nested values may use JSON. Advanced JSON Editor remains available as an explicit toggle. Invalid JSON is preserved for correction and cannot silently replace metadata. Declaring a source unit does not rescale or calibrate raw samples.\n\n'
                if title=='Updates and recovery':
                    body='\nOpen About → About / Updates, choose Check for Updates, Download, then Install Update & Restart. Installed copies use complete Setup; standalone EXEs use EXE replacement; standalone ZIP/folder copies use complete-folder staging, including _internal. Each verifies official metadata, size and SHA-256. Recovery JSON and arrays are independently copied per attempt. A visible new application must restore that recovery and acknowledge its version/path before update success is recorded. Failed startup/restore restarts the retained previous runtime. Backups are kept; source files, outputs and settings are preserved. Folder/EXE/Setup updates cannot silently change edition.\n\n'
                if title=='Generate Engineering Report':
                    body='\nChoose Generate Engineering Report, review Whole Recording / Active Cursor Interval / Both scope and expected pages, then Choose Output and Generate. The PDF starts with a ten-page presentation plan across four sections: readiness/source quality; phase/graph evidence; results/comparison; events/conclusions/traceability. Mandatory/primary results and configured acceptance results add readable continuation pages when needed. It groups repeated events and shows representative evidence; event count alone does not expand the default summary. Every original event, KPI, mapping and configuration remains in adjacent .evidence.xlsx, .events.csv and .evidence.json files with a shared report ID. An optional full-event PDF appendix grows with event count only when explicitly checked. For Excel output, the selected .xlsx file is the complete workbook, with adjacent .events.csv and .evidence.json. Raw JSON stays in companion evidence rather than filling the summary.\n\nProgress and safe cancellation are available. Keep all companion files together. Readiness distinguishes missing source, unreviewed mapping, unknown units, inadequate timing support, unsupported phases and absent acceptance limits. Unknown evidence never becomes a Pass. Whole-run and cursor results are scoped consistently; cursor positions and reviewed source roles appear when applicable.\n\n'
                if title=='Output folder and stored files':
                    body='\nInstalled copies default to the Windows Documents known folder under **SignalStudio_Output**. Standalone copies create **SignalStudio_Output** beside the executable; source launches use the checkout. If that location is read-only, a Documents fallback is used. An explicit **ANALIZER_OUTPUT_DIR** override takes precedence. Reports, saved workspaces and diagnostics use this output directory. Templates and presets use the per-user settings folder, normally **%APPDATA%/ApplianceSignalStudio**. **About → About / Updates** shows the actual locations and an **Open output folder** button. Existing portable output is not silently moved.\n\nReport/export and workspace/preset save dialogs start in these folders. You can deliberately choose a different destination. Nothing is exported without a save action. Keep workspace JSON and its named NPZ companion together. Reports and templates survive clearing the workspace and updating the runtime. Keep personal recordings and generated output outside Git and runtime-version folders.\n\n'
                if title=='Updates on managed networks and offline import':
                    body='\nIf an update check fails with a DNS/proxy error such as getaddrinfo failed, inspect the connection and your organization\'s GitHub access policy. The updater supports the Windows system proxy, including PAC/WPAD and signed-in proxy credentials, while preserving HTTPS verification and company policies. It cannot override a blocked domain or a network outage.\n\nFor an approved offline update, put the matching official manifest and payload together in one folder: **update.json + ApplianceSignalStudio.exe** for standalone EXE; **zip-update.json + the complete portable ZIP** for standalone folder; **installer-update.json + the versioned Setup EXE** for installed copies. Choose **About → About / Updates → Import offline update…** and select that manifest. Official repository URL, edition, version, file size and SHA-256 are validated. An update cannot silently change edition; install another edition separately if desired. Preserve recovery snapshots and backups until you choose to remove them. Installed recovery can require rerunning the previous official Setup to restore shortcuts/registration fully.\n\n'
                if title=='Legacy configurations and installation lifecycle':
                    # Preserve legacy schema guidance; replace obsolete cleanup promises.
                    body=body.split('After a normal packaged Windows startup')[0]
                    body+='Installed runtime removal belongs to Setup/uninstall. Source launches and self-tests do not clean installed binaries. Discovery and settings migration do not authorize deleting another installed/standalone edition, its runtime or its recovery backup. Migration retains conflicting settings under legacy-imports and records its result.\n\nUpdate transactions retain the previous runtime and independent recovery JSON/NPZ after successful startup as well as failure. Retain these until you deliberately remove them. A failed installed startup restarts the previous runtime; restoring Setup registration and shortcuts fully can require rerunning its previous official Setup. See the transaction\'s RECOVERY.txt for recovery instructions. User settings, templates, source recordings, workspaces and outputs remain outside runtime replacement/uninstall ownership.\n\n'
                if title=='Compact controls and workspace focus':
                    body=body.replace('The **top application toolbar** is the only primary navigation control set.', 'The **graph-header toolbar beside Analysis / Comparison** is the only primary navigation control set.')
                    body=body.replace('Duplicate graph-tab quick controls were removed with approval; functions and shortcuts remain.', 'Duplicated navigation widgets in the global toolbar were removed with approval; functions, shared actions and shortcuts remain.')
                    body=body.replace('native 100%, 125% and 150% scaling checks are part of release validation.', 'physical Windows 100%, 125%, 150% and 200% scaling, multi-monitor, keyboard-only and screen-reader checks remain human acceptance checks until recorded in release evidence. Automated Qt checks at simulated 100%, 150% and 200% scaling do not certify those scenarios.')
                if title=='Install, upgrade and uninstall on Windows':
                    body=body.replace('Setup-2.3.2.exe',f'Setup-{version}.exe').replace('checks that the copied runtime starts before registering','stages and checks the complete runtime before changing the installation, then verifies')
                    body=body.replace('**About → Updates → Check for updates**', '**About → About / Updates → Check for updates**')
                if title=='Removing recordings and clearing the workspace':
                    body='\nClose Dataset unloads only that recording plus its dependent derived channels, never the source disk file. When derived work is affected, review counts and expanded channel names before confirming. Channel → Undo Dataset Removal (Ctrl+Alt+Z) restores the last removal, stable IDs, dependencies, plot bindings and cursor locks. Newer channels and source metadata remain intact. Clear Workspace confirms the entire unload and can also be undone until the next removal or an explicit different-workspace restore. Save important work before closing the app.\n\n'
            if number>=(2,4,1):
                if title=='View menu and panel layout':
                    body=re.sub(r'^\| Show channel kind \|[^\n]*\n','',body,flags=re.M)
                if title=='Data Portal selection and visibility':
                    body='\nData Portal has two columns: **Channel** and **Unit**. Each channel checkbox shows or hides its trace immediately. Each file header checkbox selects/deselects only that file, including channels hidden by a filter. There is no global cross-file Select All. Right-click a file header for file-wide selection, separately labelled filtered-channel selection and **Close Dataset**. Matching/total counts disclose the affected scope. Channel kind remains available in **Properties**; no Kind or File Actions column occupies the tree.\n\nA selected channel row identifies the channel for Properties, math and channel actions; selection and visibility serve different purposes. Deselecting all channels leaves a clean empty plot. Type a name, unit, source or metadata term to filter. Enable Regex for regular expressions; an invalid expression displays an explanation and no matching channel results until corrected. File roots and their context menus remain reachable. Clear the search to see all channels. Dataset/group nodes organize channels and are not extra traces.\n\n'
                if title=='Properties and channel metadata':
                    body+='**Kind** remains available here for Analog/Discrete metadata; removing its Data Portal column does not remove the channel metadata or its processing behavior. Value interpretation remains a separate choice for numeric values versus actuator ON/OFF states.\n\n'
                if title=='Removing recordings and clearing the workspace':
                    body='\nRight-click the relevant file header in **Data Portal** and choose **Close Dataset**. '+body.lstrip()
                if title=='Reviewed recording identity and safe removal':
                    body=body.replace('When filtering, use the separately labelled filtered-channel actions to affect matching channels only;', 'Right-click that file header for Close Dataset and separately labelled filtered-channel selection actions. When filtering, those actions affect matching channels only;')
                body=body.replace('**Close Dataset** beside each file', '**Close Dataset** in each file header\'s context menu')
                body=body.replace('**Tools → About version**', '**About → About / Updates**')
                if title=='Installed and standalone updates together':
                    body=body.replace('Download the full v2.4.0 ZIP once', f'Download the full v{version} ZIP once')
            text+=f'## {title}\n' +body.replace('{{DEFAULT_VIEW}}',default)
        (ROOT/f'manuals/v{version}.md').write_text(text,encoding='utf-8')


if __name__=='__main__':
    import sys
    generate(sys.argv[1:] or None)
