"""Verify that the explicitly shared test recordings remain byte-identical."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=Path,default=Path(__file__).resolve().parents[1]/'tests/samples/recordings')
    args=parser.parse_args()
    manifest=json.loads((args.samples/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version')!=1:parser.error('Unsupported sample manifest')
    if {entry['role'] for entry in manifest['files']}!={'power','machine','tdms','simulation'}:parser.error('Expected the four recorded sample roles')
    for entry in manifest['files']:
        if Path(entry['filename']).name!=entry['filename']:parser.error('Sample filenames must be local to the sample directory')
        path=args.samples/entry['filename']
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if path.stat().st_size!=entry['bytes'] or digest!=entry['sha256']:parser.error('Sample changed: '+entry['filename'])
        print(f"OK {entry['role']}: {entry['filename']} ({entry['bytes']} bytes)")
    return 0


if __name__=='__main__':raise SystemExit(main())
