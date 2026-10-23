"""Run from the repository root: python scripts/verify_snapshot.py FILE [--output FILE]."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edge_clone_engine import MODES
from edge_verification import verify_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--mode', choices=MODES, default=MODES[1])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        report = verify_snapshot(args.snapshot.read_bytes(), args.mode)
    except (ValueError, OSError) as error:
        parser.exit(1, 'Verifica non completata: ' + (str(error) if isinstance(error, ValueError) else 'File non leggibile.') + '\n')
    rendered = json.dumps(report, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end='')


if __name__ == '__main__':
    main()
