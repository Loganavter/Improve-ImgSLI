"""Gallery test isolation: process-wide Qt singletons + lingering top-levels.

The ``src/tabs/`` suites run under ``src/tabs/conftest.py`` only — the
hygiene fixtures in ``tests/conftest.py`` (top-level suite) never apply
here. Without them, gallery tests leak hidden top-levels whose widgets
stay connected to app-lifetime singleton signals (``ThemeManager``,
``UiFont``, ``UiScale``); a later test's theme flip then fires stale
slots, and a wrapper whose C++ address was reused crashes in the Qt
event loop (order-dependent red, ``self`` is a ``dict``/``QSpacerItem``).

Mirrors ``tests/conftest.py::_destroy_lingering_toplevels`` and
``::_reset_theme_manager`` (kept as local copies — harmless duplication
beats shared-import coupling across conftest scopes, per that file).
"""

from __future__ import annotations

import pytest


def _sweep_all_destroyed(widgets) -> bool:
    """Best-effort check the sweep really destroyed everything (debug aid).

    Never fails the suite: returns True unless a *live* widget remains.
    """
    import shiboken6
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    for w in widgets:
        try:
            if shiboken6.isValid(w) and app is not None and w in app.topLevelWidgets():
                return False
        except RuntimeError:
            continue
    return True


@pytest.fixture(autouse=True)
def _destroy_lingering_toplevels():
    """Deterministically destroy lingering top-levels at teardown.

    ``qtbot`` teardown (``close()`` + ``deleteLater()``) never delivers
    ``DeferredDelete`` on its own, so test windows outlive their test
    with stale singleton receivers installed. Close the leak: at teardown
    every top-level widget created during the test is closed and its
    ``DeferredDelete`` delivered synchronously, so C++ destruction (and
    the widgets' singleton-slot disconnects) happens deterministically
    while Python wrappers are still alive.

    Only widgets created *during* the test are destroyed (setup snapshot).
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    # Strong refs: keep setup-time windows alive for the whole test so
    # the teardown below compares by identity, not id().
    before = list(app.topLevelWidgets()) if app is not None else []
    yield
    app = QApplication.instance()
    if app is None:
        return
    victims = [w for w in app.topLevelWidgets() if not any(w is b for b in before)]
    # Drop the setup refs first: widgets the test itself abandoned are
    # already half-torn-down or dead — only C++ destruction matters now.
    del before
    for w in victims:
        try:
            w.close()
        except RuntimeError:
            # Wrapper already dead (C++ gone with it) — nothing to do.
            pass
    for w in victims:
        try:
            w.deleteLater()
        except RuntimeError:
            pass
    for w in victims:
        try:
            QApplication.sendPostedEvents(w, QEvent.Type.DeferredDelete)
        except RuntimeError:
            pass
    # NOTE: no processEvents() here on purpose — pytest-qt's own
    # teardown hook drains the loop after all fixture finalizers, with
    # stale receivers already destroyed above.
    if not _sweep_all_destroyed(victims):
        import warnings

        warnings.warn(
            "lingering top-level widgets survived the teardown sweep; "
            "cross-test Qt state may leak",
            RuntimeWarning,
            stacklevel=2,
        )


@pytest.fixture(autouse=True)
def _reset_gallery_theme_manager():
    """ThemeManager is a process-wide singleton; isolate every test from it.

    Gallery theme tests register production palettes on the singleton and
    leave the last-flipped theme behind; bare-manager fallbacks are
    light-pinned, so the next test's construction-time token reads can
    observe the wrong theme. Snapshot-and-restore the singleton's mutable
    state around every test. Mirrors
    ``tests/conftest.py::_reset_theme_manager`` (palette/QSS/CSD parts
    omitted — gallery tests don't install app QSS or CSD filters).
    """
    from sli_ui_toolkit.managers import ThemeManager

    tm = ThemeManager.get_instance()
    saved = (
        tm._current_theme,
        tm._pending_theme,
        tm._light_palette,
        tm._dark_palette,
    )
    try:
        yield
    finally:
        tm._pending_theme = None
        tm._current_theme, tm._light_palette, tm._dark_palette = (
            saved[0],
            saved[2],
            saved[3],
        )
