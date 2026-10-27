"""IC open-image dialog must speak the DnD canon instead of its own suffix list.

The dialog entry (``presenters/toolbar/actions.py``) used to assemble its own
glob list — which offered ``.gif``, then outside the canon — and handed whatever
the dialog returned to ``load_images_from_paths`` with no suffix check at all.
One and the same file was accepted by the dialog and bounced by
DnD/chrome/carry — the exact drift class closed for ``.jxl`` in the 2026-08-25
C9 cross-module review, reappearing in the second entry point.

The refused example is :data:`REFUSED_SUFFIX`, a group-C suffix: ``.gif`` and
its relatives became ACCEPTED first-frame formats in the 2026-10-28 format
expansion, so they no longer illustrate a refusal. The rule under test is
unchanged — a suffix the canon refuses must be refused by the dialog too, and
the refusal must be an error event rather than a load attempt.

Two halves are pinned here, both against the canon rather than against the
source text:

* the filter actually handed to ``QFileDialog`` equals
  ``build_image_dialog_filter()`` (read off the patched dialog call, so a
  comment or a second constant cannot satisfy the test);
* the dialog verdict per suffix equals the DnD verdict (``has_image_urls`` for
  the drop-enter gate, ``is_loadable_image_path`` for the intake) and a refused
  pick never reaches the loader — it surfaces as an error event instead of a
  silent load attempt.

Headless-safe: ``QFileDialog`` and ``QTimer.singleShot`` are doubles, no real
dialog/window is created.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest

from shared.image_extensions import (
    ACCEPTED_IMAGE_EXTENSIONS,
    build_image_dialog_filter,
    has_image_urls,
    is_loadable_image_path,
)

#: What a refusal looks like now: a group-C format (``REJECTED_SUFFIXES`` in
#: ``shared/image_extensions``) the "All files" section can still hand back.
#: It is a PDF rather than the original ``.gif`` because sequence formats are
#: admitted as first-frame images since the 2026-10-28 format expansion.
REFUSED_SUFFIX = ".pdf"
REFUSED_NAME = f"probe{REFUSED_SUFFIX}"

# Every accepted suffix plus the two shapes the old hand-built list got wrong:
# a refused format offered anyway, and ``.txt``, which the "All files" section
# can still hand back.
SUFFIX_CASES = sorted(ACCEPTED_IMAGE_EXTENSIONS) + [REFUSED_SUFFIX, ".txt"]

LANGUAGES = ("en", "ru", "zh", "pt_BR")


class _Sessions:
    """Session-controller double: records the batches the dialog loads."""

    def __init__(self) -> None:
        self.loads: list[tuple[list[str], int]] = []

    def load_images_from_paths(self, paths, image_number: int) -> None:
        self.loads.append((list(paths), image_number))


class _Signal:
    """Stand-in for ``MainController.error_occurred`` / an EventBus."""

    def __init__(self) -> None:
        self.events: list = []

    def emit(self, event) -> None:
        self.events.append(event)


def _presenter(*, sessions=None, language: str = "en", bus=None):
    return SimpleNamespace(
        store=SimpleNamespace(
            settings=SimpleNamespace(
                export_default_dir="", current_language=language
            )
        ),
        main_window_app=None,
        main_controller=SimpleNamespace(sessions=sessions, error_occurred=_Signal()),
        event_bus=bus,
        _first_dialog_load_pending=True,
    )


def _patch_dialog(monkeypatch, selected: list[str]) -> dict:
    """Make ``QFileDialog`` return *selected* and record what it was given."""
    from PySide6.QtWidgets import QFileDialog

    seen: dict = {}

    def _fake(parent, caption, directory, filters, *args, **kwargs):
        seen["parent"] = parent
        seen["caption"] = caption
        seen["directory"] = directory
        seen["filters"] = filters
        return list(selected), ""

    monkeypatch.setattr(QFileDialog, "getOpenFileNames", _fake)
    return seen


def _open_dialog(monkeypatch, presenter) -> list:
    """Run the dialog entry, returning the deferred (QTimer) callbacks it queued."""
    from PySide6.QtCore import QTimer

    from tabs.image_compare.presenters.toolbar import actions as toolbar_actions

    deferred: list = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, fn: deferred.append(fn))
    toolbar_actions.open_image_dialog(presenter, 1)
    for step in deferred:
        step()
    return deferred


def _probe(tmp_path, suffix: str):
    """A real file on disk — ``is_loadable_image_path`` stats it."""
    path = tmp_path / f"probe{suffix}"
    path.write_bytes(b"")
    return path


def _handed_to_loader(sessions: _Sessions) -> list[str]:
    return [p for batch, _slot in sessions.loads for p in batch]


def _drop_verdict(path) -> bool:
    """What the DnD drop-enter gate says about this single local file."""
    from PySide6.QtCore import QMimeData, QUrl

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    return has_image_urls(mime)


# ---------------------------------------------------------------------------
# 1. The filter handed to QFileDialog is the canon's
# ---------------------------------------------------------------------------


def test_dialog_filter_is_the_canon_filter(monkeypatch):
    seen = _patch_dialog(monkeypatch, [])

    _open_dialog(monkeypatch, _presenter())

    assert seen["filters"] == build_image_dialog_filter()
    # The defect itself: the dialog offered a suffix no other entry takes.
    assert REFUSED_SUFFIX not in seen["filters"]


@pytest.mark.parametrize("language", LANGUAGES)
def test_dialog_filter_image_section_is_canon_in_every_language(
    language, monkeypatch
):
    """Localising the "All files" label must not smuggle in a local glob list."""
    canon_images = build_image_dialog_filter().split(";;")[0]
    seen = _patch_dialog(monkeypatch, [])

    _open_dialog(monkeypatch, _presenter(language=language))

    assert seen["filters"].split(";;")[0] == canon_images
    assert REFUSED_SUFFIX not in seen["filters"]


# ---------------------------------------------------------------------------
# 2. Dialog verdict == DnD verdict, per suffix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", SUFFIX_CASES)
def test_dialog_verdict_matches_the_loadable_predicate(suffix, tmp_path, monkeypatch):
    probe = _probe(tmp_path, suffix)
    sessions = _Sessions()
    _patch_dialog(monkeypatch, [str(probe)])

    _open_dialog(monkeypatch, _presenter(sessions=sessions))

    dialog_verdict = str(probe) in _handed_to_loader(sessions)
    assert dialog_verdict is is_loadable_image_path(probe), suffix
    assert dialog_verdict is _drop_verdict(probe), suffix


# ---------------------------------------------------------------------------
# 3. The refused pick is a refusal, not a load attempt
# ---------------------------------------------------------------------------


def test_a_group_c_pick_never_reaches_the_loader(tmp_path, monkeypatch):
    """Property, not example: a suffix the canon refuses is refused here too."""
    refused = _probe(tmp_path, REFUSED_SUFFIX)
    sessions = _Sessions()
    bus = _Signal()
    _patch_dialog(monkeypatch, [str(refused)])

    deferred = _open_dialog(monkeypatch, _presenter(sessions=sessions, bus=bus))

    assert sessions.loads == []  # never handed to load_images_from_paths
    assert deferred == []  # not even scheduled for the deferred load
    assert len(bus.events) == 1
    assert REFUSED_NAME in bus.events[0].error


def test_txt_through_the_dialog_never_reaches_the_loader(tmp_path, monkeypatch):
    txt = _probe(tmp_path, ".txt")
    sessions = _Sessions()
    bus = _Signal()
    _patch_dialog(monkeypatch, [str(txt)])

    _open_dialog(monkeypatch, _presenter(sessions=sessions, bus=bus))

    assert sessions.loads == []
    assert "probe.txt" in bus.events[0].error


def test_valid_png_still_loads_without_an_error(tmp_path, monkeypatch):
    png = _probe(tmp_path, ".png")
    sessions = _Sessions()
    bus = _Signal()
    _patch_dialog(monkeypatch, [str(png)])

    deferred = _open_dialog(monkeypatch, _presenter(sessions=sessions, bus=bus))

    assert sessions.loads == [([str(png)], 1)]
    assert bus.events == []
    assert len(deferred) == 1


def test_mixed_selection_loads_the_valid_files_and_reports_the_dropped(
    tmp_path, monkeypatch
):
    """Multiple selection survives: valid files load, rejects are named."""
    png = _probe(tmp_path, ".png")
    jpg = _probe(tmp_path, ".jpg")
    refused = _probe(tmp_path, REFUSED_SUFFIX)
    sessions = _Sessions()
    bus = _Signal()
    _patch_dialog(monkeypatch, [str(png), str(refused), str(jpg)])

    _open_dialog(monkeypatch, _presenter(sessions=sessions, bus=bus))

    assert sessions.loads == [([str(png), str(jpg)], 1)]
    assert len(bus.events) == 1
    assert REFUSED_NAME in bus.events[0].error
    assert "probe.png" not in bus.events[0].error
