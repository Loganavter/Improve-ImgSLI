"""Session-picker card clicks replace the picker session atomically.

``SessionPickerWidget._create`` must go through a single
``replace_workspace_session`` store change (create the new session + close the
picker) instead of two separate changes. Two changes would make the workspace
UI sync to the intermediate session list — the adaptive tab strip would hold
both tabs for a frame before the picker tab is removed (the "two tabs in the
first frame" artifact). One atomic change means the picker tab is replaced in
place, so the strip never shows two tabs.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.session_picker.widget import SessionPickerWidget


class _PickerSession:
    def __init__(self) -> None:
        self.id = "picker-session"


class _Context:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._session = _PickerSession()

    def tr(self, key: str, default: str = "") -> str:
        return default or key

    def call_service(self, name: str, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if name == "list_session_blueprints":
            return ()
        if name == "get_tab_icon":
            return None
        return None

    def get_active_session(self):
        return self._session


def test_create_replaces_picker_via_single_atomic_change(qapp):
    ctx = _Context()
    widget = SessionPickerWidget(context=ctx)

    widget._create("image_compare")

    replace_calls = [c for c in ctx.calls if c[0] == "replace_workspace_session"]
    assert replace_calls == [
        ("replace_workspace_session", ("image_compare",), {"closing_session_id": "picker-session"})
    ]
    # No separate create/close services on the picker path: those two store
    # changes would leak an intermediate two-tab strip frame.
    assert not [c for c in ctx.calls if c[0] in ("create_workspace_session", "close_workspace_session")]
    widget.deleteLater()


def test_create_without_active_picker_still_replaces(qapp):
    ctx = _Context()
    ctx._session = None
    widget = SessionPickerWidget(context=ctx)

    widget._create("image_compare")

    replace_calls = [c for c in ctx.calls if c[0] == "replace_workspace_session"]
    assert replace_calls == [
        ("replace_workspace_session", ("image_compare",), {"closing_session_id": None})
    ]
    widget.deleteLater()