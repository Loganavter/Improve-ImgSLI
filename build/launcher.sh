#!/bin/sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python "$SCRIPT_DIR/./src/Improve_ImgSLI.py" "$@"