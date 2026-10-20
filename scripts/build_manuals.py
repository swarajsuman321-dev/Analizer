"""Generate complete, version-filtered offline manuals from reviewed feature topics."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
NOTES={'2.4.0':'Approved audit improvements: exact time locking and cursor identity, graph-header navigation, readable splits, safer dataset handling, reviewed engineering readiness and ten-page four-section report summaries with complete evidence. Installed, standalone EXE and standalone ZIP updates retain matching packaging and verify restored startup.',
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
                    body='\nChoose Generate Engineering Report, review Whole Recording / Active Cursor Interval / Both scope and expected pages, then Choose Output and Generate. The default PDF has ten readable pages across four sections: readiness/source quality; phase/graph evidence; results/comparison; events/conclusions/traceability. It groups repeated events and shows representative evidence. Every original event, KPI, mapping and configuration remains in adjacent .evidence.xlsx, .events.csv and .evidence.json files with a shared report ID. An optional full-event PDF appendix adds pages only when explicitly checked. Raw JSON is kept in companion evidence rather than filling the summary.\n\nProgress and safe cancellation are available. Keep all companion files together. Readiness distinguishes missing source, unreviewed mapping, unknown units, inadequate timing support, unsupported phases and absent acceptance limits. Unknown evidence never becomes a Pass. Whole-run and cursor results are scoped consistently; cursor positions and reviewed source roles appear when applicable.\n\n'
                if title=='Install, upgrade and uninstall on Windows':
                    body=body.replace('Setup-2.3.2.exe',f'Setup-{version}.exe').replace('checks that the copied runtime starts before registering','stages and checks the complete runtime before changing the installation, then verifies')
                if title=='Removing recordings and clearing the workspace':
                    body='\nClose Dataset unloads only that recording plus its dependent derived channels, never the source disk file. When derived work is affected, review counts and expanded channel names before confirming. Channel → Undo Dataset Removal (Ctrl+Alt+Z) restores the last removal, stable IDs, dependencies, plot bindings and cursor locks. Newer channels and source metadata remain intact. Clear Workspace confirms the entire unload and can also be undone until the next removal or an explicit different-workspace restore. Save important work before closing the app.\n\n'
            text+=f'## {title}\n' +body.replace('{{DEFAULT_VIEW}}',default)
        (ROOT/f'manuals/v{version}.md').write_text(text,encoding='utf-8')


if __name__=='__main__':
    import sys
    generate(sys.argv[1:] or None)
