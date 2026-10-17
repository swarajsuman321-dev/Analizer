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
       '2.1.9':'Complete recording removal, reviewed TDMS parameter templates, persistent output folders, and real-file import corrections.'}


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
            if introduced<=number:text+=f'## {title}\n'+body.replace('{{DEFAULT_VIEW}}',default)
        (ROOT/f'manuals/v{version}.md').write_text(text,encoding='utf-8')


if __name__=='__main__':
    import sys
    generate(sys.argv[1:] or None)
