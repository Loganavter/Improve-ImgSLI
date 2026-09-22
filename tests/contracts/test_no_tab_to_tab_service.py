"""Enforcement: no tab→tab TabRegistry service calls.

Tabs are isolated modules under ``src/tabs/<name>/``.  A tab must not
reach into another tab's implementation via
``TabRegistry.create_service`` / ``create_startup_service`` /
``create_service_for`` with a service_id literal that only another tab
provides.

Provider catalog is derived from ``grep -rn 'service_id ==' src/tabs``
(the ``service_id == "X"`` branches inside ``tab.py`` and
``service_factory.py``).  A call is a violation when:

* file is ``src/tabs/<tab>/...`` owned by concrete tab ``<tab>``
  (directories with ``tab.py``), excluding the provider definitions
  themselves (``tab.py`` ``def create_service`` and
  ``service_factory.py``),
* the ``service_id`` literal is in the provider catalog,
* the owning tab is NOT in the provider set for that id (i.e. the id
  resolves only to another tab),
* host code (``src/ui/*``, ``src/plugins/*``, etc.) is out of scope — only
  ``src/tabs`` is scanned,
* ``TabContext.call_service`` / ``context.call_service("...")`` is *not*
  a registry call — it goes through ``TabContext.services`` (see
  ``tabs/contract.py:183`` ``services={...}``) — allowed,
* ``from tabs._shared import ...`` is shared infra, not tab→tab — allowed,
* a line containing ``# ALLOWED: tab calls host-provided shared`` is
  explicitly allowlisted for the single legitimate shared case (e.g.
  ``tabs/session_picker/host_chrome.py`` if it needs a host bridge).

If a tab calls a foreign id — fail with ``file:line`` and provider info.

Dogma: docs/dev/tabs/isolation.md:83 dependency wiring rule.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.contracts._framework import ROOT, SRC

TABS_ROOT = SRC / "tabs"

# service_id == "X" provider discovery — mirrors `grep -rn 'service_id =='`
_PROVIDER_RE = re.compile(r'service_id\s*==\s*["\']([^"\']+)["\']')

# registry call names that resolve via TabRegistry / capability routing
_CALL_NAMES = {"create_service", "create_startup_service", "create_service_for"}

# files that define providers, not consumers — excluded from the scan
_EXCLUDED_SUFFIXES = ("tab.py", "service_factory.py")

# concrete tabs are directories under src/tabs that contain tab.py
def _known_tabs() -> frozenset[str]:
    tabs: set[str] = set()
    if TABS_ROOT.is_dir():
        for d in TABS_ROOT.iterdir():
            if d.is_dir() and (d / "tab.py").exists():
                tabs.add(d.name)
    return frozenset(tabs)


_KNOWN_TABS = _known_tabs()
assert _KNOWN_TABS, "no tabs discovered — expected directories with tab.py under src/tabs"


def _build_provider_map() -> dict[str, set[str]]:
    """Map service_id literal -> set(owning tab names)."""
    m: dict[str, set[str]] = {}
    for py in TABS_ROOT.rglob("*.py"):
        if "__pycache__" in py.parts or "tests" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        for sid in _PROVIDER_RE.findall(text):
            try:
                idx = py.parts.index("tabs")
                tab = py.parts[idx + 1]
            except (ValueError, IndexError):
                continue
            if tab not in _KNOWN_TABS:
                continue
            m.setdefault(sid, set()).add(tab)
    return m


_PROVIDER_MAP: dict[str, set[str]] = _build_provider_map()
# sanity: at least the hub tab
assert "session_picker.host_chrome" in _PROVIDER_MAP, "provider map missing session_picker.host_chrome"


def _owning_tab(path: Path) -> str | None:
    """Return concrete tab name for path, or None if not tab-owned code."""
    try:
        idx = path.parts.index("tabs")
        tab = path.parts[idx + 1]
    except (ValueError, IndexError):
        return None
    if tab in _KNOWN_TABS:
        return tab
    return None


def _iter_tab_files():
    for py in TABS_ROOT.rglob("*.py"):
        if "__pycache__" in py.parts or "tests" in py.parts:
            continue
        # provider definitions themselves are not consumers
        if py.name in _EXCLUDED_SUFFIXES:
            continue
        # also skip any file whose name ends with those suffixes (e.g. nested)
        # service_factory.py only exists at top-level per tab, but be safe
        if py.name == "service_factory.py":
            continue
        owning = _owning_tab(py)
        if owning is None:
            # infra: src/tabs/_shared, src/tabs/contract.py, registry.py,
            # use_cases/* etc. — not tab-owned, skip
            continue
        yield py


def _is_allowed_line(line: str) -> bool:
    # single legitimate host-provided shared bridge
    return "ALLOWED" in line and "tab calls host-provided shared" in line


def _extract_service_id_literal(node: ast.Call, call_name: str) -> tuple[str | None, int | None]:
    """Return (service_id literal or None, lineno) for this registry call."""
    # create_service_for(session_type, service_id, ...)
    # create_service / create_startup_service(service_id, ...)
    try:
        if call_name == "create_service_for":
            if len(node.args) >= 2:
                arg = node.args[1]
            else:
                # keyword: service_id=...
                for kw in node.keywords:
                    if kw.arg == "service_id" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        return kw.value.value, kw.value.lineno
                return None, None
        else:
            if node.args:
                arg = node.args[0]
            else:
                for kw in node.keywords:
                    if kw.arg == "service_id" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        return kw.value.value, kw.value.lineno
                return None, None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value, arg.lineno
    except Exception:
        return None, None
    return None, None


def test_no_tab_to_tab_registry_service_calls():
    """No tab file calls registry for a service_id only another tab provides."""
    offenders: list[str] = []
    for path in sorted(_iter_tab_files()):
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except SyntaxError:
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            call_name = func.attr
            if call_name not in _CALL_NAMES:
                continue
            # need registry-like receiver? Spec says any registry.create_service
            # call — but also tolerate any object with those method names.
            # Distinguish TabContext.call_service (whitelisted, not in _CALL_NAMES)
            # so we already only look at registry names.
            # Additionally, `from tabs._shared import` is allowed — but that
            # import does not create registry calls, so no extra filter needed.
            sid, lineno = _extract_service_id_literal(node, call_name)
            if sid is None or lineno is None:
                continue
            # only flag tab-owned service_ids; host-provided ids are not in map
            providers = _PROVIDER_MAP.get(sid)
            if not providers:
                continue
            owning = _owning_tab(path)
            if owning is None:
                continue
            if owning in providers:
                # self or shared ownership — not tab→tab
                continue
            # allowlist comment on same line
            line_text = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
            if _is_allowed_line(line_text):
                continue
            # also allow if line imports from tabs._shared (not a call, but keep)
            # No need — we already filter.
            offenders.append(
                f"{rel}:{lineno} tab '{owning}' calls registry.{call_name}(\"{sid}\") "
                f"but only {sorted(providers)} provide it"
            )
    assert not offenders, (
        "tab→tab TabRegistry service calls found (use TabContext.call_service for "
        "host-provided shared, or move wiring to host/src/ui|plugins; if genuinely "
        "host-provided shared add '# ALLOWED: tab calls host-provided shared'):\n  "
        + "\n  ".join(offenders)
    )


def test_provider_map_covers_known_tabs():
    """Sanity: provider map is not empty and per-tab providers exist."""
    # each known tab should have at least one provider entry if it implements tab.py
    # image_gallery only contributes contribute_settings, etc.
    for tab in _KNOWN_TABS:
        provided = [sid for sid, tabs in _PROVIDER_MAP.items() if tab in tabs]
        assert provided, f"tab '{tab}' has no service_id == provider entries"
