"""Generate complete, version-filtered offline manuals from reviewed feature topics."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
NOTES={'2.1.0':'Streamlined standalone analysis with retained engineering, processing and reporting tools.',
       '2.1.1':'Unit detection improvements, visible navigation shortcuts, cursor locks and duplicate-free realignment.',
       '2.1.2':'Pinned lock values, extended readouts/statistics scope and quick event notes.',
       '2.1.3':'Rectangle zoom respects X-only, Y-only and XY modes.',
       '2.1.4':'Contextual actuator interpretation, ON time/duty, original readings and application icons.',
       '2.1.5':'Verified GitHub release updates, recovery restart and offline version manuals.',
       '2.1.6':'TDMS recording support and live mouse X/Y hover.',
       '2.1.7':'Top-toolbar Info/manual access, complete searchable version manuals, and every View panel enabled by default.',
       '2.1.8':'Windows system-proxy fallback, verified offline update import and actionable connection guidance.',
       '2.1.9':'Complete recording removal, reviewed TDMS parameter templates, persistent output folders, and real-file import corrections.',
       '2.2.0':'Per-file channel controls, active-graph navigation, separate About and User Manual windows, legacy configuration migration and verified installation cleanup.'}


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
            text+=f'## {title}\n'+body.replace('{{DEFAULT_VIEW}}',default)
        (ROOT/f'manuals/v{version}.md').write_text(text,encoding='utf-8')


if __name__=='__main__':
    import sys
    generate(sys.argv[1:] or None)
