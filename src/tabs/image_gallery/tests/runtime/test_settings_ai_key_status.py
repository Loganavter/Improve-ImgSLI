"""The AI key verdict is ON SCREEN — not only in the log.

RED-BEFORE (the 2026-10-28 outage): the page reported nothing about the key.
The catalog combo showed 464 models (a PUBLIC endpoint — it answers 200 for a
dead key), the keyring held an 8-character stub, every judge call got
``HTTP 401: Missing Authentication header``, and the only trace was a WARNING
deep in ``log.txt``. The owner's report was literal: "по UX это тоже не
узнать".

This file pins the two halves of the fix at the widget level:

* the caption under the key field carries the probe verdict, including the
  provider's own words (``Key rejected: HTTP 401: …``), and
* the empty-key case says so without pretending a verdict was reached.

Offscreen and hermetic: the worker seam is captured instead of started (the
test fires the completion), the catalog fetch is injected, and both QSettings
groups are redirected.
"""

from __future__ import annotations

import pytest

from tabs.image_gallery.services import ai_key_check, ai_models

_STORE_GROUP = "image_gallery_ai_test_key_status"
_MODELS_GROUP = "image_gallery_ai_models_test_key_status"


class _PendingTasks:
    """A ``START_TASK`` stand-in: records ``(task, on_done)``, never runs it."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def start(self, task, on_done):
        handle = object()
        self.calls.append((handle, on_done))
        return handle


@pytest.fixture
def isolated_store(monkeypatch):
    from PySide6.QtCore import QSettings

    from tabs.image_gallery.services import ai_settings_store as store_module

    monkeypatch.setattr(store_module, "_QS_GROUP", _STORE_GROUP)
    monkeypatch.setattr(ai_models, "_QS_GROUP", _MODELS_GROUP)
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    for group in (_STORE_GROUP, _MODELS_GROUP):
        settings.remove(group)
    yield
    for group in (_STORE_GROUP, _MODELS_GROUP):
        settings.remove(group)


@pytest.fixture
def page(qapp, isolated_store, secret_store_keyring, monkeypatch):
    """A real settings dialog with only the gallery-AI page, tasks captured.

    The secret_store_keyring fixture is the declared opt-in: typing into the key field
    persists through ``core.secret_store`` (``save_field`` → ``secret-tool
    store``), which is exactly the shape that once wrote a stub over a real key.
    The fixture pins the write to the suite's throwaway keyring.
    """
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

    pending = _PendingTasks()

    def _fake_models_for(provider, api_key, *, refresh=False, report=None):
        if report is not None:
            report["reason"] = ai_models.REASON_OK
        return ("fake/model-one",), ai_models.SOURCE_NETWORK

    monkeypatch.setattr(settings_ai, "MODELS_FOR", _fake_models_for)
    monkeypatch.setattr(settings_ai, "START_TASK", pending.start)
    monkeypatch.setattr(settings_ai, "GALLERY_OWNER", lambda: None)
    # Never touch the network from a UI test: the probe seam answers instead.
    monkeypatch.setattr(
        ai_key_check,
        "HTTP_REQUEST",
        lambda *_a, **_k: (401, b'{"error": {"message": "Missing Authentication header"}}', ""),
    )

    dialog = SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=9999,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        active_tab="image_gallery",
    )
    yield dialog, pending
    dialog.close()
    dialog.deleteLater()


def _enter_key_check(dialog, pending) -> object:
    """Trigger a page entry and return the ``on_done`` of the KEY task.

    The catalog fetch is the first task the build starts; the key probe is the
    last one a page entry starts, so it is found by its completion contract
    (the fetch delivers ``(models, source)``, the probe a 3-tuple).
    """
    dialog.gallery_ai_api_key.setText("stub-key-8")
    before = len(pending.calls)
    dialog.section_shown.emit("image_gallery.ai")
    created = pending.calls[before:]
    assert created, "a page entry must start the key probe"
    _handle, on_done = created[-1]
    return on_done


def _caption(dialog):
    return dialog.gallery_ai_key_status.text()


def test_a_rejected_key_is_named_on_screen_with_the_provider_words(page):
    dialog, pending = page
    on_done = _enter_key_check(dialog, pending)
    on_done((False, ai_key_check.REASON_AUTH, "HTTP 401: Missing Authentication header"))
    caption = _caption(dialog)
    assert "Key rejected" in caption
    assert "HTTP 401" in caption
    assert "Missing Authentication header" in caption


def test_an_accepted_key_says_so(page):
    dialog, pending = page
    on_done = _enter_key_check(dialog, pending)
    on_done((True, ai_key_check.REASON_OK, ""))
    caption = _caption(dialog)
    assert "accepted" in caption.lower()
    assert "401" not in caption


def test_an_empty_key_is_its_own_verdict_not_a_silent_blank(page):
    dialog, pending = page
    dialog.gallery_ai_api_key.setText("")
    before = len(pending.calls)
    dialog.section_shown.emit("image_gallery.ai")
    on_done = pending.calls[before:][-1][1]
    on_done((False, ai_key_check.REASON_NO_KEY, "no key is stored"))
    caption = _caption(dialog)
    assert "No key" in caption


def test_a_newer_check_owns_the_row_so_a_slow_answer_cannot_overwrite_it(page):
    """A stale verdict from an earlier edit must never win the caption."""
    dialog, pending = page
    first = _enter_key_check(dialog, pending)
    second = _enter_key_check(dialog, pending)
    second((True, ai_key_check.REASON_OK, ""))
    first((False, ai_key_check.REASON_AUTH, "HTTP 401: stale"))
    caption = _caption(dialog)
    assert "accepted" in caption.lower()
    assert "401" not in caption, "the superseded probe overwrote the fresh verdict"
