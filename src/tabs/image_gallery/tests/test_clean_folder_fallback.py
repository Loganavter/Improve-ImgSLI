"""Move without state.folder (file-drop sessions): common-parent fallback.

Regression: clean_rejected hard-required state.folder, so Move on a
folder-less session hid the overlay and moved nothing (logged "no folder")
while the subtitle promised the common parent. Folder resolution is shared
(triage.resolve_move_folder) between the subtitle and the move.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.ui.clean_review import _display_folder_for_items
from tabs.image_gallery.use_cases import triage as _triage


def _drop_file(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (16, 16), (10, 20, 30)).save(path)


def _rejected_item(path: Path) -> SimpleNamespace:
    return SimpleNamespace(rejected=True, path=str(path), name=path.name, thumbnail=None)


def test_move_uses_common_parent_without_state_folder(tmp_path: Path) -> None:
    _drop_file(tmp_path / "a.png")
    _drop_file(tmp_path / "b.png")
    owner = SimpleNamespace(
        state=SimpleNamespace(items=[_rejected_item(tmp_path / "a.png"), _rejected_item(tmp_path / "b.png")], folder=None)
    )
    moves = _triage.clean_rejected(owner)
    assert len(moves) == 2
    assert (tmp_path / "_rejected" / "a.png").is_file()
    assert (tmp_path / "_rejected" / "b.png").is_file()
    assert not (tmp_path / "a.png").exists()


def test_disagreeing_parents_move_nothing(tmp_path: Path) -> None:
    other = tmp_path / "sub"
    other.mkdir()
    _drop_file(tmp_path / "a.png")
    _drop_file(other / "b.png")
    owner = SimpleNamespace(
        state=SimpleNamespace(
            items=[_rejected_item(tmp_path / "a.png"), _rejected_item(other / "b.png")],
            folder=None,
        )
    )
    assert _triage.clean_rejected(owner) == []
    assert (tmp_path / "a.png").is_file()


def test_subtitle_matches_move_target(tmp_path: Path) -> None:
    _drop_file(tmp_path / "a.png")
    owner = SimpleNamespace(
        state=SimpleNamespace(items=[_rejected_item(tmp_path / "a.png")], folder=None)
    )
    assert _display_folder_for_items(owner, owner.state.items) == str(tmp_path)
