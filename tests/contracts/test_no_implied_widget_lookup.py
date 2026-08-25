"""No implied lookups for dependencies that should be passed explicitly.

Dogma source: docs/dev/tabs/isolation.md "Dependency Wiring Rule: No Implied
Lookups". A widget/presenter/controller reference must reach its consumer
either as a constructor/method argument from the object that owns it, or as
`self`'s own state set in `__init__`. Reaching for it via a string-keyed
registry lookup (e.g. ``legacy_tab_widgets.get("image_compare")``) is a
side-channel that hides who is actually responsible for providing the value.

``ui.legacy_tab_widgets`` is the concrete example named in the dogma: it is
defined and populated by the tab that owns the widget
(``tabs/image_compare/tab.py``, via ``ui/main_window/ui.py``'s declaration),
and must not be *read* elsewhere as a way to obtain that widget. Consumers
must receive the widget explicitly instead.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._framework import SRC, iter_py, read, rel

OWNER_FILES = {
    Path("ui/main_window/ui.py"),
    Path("tabs/image_compare/tab.py"),
    # The one legitimate resolution root: startup.py is where the app first
    # asks "which tab is currently shown" during bootstrap, caches the
    # answer once on `window.image_compare_widget`, and threads it down
    # explicitly from there (composer.py -> features.py -> UIManager ->
    # TransientUIManager -> transient_ui_parts/*, and into
    # MainWindowPresenter). No other file reads legacy_tab_widgets.
    Path("ui/main_window/startup.py"),
}

_LOOKUP_RE = re.compile(r"legacy_tab_widgets(?:\.get\(|\[)")

# Widened C1/C2/C6/C7: additional implied-lookup shapes beyond the single
# legacy_tab_widgets example. Top-level widget scans and private navigation
# manager reaches are the same anti-pattern — a string-keyed / private-attr
# hunt that hides ownership.
_TOPLEVEL_RE = re.compile(r"topLevelWidgets\s*\(\)")
_NAV_PRIVATE_RE = re.compile(r"NavigationManager\._sections")

# Files that legitimately walk top-level widgets generically (not tab-
# specific). The sanctioned tab-aware accessor is ui/helpers/window_resolver.py;
# everything else must either use it or be a system-wide generic resolver
# marked ALLOWED.
_TOPLEVEL_ALLOWED = frozenset(
    {
        Path("ui/helpers/window_resolver.py"),
        Path("core/actions/types.py"),  # ALLOWED: widget_family generic resolver
        Path("plugins/help/dialog.py"),  # ALLOWED: main-window activation fallback
        Path("plugins/settings/application_service.py"),  # ALLOWED: scale-resync flush
        Path("shared_toolkit/ui/managers/ui_resource_manager.py"),  # ALLOWED: resource manager
        Path("devtools/ui_layout_dump.py"),  # ALLOWED: headless dump
        Path("ui/main_window/window.py"),  # ALLOWED: window lifecycle
        Path("ui/main_window/lifecycle.py"),  # ALLOWED: shutdown close
        Path("ui/actions/palette/common.py"),  # ALLOWED: palette discovery
        Path("ui/actions/palette/dialog.py"),  # ALLOWED: palette dialog
        Path("ui/actions/palette/__init__.py"),  # ALLOWED: palette init
        Path("tabs/multi_compare/ui/canvas_widget.py"),  # ALLOWED: canvas fallback
        Path("tabs/host_helpers.py"),  # ALLOWED: docstring mentions private name
    }
)


def test_legacy_tab_widgets_is_not_read_as_a_lookup_side_channel():
    offenders: list[str] = []
    for py in iter_py(SRC):
        rel_path = py.relative_to(SRC)
        if rel_path in OWNER_FILES:
            continue
        text = read(py)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _LOOKUP_RE.search(line):
                offenders.append(f"{rel(py)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Found implied widget lookups via legacy_tab_widgets outside its "
        "owner. Pass the widget explicitly from the owner instead:\n  - "
        + "\n  - ".join(offenders)
    )


def test_no_top_level_widget_scan_outside_resolver():
    offenders: list[str] = []
    for py in iter_py(SRC):
        rel_path = py.relative_to(SRC)
        if rel_path in _TOPLEVEL_ALLOWED:
            continue
        text = read(py)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "ALLOWED" in line:
                continue
            if _TOPLEVEL_RE.search(line):
                offenders.append(f"{rel(py)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Found topLevelWidgets() scan outside the sanctioned resolver "
        "(ui/helpers/window_resolver.py or ALLOWED generic). Use "
        "find_main_window()/find_event_bus() instead:\n  - "
        + "\n  - ".join(offenders)
    )


def test_no_navigation_manager_private_sections():
    offenders: list[str] = []
    for py in iter_py(SRC):
        rel_path = py.relative_to(SRC)
        if rel_path in _TOPLEVEL_ALLOWED:
            continue
        text = read(py)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "ALLOWED" in line:
                continue
            if _NAV_PRIVATE_RE.search(line):
                offenders.append(f"{rel(py)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Found private NavigationManager._sections access — use the return "
        "value of declare_toolbar_navigation() / declare_navigation_rows() "
        "via tabs.host_helpers instead (C6):\n  - " + "\n  - ".join(offenders)
    )
