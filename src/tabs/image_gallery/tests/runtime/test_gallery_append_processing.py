"""Append-into-live-gallery processing UX (badge + toolbar spinner/count).

Falsification: BEFORE the fix the append-attach branch (``open_paths`` with a
live series) never stamped a local activity phase and never called
``set_background_scanning`` — so the appended card showed no top-right pill and
the toolbar showed no spinner/count, while a first load did. This test fails on
that build: ``on_done`` is not wired in and both observables stay empty.

Sibling being mirrored: ``_start_triage`` -> ``_mark_local_pass(ANALYZING)`` +
``set_scanning``/``set_background_scanning`` (the working first-load path).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryState, TriageState
from tabs.image_gallery.services.activity import activity_of
from tabs.image_gallery.tests._gallery_dispatch_doubles import make_gallery_context


class _SignalStub:
    def __init__(self) -> None:
        self._slots = []

    def connect(self, fn) -> None:
        self._slots.append(fn)

    def emit(self, *a, **kw) -> None:
        for fn in self._slots:
            fn(*a, **kw)


class _ProcessingWidgetStub:
    """Minimal widget double capturing the processing-UX surface."""

    def __init__(self) -> None:
        self.folder_pick_requested = _SignalStub()
        self.analyze_requested = _SignalStub()
        self.filter_text_changed = _SignalStub()
        self.items = []
        self.background_scanning: list[tuple[int, int]] = []
        self.refreshed: list[list[str]] = []
        self.triage_done = 0

    def set_folder_label(self, folder) -> None:
        pass

    def rebuild_grid(self, items) -> None:
        self.items = list(items)

    def refresh_card(self, item) -> None:
        pass

    def refresh_cards(self, items) -> None:
        self.refreshed.append([str(i.path) for i in items])

    def set_card_visible(self, path, visible: bool) -> None:
        pass

    def set_triage(self, *a) -> None:
        pass

    def set_scanning(self, *a) -> None:
        pass

    def set_background_scanning(self, n: int, total: int) -> None:
        self.background_scanning.append((int(n), int(total)))

    def set_triage_done(self) -> None:
        self.triage_done += 1

    def pick_folder_dialog(self, start_dir: str = ""):
        return None


def _img(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x00")
    return p


def test_append_into_live_series_shows_processing_badge_and_count(tmp_path: Path) -> None:
    widget = _ProcessingWidgetStub()
    context, _store = make_gallery_context()
    ctrl = GalleryController(
        widget, thread_pool=QThreadPool.globalInstance(), context=context
    )
    started: dict = {}

    ctrl._start_triage = lambda items, **kw: None  # type: ignore[method-assign]
    ctrl._load_thumbnail = lambda item, **kw: None  # type: ignore[method-assign]
    ctrl._attach_append_items = lambda new: {}  # type: ignore[method-assign]
    ctrl._cluster_tail_into_series = lambda: []  # type: ignore[method-assign]
    ctrl._apply_series_view = lambda series: None  # type: ignore[method-assign]

    def _proxy(items, source, mode, *, on_done=None) -> None:  # type: ignore[no-untyped-def]
        started["items"] = [str(i.path) for i in items]
        started["on_done"] = on_done

    ctrl._start_proxy_analysis = _proxy  # type: ignore[method-assign]

    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")

    # First load establishes the pool (cover-grid path, stubbed).
    ctrl.open_paths([a])
    first = ctrl.state.items[0]
    # Seed a live grouped view so the next drop takes the append-attach branch.
    ctrl.state = GalleryState(items=[first], series=[[first]], triage_state=TriageState.DONE)

    ctrl.open_paths([b])

    # Attach branch ran: Stage-2 proxied for the NEW item only, with a done hook.
    assert started["items"] == [str(b)]
    assert callable(started["on_done"])

    # Toolbar spinner + total count mirrored from the first-load path.
    assert widget.background_scanning[-1] == (0, 1)

    # Per-card activity pill stamped on the NEW item and its card refreshed.
    new_item = ctrl.state.items[-1]
    assert str(new_item.path) == str(b)
    assert activity_of(new_item)[0] == "analyzing"
    assert widget.refreshed[-1] == [str(b)]

    # Batch settles -> done fade + spinner retired.
    started["on_done"]()
    assert activity_of(new_item)[0] == "done"
    assert widget.triage_done == 1
