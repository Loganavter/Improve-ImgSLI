#!/bin/bash
# Thin POSIX wrapper: locate Python 3 and exec the real launcher (launcher.py).
# Kept bash-3.2-safe (no ${var^}, no sed -r, no arrays) so macOS works.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || command -v python || true)"

if [[ -z "$PY" ]]; then
    echo "Error: Python 3 (python3 or python) not found on PATH." >&2
    exit 1
fi

exec "$PY" "$SCRIPT_DIR/launcher.py" "$@"
