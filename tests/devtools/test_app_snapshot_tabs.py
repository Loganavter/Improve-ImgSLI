"""``get_state`` tab-scoped assertion slices (P4, plan-mcp-agent-ergonomics).

An agent must be able to assert *in-channel* what the UI shows — "Quick Look
shows image N", "gallery has this selection", "compare is on the left image" —
without overlay labels or a tracer enabled at app start. The slices are read
through the existing ``get_state {path}`` tool, so there is no new MCP tool.

Falsification (written first, red against the pre-slice tree): on that tree
``tabs.*`` does not exist, so every path below raises ``MethodError``.

Values live in the injected state/window (session slots + the live tab widget).
The sentinels are deliberately NOT derivable from the gallery pool, so a
re-derived guess cannot pass: selection is one pool path but reported verbatim,
and the open Quick Look item is a path that is absent from the pool entirely.
"""

from __future__ import annotations

import types

import pytest

from core.control.handlers import ControlHandlers, MethodError


def _item(path: str, *, metrics=None):
    return types.SimpleNamespace(
        path=path, metrics=dict(metrics or {}), status="done"
    )


def _gallery_slot():
    return types.SimpleNamespace(
        items=[_item("/pool/a.png"), _item("/pool/b.png", metrics={"ssim": 0.9})],
        selection=["/pool/b.png"],
        filter_text="rank>1",
        folder="/pool",
    )


class _Viewport:
    def __init__(self, zoom, pan_x, pan_y):
        self._view = (zoom, pan_x, pan_y)

    def current_view(self):
        return self._view


def _quick_look_overlay():
    overlay = types.SimpleNamespace(
        _current_item=_item("/ql/current-not-in-pool.png"),
        _series_items=[_item("/ql/s1.png"), _item("/ql/current-not-in-pool.png"), _item("/ql/s3.png")],
        _current_idx=1,
        _source_path="/ql/source-other.png",
        _preview_canvas=_Viewport(2.75, 12.0, -4.0),
    )
    overlay.isVisible = lambda: True  # type: ignore[assignment]
    return overlay


def _gallery_widget():
    controller = types.SimpleNamespace(
        _judgment_domain="ai",
        state=types.SimpleNamespace(
            items=[_item("/pool/a.png"), _item("/pool/b.png", metrics={"ssim": 0.9})]
        ),
    )
    return types.SimpleNamespace(
        _quick_look_overlay=_quick_look_overlay(),
        toolbar=types.SimpleNamespace(sort_text="Sort: AI quality"),
        _controller=controller,
    )


class _Session:
    def __init__(self, session_id, session_type, *, document=None, viewport=None):
        self.id = session_id
        self.session_type = session_type
        self.document = document
        self.viewport = viewport


class _Store:
    """Duck-typed Store: the three members ``app_snapshot`` actually reads."""

    def __init__(self, session, slots=None):
        self.session = session
        self.slots = dict(slots or {})

    def get_active_workspace_session(self):
        return self.session

    def get_session_state_slot(self, name, *, session_id=None, default=None):
        if session_id not in (None, self.session.id):
            return default
        return self.slots.get(name, default)


def _handlers(store, widgets=None):
    window = types.SimpleNamespace(store=store)
    handlers = ControlHandlers(window=window, artifacts_dir=None)
    tabs = [
        (session_type, types.SimpleNamespace(widget=widget))
        for session_type, widget in (widgets or {}).items()
    ]
    handlers._tabs = lambda: tabs  # type: ignore[assignment]
    return handlers


def _gallery_store(active=True):
    gallery_slot = _gallery_slot()
    chrome = {"judgment_domain": "algorithms", "view_list": False}
    session = (
        _Session("sess-gallery", "image_gallery")
        if active
        else _Session("sess-picker", "session_picker")
    )
    return _Store(
        session,
        {
            "gallery": gallery_slot,
            "image_gallery": chrome,
            "multi_compare.state": types.SimpleNamespace(
                slots=[
                    types.SimpleNamespace(id=1, path="/mc/one.png"),
                    types.SimpleNamespace(id=2, path=None),
                    types.SimpleNamespace(id=3, path="/mc/three.png"),
                ],
                focused_slot_id=3,
                slot_count=lambda: 3,
            ),
        },
    )


DOCUMENTED_KEYS = {
    "tabs.image_gallery": {
        "active",
        "folder",
        "item_count",
        "selection",
        "selection_count",
        "filter_text",
        "sort",
        "judgment_domain",
        "metrics_cache_size",
        "quick_look",
    },
    "tabs.image_gallery.quick_look": {
        "active",
        "open",
        "path",
        "index",
        "total",
        "zoom",
        "pan",
        "source_side",
    },
    "tabs.image_compare": {
        "active",
        "left_path",
        "right_path",
        "mode",
        "split_ratio",
        "diff_mode",
    },
    "tabs.multi_compare": {"active", "slot_count", "filled", "focused_slot"},
}


@pytest.mark.parametrize("path", sorted(DOCUMENTED_KEYS))
def test_documented_tab_paths_return_their_keys(path):
    handlers = _handlers(_gallery_store(), {"image_gallery": _gallery_widget()})

    result = handlers.get_state({"path": path})

    assert result["path"] == path
    assert set(result["state"]) == DOCUMENTED_KEYS[path]


def test_closed_tabs_report_inactive_with_nulls_never_an_exception():
    handlers = _handlers(_gallery_store(active=False))

    for path in sorted(DOCUMENTED_KEYS):
        state = handlers.get_state({"path": path})["state"]
        assert state["active"] is False, path
        for key, value in state.items():
            if key in ("active", "quick_look"):
                continue
            assert value is None, (path, key, value)

    quick_look = handlers.get_state({"path": "tabs.image_gallery.quick_look"})["state"]
    assert quick_look["open"] is None
    assert quick_look["path"] is None and quick_look["zoom"] is None


def test_active_gallery_with_closed_quick_look_reports_open_false():
    widget = _gallery_widget()
    widget._quick_look_overlay.isVisible = lambda: False  # type: ignore[assignment]
    handlers = _handlers(_gallery_store(), {"image_gallery": widget})

    state = handlers.get_state({"path": "tabs.image_gallery.quick_look"})["state"]

    assert state["active"] is True
    assert state["open"] is False
    assert state["path"] is None and state["index"] is None and state["total"] is None
    assert state["zoom"] is None and state["pan"] is None and state["source_side"] is None


def test_gallery_values_come_from_the_injected_state_not_a_rederivation():
    handlers = _handlers(_gallery_store(), {"image_gallery": _gallery_widget()})

    state = handlers.get_state({"path": "tabs.image_gallery"})["state"]

    assert state["active"] is True
    assert state["folder"] == "/pool"
    assert state["item_count"] == 2
    assert state["selection"] == ["/pool/b.png"]
    assert state["selection_count"] == 1
    assert state["filter_text"] == "rank>1"
    assert state["sort"] == "Sort: AI quality"
    # Live controller teardown wins over the chrome-slot mirror.
    assert state["judgment_domain"] == "ai"
    assert state["metrics_cache_size"] == 1


def test_quick_look_values_come_from_the_overlay_not_the_pool():
    handlers = _handlers(_gallery_store(), {"image_gallery": _gallery_widget()})

    state = handlers.get_state({"path": "tabs.image_gallery.quick_look"})["state"]

    assert state["open"] is True
    # The open item is NOT in the gallery pool: a re-derived answer would say None.
    assert state["path"] == "/ql/current-not-in-pool.png"
    assert state["index"] == 1
    assert state["total"] == 3
    assert state["zoom"] == 2.75
    assert state["pan"] == [12.0, -4.0]
    assert state["source_side"] == "inset"


def test_image_compare_and_multi_compare_read_their_own_session_state():
    view = types.SimpleNamespace(
        split_position=0.42,
        diff_mode="highlight",
        showing_single_image_mode=2,
    )
    document = types.SimpleNamespace(
        image1_path="/cmp/left.png", image2_path="/cmp/right.png"
    )
    store = _Store(
        _Session(
            "sess-cmp",
            "image_compare",
            document=document,
            viewport=types.SimpleNamespace(view_state=view),
        ),
        {
            "multi_compare.state": types.SimpleNamespace(
                slots=[
                    types.SimpleNamespace(id=1, path="/mc/one.png"),
                    types.SimpleNamespace(id=2, path=None),
                    types.SimpleNamespace(id=3, path="/mc/three.png"),
                ],
                focused_slot_id=3,
                slot_count=lambda: 3,
            )
        },
    )
    handlers = _handlers(store)

    compare = handlers.get_state({"path": "tabs.image_compare"})["state"]
    assert compare == {
        "active": True,
        "left_path": "/cmp/left.png",
        "right_path": "/cmp/right.png",
        "mode": 2,
        "split_ratio": 0.42,
        "diff_mode": "highlight",
    }

    # Not the active session → the multi-compare slice is closed, not guessed.
    multi = handlers.get_state({"path": "tabs.multi_compare"})["state"]
    assert multi == {
        "active": False,
        "slot_count": None,
        "filled": None,
        "focused_slot": None,
    }


def test_unknown_path_keeps_the_existing_error_behaviour():
    handlers = _handlers(_gallery_store(), {"image_gallery": _gallery_widget()})

    with pytest.raises(MethodError):
        handlers.get_state({"path": "tabs.image_gallery.nope"})
    with pytest.raises(MethodError):
        handlers.get_state({"path": "settings.nope"})


def test_existing_state_paths_are_unchanged():
    handlers = _handlers(_gallery_store(), {"image_gallery": _gallery_widget()})

    whole = handlers.get_state({})["state"]
    assert {"settings", "workspace", "document"} <= set(whole)
    assert handlers.get_state({"path": "document"})["state"] == whole["document"]
