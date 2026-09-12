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
        if d.is_dir()
        and not d.name.startswith("_")
        and d.name not in ("__pycache__", "use_cases")
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


def test_help_and_settings_contributions_are_typed_and_isolated():
    """``HelpContribution``/``SettingsContribution`` are frozen, typed and owner-isolated.

    Per ``docs/dev/tabs/isolation.md:60`` owner_tab == i18n_namespace and host
    must not import tabs.* for merge — contributions carry their own namespace.
    """
    from plugins.help.contribution import HelpContribution
    from plugins.settings.registry import SettingsContribution

    # Dataclasses are frozen
    assert getattr(HelpContribution, "__dataclass_params__").frozen is True
    assert getattr(SettingsContribution, "__dataclass_params__").frozen is True

    # HelpContribution must have typed owner_tab + nodes/aliases/body_root/asset_root/resolve_icon
    import inspect

    sig = inspect.signature(HelpContribution)
    for field in ("owner_tab", "nodes", "aliases", "body_root", "asset_root", "resolve_icon"):
        assert field in sig.parameters, f"HelpContribution missing typed field {field}"

    sig2 = inspect.signature(SettingsContribution)
    assert "owner_tab" in sig2.parameters
    assert "sections" in sig2.parameters

    # Collector exists and logs per-tab without stopping others
    from pathlib import Path

    text = (ROOT / "src" / "tabs" / "use_cases" / "capability_routing.py").read_text(encoding="utf-8")
    assert "def collect_help_contributions" in text
    assert "def collect_settings_contributions" in text
    assert "logger.exception" in text

    # Every tab that contributes help/settings must return owner_tab == i18n_namespace (or session_type fallback)
    # Instantiate tabs via registry discovery without needing Qt
    from tabs.registry import TabRegistry

    # Discover deferred too for full coverage
    reg = TabRegistry()
    reg.discover(tier="all")
    for tab in reg.list_tabs():
        expected = tab.i18n_namespace or tab.session_type
        # Check that if tab implements contribute_help/settings, it returns correct owner_tab
        # Use create_service typed path (no registry arg)
        for svc in ("contribute_help", "contribute_settings"):
            try:
                result = tab.create_service(svc)
            except Exception:
                continue
            if result is None or isinstance(result, bool):
                continue
            items = list(result) if isinstance(result, (list, tuple)) else [result]
            for item in items:
                owner = getattr(item, "owner_tab", None)
                assert owner == expected, (
                    f"tab {tab.session_type!r} {svc} owner_tab {owner!r} != expected {expected!r}"
                    " (must equal i18n_namespace per isolation.md:60)"
                )