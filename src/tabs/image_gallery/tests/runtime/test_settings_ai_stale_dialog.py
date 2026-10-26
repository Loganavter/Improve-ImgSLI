"""The model-catalog completion survives a closed Settings dialog.

The AI page's model list is fetched OFF the GUI thread
(``settings_ai._start_thread_task``): the completion arrives later, on the GUI
thread, through a closure over the dialog. Closing Settings deletes the C++
dialog tree first, so a completion that lands afterwards used to reach a dead
``ComboBox``:

    RuntimeError: libshiboken: Internal C++ object (ComboBox) already deleted
      settings_ai.py:1017 in _done -> _fill_model_list(...)
      settings_ai.py:940  in _fill_model_list -> dialog.gallery_ai_model_list.clear()

(owner log, 2026-10-26 03:34:54; those line numbers are the PRE-FIX ones —
``_fill_model_list`` is now at ``settings_ai.py:947`` and ``_done`` at
``settings_ai.py:1061``). The broad ``except`` in ``_done`` turned that
into a debug line, which is why it never crashed — and why it stayed invisible.

RED BEFORE: no code path asked whether the dialog still existed, so delivering
the completion after destruction raised the RuntimeError above (surfaced by
``_surface_apply_failure`` below, since the production ``except`` swallows it),
and the finished worker handle stayed in ``dialog._gallery_ai_model_tasks``.

Offscreen and hermetic: the discovery seam is injected (no network), the worker
seam is captured instead of started (no thread — the test decides *when* the
completion arrives), and both QSettings groups are redirected.
"""

from __future__ import annotations

import logging

import pytest
import shiboken6
from PySide6.QtCore import QSettings

from core.log_names import APP_LOGGER_NAME
from tabs.image_gallery.services import ai_models
from tabs.image_gallery.services import ai_settings_store as store_module

_STORE_GROUP = "image_gallery_ai_test_stale_dialog"
_MODELS_GROUP = "image_gallery_ai_models_test_stale_dialog"

#: The exact line the owner's log carried when the completion touched the dead
#: combo — kept as the discriminator this file pins.
_APPLY_FAILED = "AI model list apply failed"


class _PendingCompletions:
    """A ``START_TASK`` stand-in that never reports on its own.

    The page keeps every returned handle alive (a garbage-collected worker never
    delivers), so the stand-in hands back a real object and lets the test fire
    the completion — the only way to reproduce "the dialog died first".
    """

    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def start(self, task, on_done):
        handle = object()
        self.calls.append((handle, on_done))
        return handle


@pytest.fixture
def gallery_ai_store(monkeypatch):
    """Throwaway AI-settings + model-cache groups; the real config is untouched."""
    monkeypatch.setattr(store_module, "_QS_GROUP", _STORE_GROUP)
    monkeypatch.setattr(ai_models, "_QS_GROUP", _MODELS_GROUP)
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    for group in (_STORE_GROUP, _MODELS_GROUP):
        settings.remove(group)
    yield
    for group in (_STORE_GROUP, _MODELS_GROUP):
        settings.remove(group)


@pytest.fixture
def dialog_page(qapp, gallery_ai_store, monkeypatch):
    """A real ``SettingsDialog`` carrying only the gallery-AI page."""
    pending = _PendingCompletions()
    widget = _build_dialog(monkeypatch, pending)
    yield widget, pending
    # A test may have destroyed the C++ object already (that is the point).
    if shiboken6.isValid(widget):
        widget.close()
        widget.deleteLater()


def _build_dialog(monkeypatch, pending):
    from plugins.settings.dialog import SettingsDialog
    from plugins.settings.registry import (
        ensure_tab_settings_contributions,
        get_settings_registry,
    )
    from tabs.image_gallery.ui import settings_ai
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    registry.contribute_all_settings()
    ensure_tab_settings_contributions()
    assert "image_gallery.ai" in {
        section.section_id for section in get_settings_registry().all_sections()
    }

    def _fake_models_for(provider, api_key, *, refresh=False, report=None):
        if report is not None:
            report["reason"] = ai_models.REASON_OK
        return ("fake/model-one", "fake/model-two"), ai_models.SOURCE_NETWORK

    monkeypatch.setattr(settings_ai, "MODELS_FOR", _fake_models_for)
    monkeypatch.setattr(settings_ai, "START_TASK", pending.start)
    # No live gallery tab: the Apply-time re-analysis offer stays out of the way.
    monkeypatch.setattr(settings_ai, "GALLERY_OWNER", lambda: None)

    return SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=9999,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        active_tab="image_gallery",
    )


def _surface_apply_failure(caplog) -> None:
    """Re-raise the exception ``_done`` swallowed — the defect's own symptom.

    Production logs it and moves on (a settings page must never crash on a late
    fetch), so the test has to lift the record back out to fail on it.
    """
    failures = [
        record for record in caplog.records if record.getMessage() == _APPLY_FAILED
    ]
    if not failures:
        return
    exc_info = failures[0].exc_info
    if isinstance(exc_info, tuple) and len(exc_info) == 3 and exc_info[1] is not None:
        raise exc_info[1]
    raise AssertionError(f"{_APPLY_FAILED}: the completion touched a dead dialog")


def test_completion_after_the_dialog_is_destroyed_is_a_silent_noop(dialog_page, caplog):
    dialog, pending = dialog_page
    handles = dialog._gallery_ai_model_tasks
    assert len(pending.calls) == 1, "precondition: the build's fetch is in flight"
    assert len(handles) == 1, "precondition: the worker handle is kept alive"

    # What closing Settings does: the C++ tree (combo included) is deleted while
    # the fetch is still out.
    dialog.close()
    shiboken6.delete(dialog)
    assert shiboken6.isValid(dialog) is False, "precondition: the dialog is gone"

    _handle, on_done = pending.calls[0]
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        on_done((("fake/model-one",), ai_models.SOURCE_NETWORK))

    # The dead-widget access first: that is the defect (and its verbatim
    # RuntimeError), not just the bookkeeping below.
    _surface_apply_failure(caplog)
    assert handles == [], "a destroyed dialog must not keep the worker handle"


def test_destroying_the_dialog_clears_the_worker_handles(dialog_page):
    """The ``destroyed`` hook alone: no completion needed to drop the handles."""
    dialog, pending = dialog_page
    handles = dialog._gallery_ai_model_tasks
    assert len(handles) == 1, "precondition: the worker handle is kept alive"
    assert pending.calls, "precondition: a fetch was started"

    dialog.close()
    shiboken6.delete(dialog)

    assert handles == [], "a destroyed dialog must not keep the worker handle"


def test_completion_while_the_dialog_is_open_drops_the_finished_handle(dialog_page):
    dialog, pending = dialog_page
    handles = dialog._gallery_ai_model_tasks
    assert len(handles) == 1, "precondition: the worker handle is kept alive"

    _handle, on_done = pending.calls[0]
    on_done((("fake/model-one", "fake/model-two"), ai_models.SOURCE_NETWORK))

    assert handles == [], "a finished worker must not accumulate in the list"
    combo = dialog.gallery_ai_model_list
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "fake/model-one",
        "fake/model-two",
    ]
