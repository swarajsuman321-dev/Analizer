"""Create the public updater manifest from the exact tested executable."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app_version import VERSION
from app_updates import RELEASES,validate_manifest
exe=Path('dist/ApplianceSignalStudio.exe')
with exe.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
data={'version':VERSION,'url':f'{RELEASES}/download/v{VERSION}/ApplianceSignalStudio.exe',
      'size':exe.stat().st_size,'sha256':checksum,
      'notes':Path(f'manuals/v{VERSION}.md').read_text(encoding='utf-8').split('## Changes in this version\n',1)[1].split('\n##',1)[0].strip()}
Path('dist/update.json').write_text(json.dumps(validate_manifest(data),indent=2),encoding='utf-8')

# Separate feed keeps installed updates isolated from older single-EXE clients.
setup=Path(f'dist/ApplianceSignalStudio-Setup-{VERSION}.exe')
with setup.open('rb') as stream:setup_hash=hashlib.file_digest(stream,'sha256').hexdigest()
installer={**data,'kind':'installer','url':f'{RELEASES}/download/v{VERSION}/{setup.name}',
           'size':setup.stat().st_size,'sha256':setup_hash}
Path('dist/installer-update.json').write_text(json.dumps(validate_manifest(installer),indent=2),encoding='utf-8')

# Folder users receive the complete runtime rather than a single-EXE conversion.
archive=Path('dist/ApplianceSignalStudio_Portable.zip')
with archive.open('rb') as stream:archive_hash=hashlib.file_digest(stream,'sha256').hexdigest()
folder={**data,'kind':'portable-zip','url':f'{RELEASES}/download/v{VERSION}/{archive.name}',
        'size':archive.stat().st_size,'sha256':archive_hash}
Path('dist/zip-update.json').write_text(json.dumps(validate_manifest(folder),indent=2),encoding='utf-8')
