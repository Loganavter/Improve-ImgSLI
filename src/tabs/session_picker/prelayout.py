"""Pre-layout width estimate owned by the Session Picker tab.

Tab-isolation rule: code under ``src/tabs/<tab>/`` must not import the
platform-level toolkit (see ``tests/contracts/test_tabs_isolation.py``).
The generic ``estimate_prelayout_width`` helper used to be reached through
the ``tabs.host_helpers`` seam; this module owns a local copy so the tab
depends only on its own package. Body and docstring semantics are kept
identical to the original helper in the platform layout-sizing module.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget


def estimate_prelayout_width(
    widget: QWidget,
    *,
    horizontal_chrome: int = 0,
    floor: int = 0,
) -> int:
    """Best-guess content width for ``widget`` before its first layout pass.

    Some widgets need a real width estimate *before* they have ever been
    shown — e.g. to pick a grid column count synchronously at construction
    time, so the first paint doesn't need a second pass once the real size
    is known. At that point ``widget.width()`` is **not** 0 — Qt reports its
    classic constructor placeholder (100) — so a plain ``width() > 0`` check
    cannot tell "never laid out" apart from "genuinely 100px wide". The
    reliable signal is ``Qt.WidgetAttribute.WA_Resized``: Qt sets it the
    moment a widget is given a real size, either explicitly
    (``resize()``/``setGeometry()``) or by an activated layout — never for
    the untouched constructor default. Confirmed empirically: a freshly
    parented, not-yet-shown widget reports ``width()==100`` with
    ``WA_Resized`` unset; after the ancestor chain is shown and laid out,
    ``WA_Resized`` flips and ``width()`` reflects the true size.

    If the app already restores the main window's geometry before building
    workspace content (the common startup order — see
    ``ui/main_window/lifecycle.py``'s ``LoadWindowStateStep`` running before
    ``BootstrapContentStep``), the top-level window already has
    ``WA_Resized`` set and a real width at this point even though ``widget``
    itself has never been laid out (``setGeometry()`` applies immediately,
    regardless of visibility). ``widget.window().width()`` is then a much
    better estimate than any static floor — pass ``horizontal_chrome`` for
    whatever fixed width sits between the window and ``widget`` (sidebars,
    permanent margins; 0 when the widget's ancestor chain has no such
    chrome).

    One more wrinkle, confirmed from a real run: when the window is
    restored **maximized**, ``GeometryManager`` first ``setGeometry()``s it
    to the persisted *normal* (un-maximized) size — which sets
    ``WA_Resized`` and a real but not-final width — and only then requests
    ``setWindowState(Maximized)``. The platform applies that maximize
    asynchronously (a window-manager round trip), and can even deliver it in
    more than one step (the restore-size geometry briefly for real, *then*
    the final maximized geometry) — so both ``widget.width()`` and
    ``widget.window().width()`` can report a real, ``WA_Resized``-flagged,
    but still not-final size for one or more frames. ``isMaximized()`` /
    ``isFullScreen()`` do not have this staggered-delivery problem — Qt
    flips them synchronously on ``setWindowState()``, before the platform
    geometry catches up — so that check runs *first* and unconditionally
    wins over any width already recorded on the widget or window: while the
    window is (going to be) maximized/fullscreen, the screen's available
    width is always the right answer, no matter which transitional frame
    this call happens to land on.

    Falls back to ``floor`` when nothing here has a usable size yet (e.g. in
    tests that construct the widget without a real top-level window and
    never call ``resize()``/``show()``).
    """
    window = widget.window()
    if window is not None and (window.isMaximized() or window.isFullScreen()):
        screen = window.screen() if hasattr(window, "screen") else None
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            screen_width = int(screen.availableGeometry().width())
            estimated = screen_width - int(horizontal_chrome)
            if estimated > 0:
                return estimated
    if widget.testAttribute(Qt.WidgetAttribute.WA_Resized):
        width = int(widget.width())
        if width > 0:
            return width
    if window is not None and window.testAttribute(Qt.WidgetAttribute.WA_Resized):
        estimated = int(window.width()) - int(horizontal_chrome)
        if estimated > 0:
            return estimated
    return max(0, int(floor))
