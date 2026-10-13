"""B3: has-pixels / nothing-to-duplicate checks route through one shared predicate.

Pins the wave-B3 fan-out (plan-cross-cutting-policy-2026-10-13):

- ``tabs.multi_compare.pipeline.cache.slot_has_pixels`` is the single
  boolean gate (``resolve_slot_source`` stays the single tier read);
- ``tabs.multi_compare.ui.drag_drop.has_image_urls`` is the seam predicate
  (import swap — identity-pinned, including the non-local reject);
- ``context_menu._has_pixels`` and the DnD duplicate guards delegate to
  ``slot_has_pixels`` (no recomposed ``resolve(...) is not None``);
- the deferred-drop finish and ``begin_pending_paste`` filter through the
  seam ``is_loadable_image_path``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint

from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget
from tabs.multi_compare.models import CompareSlot, LeafNode


def _mime(urls):
    return SimpleNamespace(hasUrls=lambda: bool(urls), urls=lambda: list(urls))


def _url(*, local: bool, path: str):
    return SimpleNamespace(isLocalFile=lambda: local, toLocalFile=lambda: path)


def test_slot_has_pixels_table():
    """Single gate: pixels / imageless / missing cache / missing slot."""
    from tabs.multi_compare.pipeline.cache import slot_has_pixels

    sentinel = object()
    cache = SimpleNamespace(resolve=lambda p: sentinel if p else None)
    assert slot_has_pixels(cache, SimpleNamespace(path="/x/1.png", id=1)) is True
    assert slot_has_pixels(cache, SimpleNamespace(path=None, id=2)) is False
    assert slot_has_pixels(None, SimpleNamespace(path="/x/1.png", id=1)) is False
    assert slot_has_pixels(cache, None) is False


def test_drag_drop_has_image_urls_is_seam_predicate():
    """Import swap pin: the MC DnD name IS the seam object (no local copy)."""
    from shared import image_extensions as _seam
    from tabs.multi_compare.ui import drag_drop

    assert drag_drop.has_image_urls is _seam.has_image_urls
    # Behavior rides along: remote URLs rejected even with an image suffix.
    assert (
        drag_drop.has_image_urls(_mime([_url(local=False, path="/tmp/a.png")]))
        is False
    )
    assert (
        drag_drop.has_image_urls(_mime([_url(local=True, path="/tmp/a.png")]))
        is True
    )


def _mc_widget(slots, root, cache):
    return SimpleNamespace(
        canvas=SimpleNamespace(pixel_cache=cache),
        state=SimpleNamespace(slots=slots, root=root),
        store=SimpleNamespace(dispatch=lambda a: None),
        _translate=lambda key, default=None: default or key,
    )


def _mc_request(canvas, slot_id):
    return ContextMenuRequest(
        source_widget=canvas,
        global_pos=QPoint(0, 0),
        local_pos=QPoint(0, 0),
        session_type="multi_compare",
        target=ContextMenuTarget(kind="multi_compare_slot", id=slot_id),
    )


def test_menu_duplicate_enabled_tracks_shared_gate():
    """Menu enablement + ``_has_pixels`` read the shared gate (one resolve)."""
    from tabs.multi_compare.context_menu import MultiCompareContextMenuProvider

    sentinel = object()
    loaded = SimpleNamespace(resolve=lambda p: sentinel if p else None)
    widget = _mc_widget(
        [CompareSlot(id=1, path=Path("/x/1.png"), label="1")],
        LeafNode(1),
        loaded,
    )
    provider = MultiCompareContextMenuProvider(widget)
    assert provider._has_pixels(widget.state.slots[0]) is True
    dup = next(
        e
        for e in provider.entries_for(_mc_request(widget.canvas, 1))
        if getattr(e, "action_id", "") == "multi_compare.duplicate_slot"
    )
    assert dup.enabled is True

    empty_cache = SimpleNamespace(resolve=lambda p: None)
    widget.canvas.pixel_cache = empty_cache
    assert provider._has_pixels(widget.state.slots[0]) is False
    dup = next(
        e
        for e in provider.entries_for(_mc_request(widget.canvas, 1))
        if getattr(e, "action_id", "") == "multi_compare.duplicate_slot"
    )
    assert dup.enabled is False


def test_finish_external_drop_filters_via_seam(tmp_path: Path, monkeypatch):
    """Deferred finish keeps only seam-loadable paths (suffix ∧ is_file)."""
    from tabs.multi_compare.ui import drag_drop

    real = tmp_path / "a.png"
    real.write_bytes(b"\x89PNG\r\n\x1a\n")
    txt = tmp_path / "b.txt"
    txt.write_text("nope")
    ghost = tmp_path / "ghost.png"

    captured: dict = {}

    class _Queue:
        def enqueue(self, anchor, paths, widget, target, side):
            captured["paths"] = list(paths)
            return True

    monkeypatch.setattr(drag_drop, "get_drop_queue", lambda: _Queue())
    dispatched: list = []
    widget = SimpleNamespace(
        _dnd_gen=7,
        state=SimpleNamespace(root=None),
        store=SimpleNamespace(dispatch=dispatched.append),
    )
    drag_drop._finish_external_drop(
        widget, [str(real), str(txt), str(ghost)], None, 7, 0.0
    )
    assert captured["paths"] == [real]
    assert dispatched  # drag-clear dispatch still fires


def test_begin_pending_paste_rejects_non_image(tmp_path: Path, monkeypatch):
    """Paste arming admits seam-loadable paths only (parity with the finish)."""
    from tabs.multi_compare.ui import drag_drop

    txt = tmp_path / "b.txt"
    txt.write_text("nope")
    widget = SimpleNamespace(
        _pending_duplicate_source=None,
        _pending_paste_paths="sentinel",
        canvas=SimpleNamespace(
            removeEventFilter=lambda w: None, unsetCursor=lambda: None
        ),
        store=SimpleNamespace(dispatch=lambda a: None),
    )
    drag_drop.begin_pending_paste(widget, [txt])
    assert widget._pending_paste_paths is None

    real = tmp_path / "a.png"
    real.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(drag_drop, "arm_pending_placement_input", lambda w: None)
    monkeypatch.setattr(
        drag_drop, "update_pending_drag_preview", lambda w, pos, internal: None
    )
    monkeypatch.setattr(drag_drop, "canvas_cursor_pos", lambda w: None)
    drag_drop.begin_pending_paste(widget, [real, txt])
    assert widget._pending_paste_paths == [real]
