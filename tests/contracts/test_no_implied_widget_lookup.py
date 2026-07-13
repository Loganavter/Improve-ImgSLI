"""No implied lookups for dependencies that should be passed explicitly.

Dogma source: docs/dev/TAB_CONTRACT.md "Dependency Wiring Rule: No Implied
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
