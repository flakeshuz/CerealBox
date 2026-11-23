#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    python=python3
elif command -v python >/dev/null 2>&1; then
    python=python
else
    echo "Python 3.11 or newer is required but was not found." >&2
    exit 1
fi

if ! "$python" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    echo "Python 3.11 or newer is required." >&2
    exit 1
fi

if ! "$python" -c 'import cryptography, PyQt6'; then
    echo "Installing CerealBox dependencies..."
    "$python" -m pip install --user --disable-pip-version-check .
fi
exec "$python" main.py "$@"
