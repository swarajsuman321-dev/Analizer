"""Run the executable acceptance profile against source and committed recordings."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=Path, default=ROOT/'tests/samples/recordings')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from app_release_acceptance import run_acceptance
    result = run_acceptance(args.samples, args.output)
    print(json.dumps({'ok': result['ok'], **result['summary']}))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
