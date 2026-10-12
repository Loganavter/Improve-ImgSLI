"""Append-into-live-gallery processing UX (badge + toolbar spinner/count).

Falsification (two independent failures on the pre-fix build):
1. The append-attach branch (``open_paths`` with a live series) never stamped a
   local activity phase and never called ``set_background_scanning`` — the
   appended card showed no top-right pill and the toolbar showed no
   spinner/count, while a first load did.
2. Even when shown, the indicator was clobbered in the SAME event-loop turn:
   ``_apply_series_view`` ends in ``set_triage_done`` (widget ``set_triage`` +
   explicit call), so the spinner was hidden before it ever painted. The
   indicator must be raised AFTER ``_apply_series_view``.

Sibling mirrored: ``_start_triage`` -> ``_mark_local_pass(ANALYZING)`` +
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
    """Minimal widget double capturing the processing-UX surface + call order."""

    def __init__(self) -> None:
        self.folder_pick_requested = _SignalStub()
        self.analyze_requested = _SignalStub()
        self.filter_text_changed = _SignalStub()
        self.items = []
        self.events: list[tuple] = []
        self.triage_done = 0

    def set_folder_label(self, folder) -> None:
        pass

    def rebuild_grid(self, items) -> None:
        self.items = list(items)

    def refresh_card(self, item) -> None:
        pass

    def refresh_cards(self, items) -> None:
        self.events.append(("refresh", tuple(str(i.path) for i in items)))

    def set_card_visible(self, path, visible: bool) -> None:
        pass

    def set_triage(self, *a) -> None:
        self.events.append(("set_triage",))

    def set_scanning(self, *a) -> None:
        pass

    def set_background_scanning(self, n: int, total: int) -> None:
        self.events.append(("scan", int(n), int(total)))

    def set_triage_done(self) -> None:
        self.triage_done += 1
        self.events.append(("done",))

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

    def _apply_series_view(series) -> None:
        # Mimic the real tail: ``set_triage`` + an explicit ``set_triage_done``
        # (the S1 spinner retirement that used to clobber the append indicator).
        widget.set_triage(series, None, None)
        widget.set_triage_done()

    ctrl._apply_series_view = _apply_series_view  # type: ignore[method-assign]

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

    # Toolbar spinner + total count raised AFTER ``_apply_series_view``'s
    # ``set_triage_done`` — not clobbered in the same turn.
    assert ("scan", 0, 1) in widget.events, widget.events
    scan_idx = widget.events.index(("scan", 0, 1))
    done_idx = max(i for i, e in enumerate(widget.events) if e == ("done",))
    assert scan_idx > done_idx, widget.events
    assert widget.triage_done == 1  # only the view-tail's retirement so far
    assert widget.events[-1] == ("refresh", (str(b),))

    # Per-card activity pill stamped on the NEW item and its card refreshed.
    new_item = ctrl.state.items[-1]
    assert str(new_item.path) == str(b)
    assert activity_of(new_item)[0] == "analyzing"
    assert ("refresh", (str(b),)) in widget.events

    # Batch settles -> done fade + spinner retired.
    started["on_done"]()
    assert activity_of(new_item)[0] == "done"
    assert widget.triage_done == 2
    assert widget.events[-1] == ("done",)
