"""``open_folder`` drop hints — ``slot`` (Image Compare) / ``side`` (Multi Compare).

A mouse drop carries its target in the pointer position, so the drop path
reads a *hint* the host builds from the cursor. A headless control client has
no pointer, and before this contract it simply got the no-hint path: a pair
drop filled Image Compare's left slot only (``right_path: null``) and a folder
handed to Multi Compare stacked the images in the auto column instead of a
row. These tests pin the control-surface half of that contract:

* ``slot=1|2`` reaches the tab's own ``handle_drop`` as ``{"slot": n}`` and
  therefore Image Compare's left/right slot;
* ``side=left|right|top|bottom`` reaches the tab as ``{"side": s}`` (the tab
  half — side → ``load_external_paths`` → ``on_images_dropped`` — lives in
  ``src/tabs/multi_compare/tests/plugins/test_mc_handle_drop_side.py``);
* an unknown ``slot``/``side`` (or both at once) is the control surface's own
  ``MethodError`` — never a silently ignored drop;
* a tab whose ``handle_drop`` predates the hint parameter keeps working, and
  the no-hint call is byte-for-byte today's (one positional argument).

Falsification: every assertion below fails against an implementation that
validates but drops the hint, or that passes the hint as a second positional
to every tab (TypeError for older tabs). Runs offscreen — no display; the
tab-side behavior is proven against real ``MultiCompareTab`` objects in the
tab's own suite.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.control import drop_routing
from core.control.handlers import ControlHandlers, MethodError


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "series"
    folder.mkdir()
    for name in ("a.png", "b.jpg", "notes.txt"):
        (folder / name).write_bytes(b"x")
    return folder


class _HintTab:
    """Tab stand-in that understands the hint (its own ``handle_drop(paths, hint)``)."""

    def __init__(self, *, folders: bool = False) -> None:
        self.folders = folders
        self.dropped: list[tuple[list[Path], dict | None]] = []

    def accepts_drop(self, paths) -> bool:
        paths = list(paths)
        if paths and all(path.is_dir() for path in paths):
            return self.folders
        return True

    def handle_drop(self, paths, hint=None) -> bool:
        self.dropped.append((list(paths), hint))
        return True


class _PathsOnlyTab:
    """A tab (or fake) whose hook predates the hint parameter."""

    def __init__(self) -> None:
        self.calls = 0
        self.dropped: list[list[Path]] = []

    def accepts_drop(self, paths) -> bool:
        return True

    def handle_drop(self, paths) -> bool:
        self.calls += 1
        self.dropped.append(list(paths))
        return True


# -- routing -----------------------------------------------------------------


def test_route_paths_forwards_the_hint_to_the_tab(tmp_path) -> None:
    tab = _HintTab()
    files = [tmp_path / "a.png"]

    assert (
        drop_routing.route_paths([("multi_compare", tab)], files, hint={"side": "right"})
        == "multi_compare"
    )
    assert tab.dropped == [(files, {"side": "right"})]


def test_route_paths_without_a_hint_calls_handle_drop_with_paths_only(tmp_path) -> None:
    """No hint must be exactly the pre-hint call (no second argument)."""
    tab = _HintTab()
    files = [tmp_path / "a.png"]

    assert drop_routing.route_paths([("multi_compare", tab)], files) == "multi_compare"
    assert tab.dropped == [(files, None)]


def test_route_paths_still_feeds_a_tab_without_a_hint_parameter(tmp_path) -> None:
    tab = _PathsOnlyTab()
    files = [tmp_path / "a.png"]

    assert (
        drop_routing.route_paths([("image_compare", tab)], files, hint={"slot": 2})
        == "image_compare"
    )
    assert tab.dropped == [files]
    assert tab.calls == 1, "the hinted call must not apply the drop and then retry it"


def test_open_folder_into_forwards_the_hint_to_the_expanded_files(tmp_path) -> None:
    folder = _folder(tmp_path)
    tab = _HintTab()

    result = drop_routing.open_folder_into(
        folder,
        "multi_compare",
        tabs=lambda: [("multi_compare", tab)],
        kinds=["multi_compare"],
        run_action=lambda _action: pytest.fail("an open tab must not be recreated"),
        hint={"side": "right"},
    )

    assert result["images"] == 2
    paths, hint = tab.dropped[-1]
    assert [p.name for p in paths] == ["a.png", "b.jpg"]
    assert hint == {"side": "right"}


def test_open_folder_into_without_a_hint_sends_none(tmp_path) -> None:
    folder = _folder(tmp_path)
    tab = _HintTab()

    drop_routing.open_folder_into(
        folder,
        "multi_compare",
        tabs=lambda: [("multi_compare", tab)],
        kinds=["multi_compare"],
        run_action=lambda _action: None,
    )

    assert tab.dropped[-1][1] is None


def test_drop_hint_is_none_when_unset() -> None:
    assert drop_routing.drop_hint({}) is None
    assert drop_routing.drop_hint({"path": "/tmp"}) is None


# -- the control handler -----------------------------------------------------


def _handlers(*tabs: tuple[str, object]) -> ControlHandlers:
    registry = SimpleNamespace(all_actions=lambda: [], get=lambda _action_id: None)
    handlers = ControlHandlers(
        window=SimpleNamespace(store=None), registry_provider=lambda: registry
    )
    handlers._tabs = lambda: list(tabs)
    handlers._tab_kinds = lambda: ["image_compare", "multi_compare"]
    return handlers


@pytest.mark.parametrize("params", [{"slot": 3}, {"slot": 0}, {"slot": "left"}])
def test_open_folder_rejects_an_unknown_slot(tmp_path, params) -> None:
    tab = _HintTab()
    handlers = _handlers(("image_compare", tab))

    with pytest.raises(MethodError) as exc:
        handlers.open_folder({"path": str(tmp_path), "tab": "image_compare", **params})

    assert "unknown slot" in exc.value.message
    assert "slot=1" in exc.value.hint
    assert tab.dropped == [], "a rejected hint must never reach the tab"


@pytest.mark.parametrize("side", ["middle", "Left", ""])
def test_open_folder_rejects_an_unknown_side(tmp_path, side) -> None:
    tab = _HintTab()
    handlers = _handlers(("multi_compare", tab))

    with pytest.raises(MethodError) as exc:
        handlers.open_folder({"path": str(tmp_path), "tab": "multi_compare", "side": side})

    assert "unknown side" in exc.value.message
    assert tab.dropped == []


def test_open_folder_rejects_slot_and_side_together(tmp_path) -> None:
    tab = _HintTab()
    handlers = _handlers(("multi_compare", tab))

    with pytest.raises(MethodError) as exc:
        handlers.open_folder(
            {"path": str(tmp_path), "tab": "multi_compare", "slot": 1, "side": "right"}
        )

    assert "not both" in exc.value.message
    assert tab.dropped == []


@pytest.mark.parametrize(
    "tab_kind, params, expected",
    [
        ("image_compare", {"slot": 2}, {"slot": 2}),
        ("image_compare", {"slot": "1"}, {"slot": 1}),
        ("multi_compare", {"side": "right"}, {"side": "right"}),
    ],
)
def test_open_folder_hands_the_hint_to_the_tab(tmp_path, tab_kind, params, expected) -> None:
    folder = _folder(tmp_path)
    tab = _HintTab()
    handlers = _handlers((tab_kind, tab))

    result = handlers.open_folder({"path": str(folder), "tab": tab_kind, **params})

    assert result == {
        "routed": True,
        "path": str(folder),
        "tab": tab_kind,
        "images": 2,
    }
    assert tab.dropped[-1][1] == expected


def test_open_folder_auto_route_also_carries_the_hint(tmp_path) -> None:
    """No ``tab=``: the auto-route still passes the hint to the tab it lands on."""
    folder = _folder(tmp_path)
    tab = _HintTab(folders=True)  # folder-native: takes the directory itself
    handlers = _handlers(("image_gallery", tab))

    result = handlers.open_folder({"path": str(folder), "slot": 2})

    assert result == {"routed": True, "path": str(folder), "tab": "image_gallery"}
    assert tab.dropped == [([folder], {"slot": 2})]
