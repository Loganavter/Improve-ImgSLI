"""``core.control.drop_routing`` — feeding a tab without a live app.

Falsification: the rules that let the control surface feed a *file-only* tab
(``multi_compare``) did not exist — its "add images" QFileDialog was the only
entry point and a headless client cannot drive it (no element ids for the
list rows, and the dialog window never maps). Pinned here:

- a folder is offered as a folder first (gallery-native tabs scan it);
- a tab that does not accept the paths is skipped, not forced;
- a file-only tab receives the folder's images as files (shared extension
  set, name-sorted);
- a missing tab is created once through its own ``workspace.new_<kind>``
  action and the list is re-read afterwards;
- an unknown kind or a tab that accepts nothing raises ``ValueError``
  (the caller maps it to the control surface's error type).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.control import drop_routing


class _Tab:
    """Tab stand-in with exactly the accept/drop contract the router uses."""

    def __init__(self, *, folders: bool = True, files: bool = True, returns: bool = True) -> None:
        self.folders = folders
        self.files = files
        self.returns = returns
        self.dropped: list[list[Path]] = []

    def accepts_drop(self, paths) -> bool:
        paths = list(paths)
        if paths and all(path.is_dir() for path in paths):
            return self.folders
        return self.files

    def handle_drop(self, paths) -> bool:
        self.dropped.append(list(paths))
        return self.returns


def _folder(tmp_path: Path) -> Path:
    for name in ("b.png", "a.jpg", "notes.txt", "c.webp"):
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


def test_folder_image_paths_is_images_only_and_name_sorted(tmp_path) -> None:
    assert [p.name for p in drop_routing.folder_image_paths(_folder(tmp_path))] == [
        "a.jpg",
        "b.png",
        "c.webp",
    ]


def test_folder_image_paths_missing_folder_is_empty(tmp_path) -> None:
    assert drop_routing.folder_image_paths(tmp_path / "nope") == []


def test_route_paths_skips_non_accepting_and_returns_the_taker(tmp_path) -> None:
    folder = _folder(tmp_path)
    mc = _Tab(folders=False)  # file-only, like multi_compare: rejects the directory
    gallery = _Tab()  # folder-native
    tabs = [("multi_compare", mc), ("image_gallery", gallery)]

    assert drop_routing.route_paths(tabs, [folder]) == "image_gallery"
    assert mc.dropped == [], "a non-accepting tab is never handed the paths"
    assert gallery.dropped == [[folder]]


def test_route_paths_only_filters_by_session_type(tmp_path) -> None:
    folder = _folder(tmp_path)
    gallery = _Tab()
    mc = _Tab()

    assert drop_routing.route_paths([("image_gallery", gallery), ("multi_compare", mc)], [folder], only="multi_compare") == "multi_compare"
    assert gallery.dropped == []


def test_open_folder_into_expands_a_file_only_tab(tmp_path) -> None:
    folder = _folder(tmp_path)
    mc = _Tab(folders=False)
    result = drop_routing.open_folder_into(
        folder,
        "multi_compare",
        tabs=lambda: [("multi_compare", mc)],
        kinds=["image_gallery", "multi_compare"],
        run_action=lambda _action: pytest.fail("an open tab must not be recreated"),
    )

    assert result == {"routed": True, "path": str(folder), "tab": "multi_compare", "images": 3}
    assert [p.name for p in mc.dropped[-1]] == ["a.jpg", "b.png", "c.webp"]


def test_open_folder_into_sends_the_directory_to_a_folder_native_tab(tmp_path) -> None:
    folder = _folder(tmp_path)
    gallery = _Tab()
    result = drop_routing.open_folder_into(
        folder,
        "image_gallery",
        tabs=lambda: [("image_gallery", gallery)],
        kinds=["image_gallery", "multi_compare"],
        run_action=lambda _action: pytest.fail("an open tab must not be recreated"),
    )

    assert result == {"routed": True, "path": str(folder), "tab": "image_gallery"}
    assert gallery.dropped == [[folder]], "no expansion for a folder-native tab"


def test_open_folder_into_creates_the_tab_once_and_re_reads(tmp_path) -> None:
    folder = _folder(tmp_path)
    mc = _Tab(folders=False)
    live: list[tuple[str, _Tab]] = []
    actions: list[str] = []

    def _run_action(action_id: str) -> None:
        actions.append(action_id)
        live.append(("multi_compare", mc))

    result = drop_routing.open_folder_into(
        folder,
        "multi_compare",
        tabs=lambda: list(live),
        kinds=["multi_compare"],
        run_action=_run_action,
    )

    assert actions == ["workspace.new_multi_compare"]
    assert result["tab"] == "multi_compare" and result["images"] == 3


def test_open_folder_into_rejects_an_unknown_kind(tmp_path) -> None:
    with pytest.raises(ValueError, match="unknown tab kind"):
        drop_routing.open_folder_into(
            _folder(tmp_path),
            "wibble",
            tabs=lambda: [],
            kinds=["multi_compare"],
            run_action=lambda _action: None,
        )


def test_open_folder_into_reports_a_tab_that_accepts_nothing(tmp_path) -> None:
    folder = _folder(tmp_path)
    stub = _Tab(folders=False, files=False)

    with pytest.raises(ValueError, match="did not accept"):
        drop_routing.open_folder_into(
            folder,
            "multi_compare",
            tabs=lambda: [("multi_compare", stub)],
            kinds=["multi_compare"],
            run_action=lambda _action: None,
        )


def test_open_folder_into_folder_without_images_keeps_the_directory_attempt(tmp_path) -> None:
    """An empty (or image-less) folder: no expansion, honest failure."""
    folder = tmp_path / "empty"
    folder.mkdir()
    (folder / "notes.txt").write_bytes(b"x")
    stub = _Tab(folders=False, files=True)

    with pytest.raises(ValueError, match="did not accept"):
        drop_routing.open_folder_into(
            folder,
            "multi_compare",
            tabs=lambda: [("multi_compare", stub)],
            kinds=["multi_compare"],
            run_action=lambda _action: None,
        )
    assert stub.dropped == []
