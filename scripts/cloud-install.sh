#!/usr/bin/env bash
set -euo pipefail

# Each cloud task is isolated: use the existing checkout, not another worktree.
cd /workspace/SPX-Edge-GEX-Lab
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/workspace/.cache/pip}"
if [ ! -x .venv/bin/python ]; then
    python3.12 -m venv .venv
fi
.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 required"'
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest tests -q -p no:cacheprovider
