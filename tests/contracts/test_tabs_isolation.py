"""Tab isolation dogma.

A tab under ``src/tabs/<name>/`` is a self-contained mini-app: it owns its own
i18n namespace and resources. It must NOT:
  * import the app's main i18n key set (``resources.i18n``) or the shared
    UI toolkit theme set (``shared_toolkit``);
  * reference foreign i18n namespaces (``app.*``, ``main.*``, ``common.*``)
    in its own translation JSON.

Dogma source: docs/dev/tabs/isolation.md (tabs use only their own namespace).
"""

from __future__ import annotations

import json
import re

import pytest

from ._framework import ROOT, iter_py, module_imports, rel

TABS = ROOT / "src" / "tabs"

def _tab_packages() -> list:
    if not TABS.is_dir():
        return []
    return sorted(
        d
        for d in TABS.iterdir()
        if d.is_dir() and not d.name.startswith("_") and d.name != "__pycache__"
    )

TAB_PKGS = _tab_packages()
TAB_IDS = [d.name for d in TAB_PKGS]

_FORBIDDEN_IMPORT_RE = re.compile(
    r"^(?:src\.)?(resources\.i18n|resources\.translations|shared_toolkit|ui\.icon_manager)\b"
)
_FOREIGN_NS = ("app.", "main.", "common.")

@pytest.mark.parametrize("pkg", TAB_PKGS, ids=TAB_IDS)
def test_tab_does_not_import_app_i18n_or_theme_set(pkg):
    leaks: list[str] = []
    for py in iter_py(pkg):
        for module, lineno in module_imports(py):
            if _FORBIDDEN_IMPORT_RE.match(module):
                leaks.append(
                    f"{rel(py)}:{lineno} imports '{module}' "
                    f"(tabs must use their own namespace/resources)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)

@pytest.mark.parametrize("pkg", TAB_PKGS, ids=TAB_IDS)
def test_tab_json_uses_only_own_namespace(pkg):
    leaks: list[str] = []
    for jf in pkg.rglob("*.json"):
        if "__pycache__" in jf.parts:
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        for key in _flat_keys(data):
            if key.startswith(_FOREIGN_NS):
                leaks.append(
                    f"{rel(jf)} references foreign i18n key '{key}' "
                    f"(tabs must use their own namespace)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)

def _flat_keys(data: dict, prefix: str = "") -> list[str]:
    out: list[str] = []
    for key, value in data.items():
        full = f"{prefix}{key}"
        out.append(full)
        if isinstance(value, dict):
            out.extend(_flat_keys(value, f"{full}."))
    return out
