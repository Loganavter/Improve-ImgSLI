"""Runtime-suite Qt isolation: deterministically destroy lingering top-levels.

Segfault root cause (2026-09, ``feat/toast-cleanup``): the full
``tests/runtime`` run crashed with a Fatal Python error (SIGSEGV) in
``pytestqt/plugin.py:_process_events`` at
``test_value_slider_row.py::test_label_tracks_slider_value``. Bisection
pinned the minimal pair to
``test_ui_scale_live_apply.py`` + ``test_value_slider_row.py`` — more
precisely, to *constructing* a ``SettingsDialog`` in one test and showing
a plain ``QDialog`` in the next. Causal chain:

1. Building a ``SettingsDialog`` registers navigation sections (sidebar +
   every settings page) in the process-wide ``NavigationManager``
   singleton, which installs itself as a permanent ``QApplication`` event
   filter on first registration.
2. ``qtbot`` teardown (``close()`` + ``deleteLater()`` + bare
   ``processEvents()``) never actually destroys test windows: on the
   offscreen QPA, ``processEvents()`` does not deliver ``DeferredDelete``,
   so the dialog leaks — alive, with its nav registrations keeping the
   app filter installed. (Plus, several ``SettingsDialog`` signal
   connections hold bound methods, so even Python GC never reclaims it.)
3. The next test shows its own dialog. ``qtbot.waitExposed(d)`` used as a
   bare call (no ``with``) is a no-op — the wait only happens in the
   context manager's ``__exit__`` — so no events are processed while the
   window is alive.
4. At body end the test frame dies, the parentless dialog has no Python
   refs left, and shiboken deletes the C++ window synchronously (normal
   PySide ownership semantics for Python-owned top-levels).
5. Post-body ``app.processEvents()`` delivers the stale window-system
   focus event queued by ``show()``; ``setActiveWindow`` notifies through
   the still-installed app filter with the dead receiver, and PySide's
   ``getWrapperForQObject`` dereferences freed memory
   (``QObject::property`` → SIGSEGV).

This fixture closes the leak at step 2: at teardown every top-level
widget created during the test is closed and its ``DeferredDelete``
delivered synchronously, so C++ destruction (and with it all
``destroyed``-triggered cleanups: nav ``unregister()``, theme/UiScale
disconnects, app-filter unhooks) happens deterministically while Python
wrappers are still alive. The next test then runs filter-free and the
stale focus events from step 5 are harmless.

Only widgets created *during* the test are destroyed (setup snapshot),
so windows owned by wider-scoped fixtures would survive — there are
currently no module/session-scoped widget fixtures under
``tests/runtime``.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture(autouse=True)
def _destroy_lingering_toplevels():
    app = QApplication.instance()
    # Strong refs: keep setup-time windows alive for the whole test so
    # their later teardown below compares by identity, not id().
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
    # the nav app filter already uninstalled by the destroys above.
    if not _all_destroyed(victims):
        import warnings

        warnings.warn(
            "lingering top-level widgets survived the runtime teardown sweep; "
            "cross-test Qt state may leak",
            RuntimeWarning,
            stacklevel=2,
        )


@pytest.fixture(autouse=True)
def _reset_font_state():
    """App font state is process-wide; isolate every test from it.

    ``FontManager.apply_from_state()`` (e.g. ``test_ui_scale_live_apply``)
    pins the application font (builtin Source Sans 3) via
    ``QApplication.setFont`` + ``UiFont.set_family`` and never unpins it.
    Later pixel-exact tests (``test_value_popup_surface`` grabs a
    ``_PopupBubble`` and asserts its center pixel equals the
    ``flyout.background`` token) then rasterize their labels in a
    different face: glyph metrics shift, the bubble center lands on an
    antialiased text edge (46,43,43 vs 43,43,43) and the test fails only
    in full-suite order. Snapshot and restore the font state around every
    test, mirroring ``_reset_theme_manager`` in ``tests/conftest.py``.
    """
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from shared_toolkit.ui.managers.font_manager import FontManager

    fm = FontManager.get_instance()
    saved_mode, saved_family = fm._current_mode, fm._current_family
    app = QApplication.instance()
    saved_qfont = QFont(app.font()) if app is not None else None
    ui = None
    saved_ui_family = None
    try:
        from sli_ui_toolkit.managers import UiFont

        ui = UiFont.get_instance()
        if hasattr(ui, "family"):
            saved_ui_family = ui.family()
    except Exception:
        ui = None
    try:
        yield
    finally:
        fm._current_mode, fm._current_family = saved_mode, saved_family
        if app is not None and saved_qfont is not None:
            try:
                app.setFont(saved_qfont)
            except RuntimeError:
                pass
        if ui is not None and saved_ui_family is not None:
            try:
                ui.set_family(saved_ui_family)
                if hasattr(ui, "sync_from_application"):
                    ui.sync_from_application()
            except Exception:
                pass


def _all_destroyed(widgets: list[QWidget]) -> bool:
    """Best-effort check the sweep really destroyed everything (debug aid).

    Never fails the suite: returns True unless a *live* widget remains.
    """
    import shiboken6

    for w in widgets:
        try:
            if shiboken6.isValid(w) and w in QApplication.instance().topLevelWidgets():
                return False
        except RuntimeError:
            continue
    return True
