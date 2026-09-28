"""Tests for the multi-compare Crop context-menu entry (parametric crop)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from tabs.multi_compare.context_menu import MultiCompareContextMenuProvider
from tabs.multi_compare.models import CompareSlot, LeafNode, MultiCompareState
from tabs.multi_compare.scene import MultiCompareStore
from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget


def _provider(slots, *, settings=None, controller=None):
    store = MultiCompareStore(
        MultiCompareState(slots=list(slots), root=None)
    )
    widget = SimpleNamespace(
        canvas=SimpleNamespace(pixel_cache=None),
        state=store.state,
        store=store,
        _translate=lambda _key, default=None: default or _key,
    )
    if settings is not None:
        widget.store = SimpleNamespace(
            dispatch=store.dispatch,
            settings=settings,
        )
        widget.state = store.state
    if controller is not None:
        widget._controller = controller
    return MultiCompareContextMenuProvider(widget), widget, store


def _request(canvas, slot_id):
    return ContextMenuRequest(
        source_widget=canvas,
        global_pos=QPoint(0, 0),
        local_pos=QPoint(0, 0),
        session_type="multi_compare",
        target=ContextMenuTarget(kind="multi_compare_slot", id=slot_id),
    )


def _crop_entry(provider, widget, slot_id):
    entries = provider.entries_for(_request(widget.canvas, slot_id))
    found = [e for e in entries if getattr(e, "action_id", "") == "multi_compare.crop_slot"]
    assert len(found) == 1
    return found[0]


def test_crop_entry_checked_reflects_effective_state(qapp):
    on = SimpleNamespace(auto_crop_black_borders=True)
    off = SimpleNamespace(auto_crop_black_borders=False)
    cases = [
        (CompareSlot(id=1, path=Path("a.png"), crop_override=True), on, True),
        (CompareSlot(id=1, path=Path("a.png"), crop_override=False), on, False),
        (CompareSlot(id=1, path=Path("a.png"), crop_override=None), on, True),
        (CompareSlot(id=1, path=Path("a.png"), crop_override=None), off, False),
    ]
    for slot, settings, want in cases:
        provider, widget, _store = _provider([slot], settings=settings)
        entry = _crop_entry(provider, widget, 1)
        assert entry.checkable is True
        assert bool(entry.checked) is want


def test_crop_execute_toggles_via_controller(qapp):
    calls = []

    class _Ctrl:
        def set_slot_crop_override(self, slot_id, value):
            calls.append((slot_id, value))

    slot = CompareSlot(id=7, path=Path("a.png"), crop_override=None)
    provider, widget, _store = _provider(
        [slot],
        settings=SimpleNamespace(auto_crop_black_borders=True),
        controller=_Ctrl(),
    )
    handled = provider.execute(
        "multi_compare.crop_slot", _request(widget.canvas, 7), 7
    )
    assert handled is True
    assert calls == [(7, False)]  # effective on -> explicit off


def test_crop_execute_falls_back_to_widget_dispatch(qapp):
    slot = CompareSlot(id=7, path=Path("a.png"), crop_override=False)
    provider, widget, store = _provider(
        [slot], settings=SimpleNamespace(auto_crop_black_borders=True)
    )
    handled = provider.execute(
        "multi_compare.crop_slot", _request(widget.canvas, 7), 7
    )
    assert handled is True
    updated = [s for s in store.state.slots if s.id == 7][0]
    assert updated.crop_override is True  # effective off -> explicit on


def test_unknown_action_not_handled(qapp):
    slot = CompareSlot(id=7, path=Path("a.png"))
    provider, widget, _store = _provider([slot])
    assert (
        provider.execute("multi_compare.nope", _request(widget.canvas, 7), 7)
        is False
    )


def test_crop_toggle_pathless_slot_is_noop(qapp):
    slot = CompareSlot(id=7, path=None)
    provider, widget, store = _provider(
        [slot], settings=SimpleNamespace(auto_crop_black_borders=True)
    )
    handled = provider.execute(
        "multi_compare.crop_slot", _request(widget.canvas, 7), 7
    )
    assert handled is True
    updated = [s for s in store.state.slots if s.id == 7][0]
    assert updated.crop_override is None  # imageless: Auto untouched
