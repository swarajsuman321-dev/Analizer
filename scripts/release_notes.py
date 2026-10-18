"""Keep GitHub release notes bounded; attach the complete version manual separately."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app_version import VERSION


def release_notes(version,manual):
    heading='## Changes in this version\n'
    if heading not in manual:raise ValueError('Version manual is missing release notes')
    changes=manual.split(heading,1)[1].split('\n##',1)[0].strip()
    if not changes or len(changes)>12000:raise ValueError('Release summary must contain 1–12000 characters')
    return f'# Appliance Signal Studio {version}\n\n{changes}\n\nFor installation, download **ApplianceSignalStudio-Setup-{version}.exe**. The Windows standalone EXE and complete portable ZIP remain available below. The complete user manual is attached as **v{version}.md**.\n\nExisting workspaces and source data remain supported. Configure appliance mappings, calibrations and acceptance limits before evaluating engineering results.\n'


if __name__=='__main__':
    manual=Path(f'manuals/v{VERSION}.md').read_text(encoding='utf-8')
    Path('dist').mkdir(exist_ok=True)
    Path('dist/release-notes.md').write_text(release_notes(VERSION,manual),encoding='utf-8')
