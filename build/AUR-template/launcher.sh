#!/bin/sh
export PYTHONPATH="/usr/lib/improve-imgsli/vendor-libs${PYTHONPATH:+:$PYTHONPATH}"
exec python "/usr/lib/improve-imgsli/Improve_ImgSLI.py" "$@"