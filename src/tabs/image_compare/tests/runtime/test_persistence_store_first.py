"""Store-first persistence: snapshot/restore must not roundtrip widget state.

Regression: "file names enabled" lived in two places — the Store's
``viewport.render_config.include_file_names_in_saved`` (SSOT) and the side
slot ``ImageCompareState.show_file_names`` fed from
``widget.btn_file_names.isChecked()``. On restart the stale side slot
unchecked the button while the restored Store enabled the edit panel.
Caption-editor texts were likewise persisted via widget ``.text()`` while
``DocumentModel`` display names are the real source.
"""

from __future__ import annotations

import os
from contextlib import nullcontext
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.contract import TabContext
from tabs.image_compare.models import ImageCompareState
from tabs.image_compare.use_cases import persistence


class _RecBtn:
    def __init__(self, checked: bool = False):
        self._checked = checked
        self.isChecked_calls = 0
        self.setChecked_calls: list[bool] = []

    def isChecked(self):
        self.isChecked_calls += 1
        return self._checked

    def setChecked(self, value):
        self.setChecked_calls.append(bool(value))


class _RecEdit:
    def __init__(self, text: str = ""):
        self._text = text
        self.text_calls = 0
        self.setText_calls: list[str] = []

    def text(self):
        self.text_calls += 1
        return self._text

    def setText(self, value):
        self.setText_calls.append(value)


def _rec_widget(**overrides):
    widget = SimpleNamespace(
        image_label=None,
        btn_file_names=_RecBtn(False),
        edit_name1=_RecEdit("stale-1"),
        edit_name2=_RecEdit("stale-2"),
    )
    for key, value in overrides.items():
        setattr(widget, key, value)
    return widget


class _Session:
    def __init__(self, session_id: str, *, document=None, viewport=None):
        self.id = session_id
        self.session_type = "image_compare"
        self.document = document
        self.viewport = viewport
        self.state_slots: dict = {}


class _Store:
    """Minimal fake covering the slot APIs persistence.py uses."""

    def __init__(self, sessions: dict | None = None, *, flag: bool = False):
        self._sessions = sessions or {}
        self.viewport = SimpleNamespace(
            render_config=SimpleNamespace(include_file_names_in_saved=flag)
        )

    def get_workspace_session(self, session_id):
        return self._sessions.get(session_id)

    def get_active_workspace_session(self):
        return None

    def get_session_state_slot(self, slot, *, session_id=None, default=None):
        session = self._sessions.get(session_id) if session_id else None
        if session is None:
            return default
        return session.state_slots.get(slot, default)

    def set_session_state_slot(self, slot, value, *, session_id=None, emit_scope=None):
        session = self._sessions.get(session_id) if session_id else None
        if session is None:
            return
        if slot == "document":
            session.document = value
        else:
            session.state_slots[slot] = value

    def ensure_session_state_slot(self, slot, *, session_id=None, factory=None):
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if slot == "document":
            return session.document
        existing = session.state_slots.get(slot)
        if existing is None and factory is not None:
            existing = factory()
            session.state_slots[slot] = existing
        return existing

    def get_dispatcher(self):
        return None

    def batch_changes(self):
        return nullcontext()


class _Tab:
    session_type = "image_compare"

    def __init__(self, widget=None, active_session_id=None):
        self._widget = widget
        self._active_session_id = active_session_id


def test_snapshot_never_reads_widget_state():
    """Widget disagrees with the Store — snapshot must not consult it."""
    session = _Session("s1")
    store = _Store({"s1": session}, flag=True)
    widget = _rec_widget()
    tab = _Tab(widget, "s1")

    persistence.snapshot_into(tab, TabContext(store=store), "s1")

    assert widget.btn_file_names.isChecked_calls == 0
    assert widget.edit_name1.text_calls == 0
    assert widget.edit_name2.text_calls == 0
    # Only the camera is captured; the Store flag is the SSOT, untouched.
    slot = session.state_slots[persistence._STATE_SLOT]
    assert isinstance(slot, ImageCompareState)
    assert (slot.zoom, slot.pan_x, slot.pan_y) == (1.0, 0.0, 0.0)
    assert store.viewport.render_config.include_file_names_in_saved is True
    assert not hasattr(slot, "show_file_names")
    assert not hasattr(slot, "edit_name_1")


def test_restore_performs_zero_widget_writes_but_applies_camera():
    session = _Session("s1")
    session.state_slots[persistence._STATE_SLOT] = ImageCompareState(
        zoom=2.0, pan_x=5.0, pan_y=-3.0
    )
    store = _Store({"s1": session})
    widget = _rec_widget()
    tab = _Tab(widget, "s1")
    cameras: list[tuple[float, float, float]] = []
    real = persistence.apply_camera_to_host
    try:
        persistence.apply_camera_to_host = (  # type: ignore[method-assign]
            lambda t, z, x, y: cameras.append((z, x, y))
        )
        persistence.restore_from(tab, TabContext(store=store), "s1")
    finally:
        persistence.apply_camera_to_host = real  # type: ignore[method-assign]

    assert widget.btn_file_names.setChecked_calls == []
    assert widget.edit_name1.setText_calls == []
    assert widget.edit_name2.setText_calls == []
    assert cameras == [(2.0, 5.0, -3.0)]


def _deserialize_store(session_id: str = "s1") -> _Store:
    from core.store_viewport import ViewportState

    return _Store({session_id: _Session(session_id, viewport=ViewportState())})


def _v2_data() -> dict:
    return {
        "version": 2,
        "image_list1": [{"path": "/a.png", "display_name": "a", "rating": 0}],
        "image_list2": [{"path": "/b.png", "display_name": "b", "rating": 1}],
        "current_index1": 0,
        "current_index2": 0,
        "show_file_names": True,
        "edit_name_1": "Left",
        "edit_name_2": "Right",
        "camera": {"zoom": 1.5, "pan_x": 2.0, "pan_y": 3.0},
    }


def test_deserialize_accepts_v2_ignoring_legacy_keys():
    store = _deserialize_store()
    tab = _Tab(_rec_widget(), active_session_id="other")

    persistence.deserialize_session(tab, "s1", _v2_data(), TabContext(store=store))

    session = store.get_workspace_session("s1")
    assert session.document.image_list1[0].display_name == "a"
    slot = session.state_slots[persistence._STATE_SLOT]
    assert (slot.zoom, slot.pan_x, slot.pan_y) == (1.5, 2.0, 3.0)
    assert not hasattr(slot, "show_file_names")


def test_deserialize_accepts_v3():
    store = _deserialize_store()
    tab = _Tab(_rec_widget(), active_session_id="other")
    data = _v2_data()
    data.pop("show_file_names")
    data.pop("edit_name_1")
    data.pop("edit_name_2")
    data["version"] = 3

    persistence.deserialize_session(tab, "s1", data, TabContext(store=store))

    session = store.get_workspace_session("s1")
    assert session.document.image_list2[0].display_name == "b"
    slot = session.state_slots[persistence._STATE_SLOT]
    assert (slot.zoom, slot.pan_x, slot.pan_y) == (1.5, 2.0, 3.0)


def test_serialize_emits_v3_without_legacy_keys():
    from core.store_viewport import ViewportState

    from tabs.image_compare.state.document import DocumentModel, ImageItem

    doc = DocumentModel(
        image_list1=[ImageItem(path="/a.png", display_name="a")],
        image_list2=[],
        current_index1=0,
        current_index2=-1,
    )
    store = _Store(
        {"s1": _Session("s1", document=doc, viewport=ViewportState())}
    )
    tab = _Tab(_rec_widget(), active_session_id="s1")

    blob = persistence.serialize_session(tab, "s1", TabContext(store=store))

    assert blob is not None
    assert blob["version"] == 3
    assert "show_file_names" not in blob
    assert "edit_name_1" not in blob
    assert "edit_name_2" not in blob


def test_apply_host_session_mode_follows_store_not_widget():
    from tabs.image_compare.tab import ImageCompareTab

    tab = ImageCompareTab()
    toggled: list[bool] = []
    widget = SimpleNamespace(
        toggle_edit_layout_visibility=lambda v: toggled.append(bool(v)),
        btn_file_names=_RecBtn(False),
    )
    tab._widget = widget
    ui = SimpleNamespace(
        store=SimpleNamespace(
            viewport=SimpleNamespace(
                render_config=SimpleNamespace(include_file_names_in_saved=True)
            )
        )
    )

    assert tab.apply_host_session_mode(ui) is True
    assert toggled == [True]
    assert widget.btn_file_names.isChecked_calls == 0
