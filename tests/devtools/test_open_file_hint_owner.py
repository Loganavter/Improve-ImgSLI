"""A placement hint must belong to the tab that reads it.

Measured live 2026-10-28 on a leased instance: ``open_file(path=…gif,
tab="image_compare", side="right")`` answered ``opened: true`` and put the file in
the **left** slot (``right_path`` stayed ``null``). Image Compare reads ``slot``;
``side`` is Multi Compare's key. ``drop_hint``'s docstring promises that an unknown
hint is the control surface's own error and "never a silently ignored drop", and it
enforces that for an unknown *value* — but the key/target mismatch slipped through.

The answer lives with the receiving **tab** (``TabContract.drop_hint_key``), not in
a table of tab names inside ``core/``: the first version of this fix kept such a
table and broke ``test_platform_isolation`` / ``test_ui_tab_sandbox`` in the very
same wave. ``route_paths`` asks each accepting tab which key it reads, before the
tab consumes anything, so a refused hint cannot half-load a file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.control.drop_routing import check_hint_owner, open_file_into, open_folder_into, route_paths


class _Tab:
    """Minimal drop target; the key is a CLASS attribute, like a real tab."""

    drop_hint_key: str | None = "slot"

    def __init__(self) -> None:
        self.dropped: list[tuple[list[Path], dict | None]] = []

    def accepts_drop(self, paths) -> bool:
        return True

    def handle_drop(self, paths, hint=None) -> bool:
        self.dropped.append((list(paths), hint))
        return True


class _SideTab(_Tab):
    drop_hint_key = "side"




def test_a_tab_declares_its_hint_key_as_a_class_attribute():
    """The answer lives with the tab, and it is a CLASS attribute on purpose.

    ``route_paths`` reads ``type(tab).drop_hint_key`` — a class lookup, never a
    property on a live widget: the sync-boundary contract forbids widget I/O on
    that path (a property read there was measured failing
    ``test_sync_boundary_purity``). The real tabs' values are asserted in their own
    suites (``src/tabs/*/tests``), which may import tab internals; this file may not.
    """
    from tabs.contract import TabContract

    assert TabContract.drop_hint_key is None
    assert isinstance(TabContract.__dict__["drop_hint_key"], str) is False


@pytest.mark.parametrize(
    "hint, hint_key",
    (
        ({"slot": 1}, "slot"),
        ({"slot": 2}, "slot"),
        ({"side": "left"}, "side"),
        ({"slot": 2}, None),  # a tab that takes no placement hint: pass-through
        (None, "slot"),
        (None, None),
    ),
)
def test_owned_hints_pass(hint, hint_key):
    check_hint_owner(hint, hint_key, "some_tab")


def test_a_foreign_hint_is_refused_by_name():
    with pytest.raises(ValueError) as excinfo:
        check_hint_owner({"side": "right"}, "slot", "image_compare")
    message = str(excinfo.value)
    assert "side=" in message and "image_compare reads slot=" in message.replace("takes", "reads") or (
        "side=" in message and "it takes slot=" in message
    )
    assert "opened=true" in message


def test_route_paths_refuses_before_the_tab_consumes_anything(tmp_path):
    path = tmp_path / "probe.png"
    path.write_bytes(b"x")
    tab = _Tab()

    with pytest.raises(ValueError, match="it takes slot="):
        route_paths([("image_compare", tab)], [path], hint={"side": "right"})
    assert tab.dropped == [], "a refused hint must never reach the tab"


def test_route_paths_still_forwards_a_owned_hint(tmp_path):
    path = tmp_path / "probe.png"
    path.write_bytes(b"x")
    tab = _SideTab()

    assert route_paths([("multi_compare", tab)], [path], hint={"side": "top"}) == "multi_compare"
    assert tab.dropped == [([path], {"side": "top"})]


def test_a_refused_hint_never_reaches_the_tab_through_open_file(tmp_path):
    path = tmp_path / "probe.png"
    path.write_bytes(b"x")

    tab = _Tab()

    with pytest.raises(ValueError, match="it takes slot="):
        open_file_into(
            path,
            wanted="image_compare",
            candidates=["image_compare"],
            tabs=lambda: [("image_compare", tab)],
            kinds=["image_compare", "multi_compare"],
            run_action=lambda action_id: None,
            hint={"side": "right"},
        )
    assert tab.dropped == [], "a refused hint must never reach the tab"


def test_open_folder_uses_the_same_rule(tmp_path):
    folder = tmp_path / "shots"
    folder.mkdir()
    tab = _SideTab()
    with pytest.raises(ValueError, match="it takes side="):
        open_folder_into(
            folder,
            "multi_compare",
            tabs=lambda: [("multi_compare", tab)],
            kinds=["image_compare", "multi_compare"],
            run_action=lambda action_id: None,
            hint={"slot": 1},
        )
    assert tab.dropped == []
