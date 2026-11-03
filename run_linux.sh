#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -x ".venv/bin/python" ]; then
    echo "Creating virtual environment in .venv..."
    if command -v uv >/dev/null 2>&1; then
        uv venv .venv
        uv pip install "git+https://github.com/sslivins/pysensorlinx.git"
        uv pip install -e .
    else
        python3 -m venv .venv
        .venv/bin/pip install --upgrade pip
        .venv/bin/pip install "git+https://github.com/sslivins/pysensorlinx.git"
        .venv/bin/pip install -e .
    fi
fi

exec .venv/bin/python -m sensorlinx_desktop.main "$@"
