"""Single source of the product name for the Windows packaging layer.

The name is **not** defined here: it lives in ``src/core/log_names.py``
(``APP_NAME``), the app's one spelling of its identity, so packaging can never
drift from what the executable calls itself. This module only derives the
Windows artifact names and paths from that constant.

The installer version keeps its old home — ``#define MyAppVersion`` in
``inno_setup_6.iss`` — and is read from there instead of being duplicated.

Importers: ``<APP_NAME>.spec``, ``build_windows.py``,
``write_license_bundle.py``, ``build/ci/validate_*.py`` and
``check_product_name.py``. The spec and ``build_windows.py`` must not spell the
product name again; ``check_product_name.py`` fails the build when they do.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMPLATE_DIR.parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.log_names import APP_NAME  # noqa: E402  (needs SRC_ROOT on sys.path)

INNO_PATH = TEMPLATE_DIR / "inno_setup_6.iss"

SPEC_FILENAME = f"{APP_NAME}.spec"
SPEC_PATH = TEMPLATE_DIR / SPEC_FILENAME

#: PyInstaller onedir output directory: ``dist/<APP_NAME>/``.
DIST_DIRNAME = APP_NAME
DIST_DIR = REPO_ROOT / "dist" / DIST_DIRNAME

#: Executable inside the onedir bundle: ``dist/<APP_NAME>/<APP_NAME>.exe``.
BUNDLE_EXE_NAME = f"{APP_NAME}.exe"
BUNDLE_EXE = DIST_DIR / BUNDLE_EXE_NAME

#: Inno ``OutputDir`` from the same script (relative to the template dir).
INNO_OUTPUT_DIR = TEMPLATE_DIR / "Output"


def read_inno_define(name: str, *, path: Path = INNO_PATH) -> str:
    """Return the value of ``#define <name> "value"`` from the Inno script."""
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf'^#define\s+{re.escape(name)}\s+"([^"]*)"\s*$', text, re.MULTILINE
    )
    if match is None:
        raise RuntimeError(f"{path.name}: missing '#define {name}'")
    return match.group(1)


#: Version single source for Windows packaging: the installer script.
APP_VERSION = read_inno_define("MyAppVersion")

#: ``<APP_NAME>_Setup_v<version>.exe`` in the Inno output directory.
SETUP_BASENAME = f"{APP_NAME}_Setup_v{APP_VERSION}"
SETUP_EXE_NAME = f"{SETUP_BASENAME}.exe"
SETUP_EXE = INNO_OUTPUT_DIR / SETUP_EXE_NAME
